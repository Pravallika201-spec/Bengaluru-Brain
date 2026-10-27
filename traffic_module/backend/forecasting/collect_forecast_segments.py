"""
SEPARATE, forecasting-only TomTom collector — intentionally NOT the same
as collect_bengaluru_traffic_production.py (369-ward citywide rotation).
That collector's design (one representative edge per ward, batched and
rotated) structurally cannot support T+120 forecasting: the audit in
data/forecast/data_readiness_report.json found a ~354-minute median
per-edge revisit interval there, versus the ~120-minute horizon needed
here. This collector fixes that by doing the opposite trade: a SMALL,
FIXED, NEVER-ROTATED set of 8 real segments, polled every 5 minutes,
every cycle, with no citywide-coverage goal at all.

Writes to its own file (forecasting/data/forecast_segments_history.csv)
— never mixed into bengaluru_traffic_history.csv (see requirement to
keep this dataset separate).

STILL TRUE (repeated deliberately): this collector prepares data. It
does not, on its own, prove enough data exists yet — see --status and
the project's own forecasting/README.md / data_readiness_report.json
for that judgment, made separately from actual measured pair counts.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import sys
import time
from datetime import datetime, date

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DATA_DIR = os.path.join(HERE, "data")

GRAPH_FILE = os.path.join(BACKEND, "data", "bengaluru_graph.pkl")
OUTPUT_FILE = os.path.join(DATA_DIR, "forecast_segments_history.csv")
ERROR_FILE = os.path.join(DATA_DIR, "forecast_segments_errors.csv")
QUOTA_STATE_FILE = os.path.join(DATA_DIR, "forecast_collector_quota_state.json")

TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
API_KEY = os.environ.get("TOMTOM_API_KEY") or os.environ.get("TRAFFIC_API_KEY")

INTERVAL_SECONDS = 300  # 5 minutes — fixed, no rotation
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.3

# Quota protection: refuses to make another request once this many have
# been made today, regardless of what the caller asks for. 8 segments x
# 288 cycles/day = 2,304/day — comfortably under a 2,500/day free-tier
# budget with headroom. Configurable, not hardcoded deep in the logic.
MAX_REQUESTS_PER_DAY = 2300

# The 8 fixed segments (real OSM u,v,key identities — never rotated).
# Selected from the actual graph for being major (trunk/primary) named
# corridors, geographically spread across Bengaluru (not clustered), and
# widely recognized/high-traffic — see the accompanying report for the
# exact selection query. Attributes (name/highway/coords) are looked up
# fresh from the real graph at every startup below, never hardcoded here,
# so a graph update is always reflected honestly.
FIXED_SEGMENTS = [
    {"label": "Outer Ring Road", "u": 11846694183, "v": 335648021, "key": 0},
    {"label": "Hosur Road", "u": 11919389037, "v": 13633447127, "key": 0},
    {"label": "Bellary Road", "u": 12553535777, "v": 332955193, "key": 0},
    {"label": "Old Madras Road", "u": 343459489, "v": 1483859318, "key": 0},
    {"label": "Tumkur Road", "u": 426403819, "v": 11886298793, "key": 0},
    {"label": "Bangalore-Mysore Road", "u": 6226329981, "v": 248677965, "key": 0},
    {"label": "Marathahalli Underpass", "u": 6562185321, "v": 343322993, "key": 0},
    {"label": "Silk Board Flyover", "u": 8239947030, "v": 12040966310, "key": 0},
]

CSV_COLUMNS = [
    "timestamp", "data_mode", "osm_u", "osm_v", "osm_key", "latitude", "longitude",
    "road_name", "highway", "edge_length_m", "base_speed_kph",
    "status", "http_status", "current_speed_kmh", "free_flow_speed_kmh",
    "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
    "road_closure", "tomtom_segment_id", "speed_ratio", "delay_percent",
]


def _parser():
    p = argparse.ArgumentParser(description="Forecasting-only fixed-8-segment TomTom collector")
    p.add_argument("--once", action="store_true", help="Collect exactly one cycle and exit")
    p.add_argument("--validate-only", action="store_true", help="Check the 8 segments (graph + one real TomTom call each) and exit, no CSV writes")
    p.add_argument("--status", action="store_true", help="Print the collection status/report and exit, no API calls")
    return p


def load_graph():
    with open(GRAPH_FILE, "rb") as f:
        return pickle.load(f)


def resolve_fixed_segments(graph):
    """Looks up each fixed (u,v,key)'s REAL current attributes from the
    graph. A segment failing this (missing node, missing coordinates) is
    reported, not silently dropped or replaced with a guess."""
    resolved = []
    problems = []

    for seg in FIXED_SEGMENTS:
        u, v, key = seg["u"], seg["v"], seg["key"]

        if not graph.has_edge(u, v, key):
            problems.append(f"{seg['label']}: edge ({u},{v},{key}) not found in current graph")
            continue

        data = graph.get_edge_data(u, v, key)
        u_data, v_data = graph.nodes.get(u), graph.nodes.get(v)

        if not u_data or not v_data:
            problems.append(f"{seg['label']}: missing node data for u={u} or v={v}")
            continue

        lat1, lon1 = u_data.get("y"), u_data.get("x")
        lat2, lon2 = v_data.get("y"), v_data.get("x")

        if None in (lat1, lon1, lat2, lon2):
            problems.append(f"{seg['label']}: missing coordinates on edge endpoints")
            continue

        highway = data.get("highway")
        name = data.get("name")

        resolved.append({
            "label": seg["label"],
            "u": u, "v": v, "key": key,
            "latitude": (float(lat1) + float(lat2)) / 2,
            "longitude": (float(lon1) + float(lon2)) / 2,
            "road_name": " | ".join(name) if isinstance(name, list) else (name or seg["label"]),
            "highway": " | ".join(highway) if isinstance(highway, list) else str(highway),
            "edge_length_m": float(data.get("length", 0)),
            "base_speed_kph": float(data.get("speed_kph", 0)),
        })

    return resolved, problems


def get_traffic(latitude, longitude):
    if not API_KEY:
        return {"status": "ERROR", "http_status": None, "error": "TOMTOM_API_KEY not configured"}
    params = {"key": API_KEY, "point": f"{latitude},{longitude}"}
    try:
        response = requests.get(TOMTOM_URL, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return {"status": "ERROR", "http_status": response.status_code, "error": response.text[:300]}
        data = response.json()
        flow = data.get("flowSegmentData")
        if not flow:
            return {"status": "ERROR", "http_status": response.status_code, "error": "flowSegmentData missing"}
        return {
            "status": "OK",
            "http_status": response.status_code,
            "current_speed_kmh": flow.get("currentSpeed"),
            "free_flow_speed_kmh": flow.get("freeFlowSpeed"),
            "current_travel_time_sec": flow.get("currentTravelTime"),
            "free_flow_travel_time_sec": flow.get("freeFlowTravelTime"),
            "confidence": flow.get("confidence"),
            "road_closure": flow.get("roadClosure"),
            "tomtom_segment_id": "|".join(f"{c['latitude']:.5f},{c['longitude']:.5f}" for c in flow.get("coordinates", {}).get("coordinate", [])[:1]) or None,
        }
    except Exception as e:
        return {"status": "ERROR", "http_status": None, "error": str(e)}


# ---------------- quota protection ----------------

def _load_quota_state():
    if os.path.exists(QUOTA_STATE_FILE):
        try:
            with open(QUOTA_STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == date.today().isoformat():
                return state
        except (json.JSONDecodeError, OSError):
            pass
    return {"date": date.today().isoformat(), "requests_made": 0}


def _save_quota_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(QUOTA_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def quota_allows(state, n_requests):
    return state["requests_made"] + n_requests <= MAX_REQUESTS_PER_DAY


# ---------------- restart-safe duplicate prevention ----------------

def load_already_written_keys():
    """(segment_key, timestamp) pairs already on disk — a restart will
    skip re-writing any of these even if a cycle happens to land on the
    exact same minute."""
    written = set()
    if not os.path.exists(OUTPUT_FILE):
        return written
    with open(OUTPUT_FILE, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            written.add((row.get("osm_u"), row.get("osm_v"), row.get("osm_key"), row.get("timestamp")))
    return written


def _validate_row(row: dict) -> tuple[bool, str]:
    """Sanity-checks a row before it is ever written — never silently
    saves something structurally wrong."""
    try:
        datetime.fromisoformat(row["timestamp"])
    except (ValueError, KeyError):
        return False, "unparseable/missing timestamp"
    if row.get("osm_u") is None or row.get("osm_v") is None:
        return False, "missing segment identity"
    lat, lon = row.get("latitude"), row.get("longitude")
    if lat is None or lon is None or not (12.7 <= float(lat) <= 13.3) or not (77.3 <= float(lon) <= 77.9):
        return False, "coordinates outside plausible Bengaluru bounding box"
    if row["status"] == "OK":
        cs = row.get("current_speed_kmh")
        if cs is not None and not (0 <= float(cs) <= 150):
            return False, f"implausible current_speed_kmh: {cs}"
    return True, ""


def collect_cycle(segments, already_written, timestamp: str | None = None):
    """timestamp is normally left None (real wall-clock time) — the
    explicit-timestamp path exists so the restart-safe dedup guard can be
    exercised deterministically in tests without waiting on real time."""
    if timestamp is None:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    successful = 0
    failed = 0
    skipped_duplicate = 0
    skipped_invalid = 0

    for seg in segments:
        key_tuple = (str(seg["u"]), str(seg["v"]), str(seg["key"]), timestamp)
        if key_tuple in already_written:
            skipped_duplicate += 1
            continue

        traffic = get_traffic(seg["latitude"], seg["longitude"])

        row = {
            "timestamp": timestamp,
            "data_mode": "LIVE_TOMTOM" if traffic["status"] == "OK" else "LIVE_TOMTOM_ATTEMPT_FAILED",
            "osm_u": seg["u"], "osm_v": seg["v"], "osm_key": seg["key"],
            "latitude": seg["latitude"], "longitude": seg["longitude"],
            "road_name": seg["road_name"], "highway": seg["highway"],
            "edge_length_m": seg["edge_length_m"], "base_speed_kph": seg["base_speed_kph"],
            "status": traffic["status"], "http_status": traffic.get("http_status"),
            "current_speed_kmh": traffic.get("current_speed_kmh"),
            "free_flow_speed_kmh": traffic.get("free_flow_speed_kmh"),
            "current_travel_time_sec": traffic.get("current_travel_time_sec"),
            "free_flow_travel_time_sec": traffic.get("free_flow_travel_time_sec"),
            "confidence": traffic.get("confidence"),
            "road_closure": traffic.get("road_closure"),
            "tomtom_segment_id": traffic.get("tomtom_segment_id"),
        }

        current = row.get("current_speed_kmh")
        free = row.get("free_flow_speed_kmh")
        if current is not None and free:
            row["speed_ratio"] = round(current / free, 4)
            row["delay_percent"] = round(max(0.0, (1 - current / free)) * 100, 1)
        else:
            row["speed_ratio"] = None
            row["delay_percent"] = None

        ok, reason = _validate_row(row)
        if not ok:
            print(f"  [SKIPPED-INVALID] {seg['label']}: {reason}")
            skipped_invalid += 1
            continue

        if traffic["status"] == "OK":
            successful += 1
        else:
            failed += 1
            print(f"  [FAILED] {seg['label']}: {traffic.get('error')}")

        rows.append(row)
        already_written.add(key_tuple)
        time.sleep(REQUEST_DELAY_SECONDS)

    return rows, successful, failed, skipped_duplicate, skipped_invalid


def save_rows(rows):
    if not rows:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    file_exists = os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    errors = [r for r in rows if r["status"] == "ERROR"]
    if errors:
        error_exists = os.path.exists(ERROR_FILE)
        with open(ERROR_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if not error_exists:
                writer.writeheader()
            for row in errors:
                writer.writerow(row)


def print_status():
    """Item 16 — no API calls, reads only what's already on disk."""
    if not os.path.exists(OUTPUT_FILE):
        print("No observations collected yet — output file does not exist:")
        print(f"  {OUTPUT_FILE}")
        return

    with open(OUTPUT_FILE, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("Output file exists but has no rows yet.")
        return

    timestamps = sorted({r["timestamp"] for r in rows})
    segments = {(r["osm_u"], r["osm_v"], r["osm_key"]) for r in rows}
    ok_rows = [r for r in rows if r["status"] == "OK"]
    failed_rows = [r for r in rows if r["status"] != "OK"]

    dup_check = {}
    duplicates = 0
    for r in rows:
        k = (r["osm_u"], r["osm_v"], r["osm_key"], r["timestamp"])
        dup_check[k] = dup_check.get(k, 0) + 1
    duplicates = sum(c - 1 for c in dup_check.values() if c > 1)

    parsed_ts = sorted(datetime.fromisoformat(t) for t in timestamps)
    avg_interval_min = None
    if len(parsed_ts) >= 2:
        gaps = [(parsed_ts[i + 1] - parsed_ts[i]).total_seconds() / 60 for i in range(len(parsed_ts) - 1)]
        avg_interval_min = sum(gaps) / len(gaps)

    print("=" * 70)
    print("FORECAST SEGMENT COLLECTOR — STATUS")
    print("=" * 70)
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Total observations (rows): {len(rows)}")
    print(f"  OK: {len(ok_rows)}   FAILED: {len(failed_rows)}")
    print(f"Unique segments: {len(segments)} (expected {len(FIXED_SEGMENTS)})")
    print(f"Unique timestamps (collection cycles): {len(timestamps)}")
    print(f"Average polling interval: {avg_interval_min:.2f} min" if avg_interval_min else "Average polling interval: n/a (need >=2 cycles)")
    print(f"Duplicate (segment,timestamp) rows found: {duplicates}")
    print(f"Earliest timestamp: {timestamps[0]}")
    print(f"Latest timestamp:   {timestamps[-1]}")

    quota = _load_quota_state()
    print()
    print(f"Quota today ({quota['date']}): {quota['requests_made']} / {MAX_REQUESTS_PER_DAY} requests used")


def main():
    args = _parser().parse_args()

    if args.status:
        print_status()
        return

    graph = load_graph()
    segments, problems = resolve_fixed_segments(graph)

    print("=" * 70)
    print("FORECAST SEGMENT COLLECTOR")
    print("=" * 70)
    print(f"Fixed segments resolved from real graph: {len(segments)}/{len(FIXED_SEGMENTS)}")
    for s in segments:
        print(f"  - {s['label']}: {s['road_name']} [{s['highway']}] ({s['latitude']:.5f},{s['longitude']:.5f})")
    if problems:
        print("PROBLEMS (excluded from collection):")
        for p in problems:
            print(f"  ! {p}")

    if args.validate_only:
        print()
        print("Validating each segment with ONE real TomTom call (--validate-only)...")
        if not API_KEY:
            print("TOMTOM_API_KEY is not set — cannot make real validation calls. "
                  "Set it and re-run --validate-only before starting continuous collection.")
            return
        for s in segments:
            result = get_traffic(s["latitude"], s["longitude"])
            status = "VALID" if result["status"] == "OK" else f"FAILED ({result.get('error')})"
            print(f"  - {s['label']}: {status}")
        return

    if not API_KEY:
        print()
        print("ERROR: TOMTOM_API_KEY is not set. Run: $env:TOMTOM_API_KEY=\"YOUR_KEY\"")
        raise SystemExit(1)

    already_written = load_already_written_keys()
    print(f"Restart-safe: loaded {len(already_written)} existing (segment,timestamp) keys from disk.")

    quota = _load_quota_state()

    try:
        while True:
            if not quota_allows(quota, len(segments)):
                print(f"QUOTA PROTECTION: {quota['requests_made']}/{MAX_REQUESTS_PER_DAY} used today — "
                      f"skipping this cycle to stay within budget.")
            else:
                print()
                print(f"[{datetime.now().isoformat(timespec='seconds')}] Collecting {len(segments)} fixed segments...")
                rows, ok, failed, dup, invalid = collect_cycle(segments, already_written)
                save_rows(rows)
                quota["requests_made"] += len(segments)
                _save_quota_state(quota)
                print(f"  OK={ok} FAILED={failed} SKIPPED_DUPLICATE={dup} SKIPPED_INVALID={invalid} "
                      f"quota_used={quota['requests_made']}/{MAX_REQUESTS_PER_DAY}")

            if args.once:
                break

            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print()
        print("Collector stopped.")


if __name__ == "__main__":
    main()
