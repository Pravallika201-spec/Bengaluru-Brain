"""
EXPANDED forecasting-only TomTom collector — adds broader geographic
coverage on top of (never replacing) the original fixed-8-segment
collector (collect_forecast_segments.py, untouched by this file).

WHY A SEPARATE FILE: the original collector's 8 segments and its output
CSV (forecast_segments_history.csv) are the exact dataset the currently
trained/evaluated T+120 model and its saved metrics
(models/t120_preliminary_metrics.json) are built from. Adding segments
to that same file would silently change what "the dataset" means for
anyone re-running the existing training/evaluation pipeline against it.
This collector instead writes ADDITIONAL real segments to their OWN new
file (bengaluru_t120_expanded_history.csv), so the original 8-segment
dataset stays exactly as it is, byte for byte, and the expanded data is
available separately for a FUTURE retrain once enough of it accumulates.

REUSE, NOT DUPLICATION: this module imports get_traffic()/load_graph()
from collect_forecast_segments.py rather than reimplementing TomTom
request handling -- the only things that differ here are the segment
list, the polling interval, the output files, and the quota budget
(each independently configurable, see below).

SEGMENT SELECTION: every entry in FIXED_SEGMENTS_EXPANDED is a real
(osm_u, osm_v, osm_key) edge identity, resolved from the project's own
existing OSM graph (backend/data/bengaluru_graph.pkl) -- found by
searching that graph's real edge `name` tags for each requested Bengaluru
corridor (Outer Ring Road, Hosur Road, Sarjapur Road, MG Road, ...), and
for corridor/area names that aren't literal road names in OSM (KR Puram,
Yeshwanthpur, MG Road's exact tag "Mahatma Gandhi Road"), by finding the
nearest real trunk/primary/secondary edge to that area's already-existing
coordinate in this project's own location_data.py (the same "landmark ->
nearest real graph edge" pattern models/predict_route_v2.py already uses
for routing -- not a new coordinate, not a Google lookup, and not
invented). None of these 21 edges duplicate the original 8's
(osm_u, osm_v, osm_key) triples. "Electronic City" was searched but no
real named arterial edge was found close enough to it in the graph to
honestly attribute to that name -- it is deliberately left out rather
than mislabeling a distant/unnamed edge; the Hosur Road segment already
covers that corridor.

QUOTA SAFETY: segment count and polling interval are both configurable
via environment variables (FORECAST_SEGMENT_COUNT, FORECAST_INTERVAL_SECONDS)
specifically so this collector's real daily request volume can be tuned
to whatever the operator's actual TomTom plan allows -- see the printed
"estimated requests/day" at startup, computed from whatever count/interval
are actually in effect, never a fixed assumption.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_forecast_segments import get_traffic, load_graph  # reuse, don't duplicate

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

OUTPUT_FILE = os.path.join(DATA_DIR, "bengaluru_t120_expanded_history.csv")
ERROR_FILE = os.path.join(DATA_DIR, "bengaluru_t120_expanded_errors.csv")
QUOTA_STATE_FILE = os.path.join(DATA_DIR, "forecast_expanded_collector_quota_state.json")

REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.3

# Configurable via environment variables -- never hardcoded deep in the
# logic, per the requirement to make count/interval tunable to the
# operator's real TomTom quota.
#
# Default: 21 segments (the real corridor edges resolved below) at a
# 1800s (30 min) interval -> 21 * (86400/1800) = 21 * 48 = 1,008
# requests/day for THIS collector. This is deliberately conservative and
# mirrors the original 8-segment collector's own budgeting style (which
# targets ~2,300/day at a 5-min interval); running BOTH collectors
# together would total ~1,008 + 2,300 = ~3,308 requests/day -- if your
# TomTom plan's daily cap is the commonly-documented free-tier 2,500/day,
# do not run both concurrently without lowering FORECAST_SEGMENT_COUNT
# and/or raising FORECAST_INTERVAL_SECONDS first (or confirm your actual
# plan's real daily limit and adjust MAX_REQUESTS_PER_DAY accordingly).
# A 30-minute revisit interval still comfortably supports T+120 pairing:
# an observation 4 cycles (120 min) later falls well within the dataset
# builder's existing +-15 minute tolerance.
FORECAST_INTERVAL_SECONDS = int(os.environ.get("FORECAST_INTERVAL_SECONDS", "1800"))

API_KEY = os.environ.get("TOMTOM_API_KEY") or os.environ.get("TRAFFIC_API_KEY")

CSV_COLUMNS = [
    "timestamp", "data_mode", "osm_u", "osm_v", "osm_key", "latitude", "longitude",
    "road_name", "highway", "edge_length_m", "base_speed_kph",
    "status", "http_status", "current_speed_kmh", "free_flow_speed_kmh",
    "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
    "road_closure", "tomtom_segment_id", "speed_ratio", "delay_percent",
]

# Real (osm_u, osm_v, osm_key) edge identities resolved from the actual
# graph (backend/data/bengaluru_graph.pkl) -- see module docstring for
# exactly how each was found. Every one of these is confirmed distinct
# from the original 8 fixed segments in collect_forecast_segments.py.
# Attributes (name/highway/length/coords) are looked up fresh from the
# real graph at every startup below, never hardcoded here.
FIXED_SEGMENTS_EXPANDED = [
    {"label": "Outer Ring Road (Banashankari)", "u": 247974062, "v": 7291672021, "key": 0},
    {"label": "Hosur Road (Koramangala)", "u": 60952302, "v": 62013232, "key": 0},
    {"label": "Bellary Road (Ganganagar)", "u": 282765938, "v": 461539120, "key": 0},
    {"label": "Old Madras Road (KR Puram)", "u": 442437516, "v": 11886006947, "key": 0},
    {"label": "Tumkur Road (Yeshwanthpur)", "u": 251361763, "v": 427594204, "key": 0},
    {"label": "Bangalore-Mysore Road (Kengeri)", "u": 66666538, "v": 1110309152, "key": 0},
    {"label": "Kanakapura Road", "u": 248809625, "v": 308807637, "key": 0},
    {"label": "Bannerghatta Road", "u": 247966696, "v": 5273034569, "key": 0},
    {"label": "Sarjapur Road (Varthur)", "u": 292565706, "v": 307396348, "key": 0},
    {"label": "Whitefield Road", "u": 251106545, "v": 251106828, "key": 0},
    {"label": "Marathahalli Underpass", "u": 343326429, "v": 11350180411, "key": 0},
    {"label": "Silk Board Interchange", "u": 306611194, "v": 12969313169, "key": 0},
    {"label": "Hebbal Flyover", "u": 332955193, "v": 6531392925, "key": 0},
    {"label": "HAL Old Airport Road", "u": 251099553, "v": 251099555, "key": 0},
    {"label": "Richmond Road", "u": 248455257, "v": 248455450, "key": 0},
    {"label": "Residency Road", "u": 60952254, "v": 248459877, "key": 0},
    {"label": "Magadi Road", "u": 249084518, "v": 1520838648, "key": 0},
    {"label": "Old Mysuru Road", "u": 347295567, "v": 429286801, "key": 0},
    {"label": "Yeshwanthpur (Nelamangala-Majestic Rd)", "u": 463393130, "v": 6513888393, "key": 0},
    {"label": "KR Puram (Devasandra Main Road)", "u": 1837297484, "v": 7479986365, "key": 0},
    {"label": "MG Road (Mahatma Gandhi Road)", "u": 334473795, "v": 11464483504, "key": 0},
]

# How many of the segments above to actually poll each cycle -- lets an
# operator dial coverage vs. quota usage down (or, up to the full list
# above, up) without editing code.
FORECAST_SEGMENT_COUNT = int(os.environ.get("FORECAST_SEGMENT_COUNT", str(len(FIXED_SEGMENTS_EXPANDED))))

# Sized to this collector's own configured segment count/interval (see
# comment above) -- recomputed at import time so changing the env vars
# also changes the enforced daily cap consistently, not just the printed
# estimate.
_cycles_per_day = 86400 / FORECAST_INTERVAL_SECONDS
MAX_REQUESTS_PER_DAY = int(FORECAST_SEGMENT_COUNT * _cycles_per_day)


def _parser():
    p = argparse.ArgumentParser(description="Expanded forecasting-only TomTom collector (broader real Bengaluru corridor coverage)")
    p.add_argument("--once", action="store_true", help="Collect exactly one cycle and exit")
    p.add_argument("--validate-only", action="store_true", help="Check the segments (graph + one real TomTom call each) and exit, no CSV writes")
    p.add_argument("--status", action="store_true", help="Print the collection status/report and exit, no API calls")
    return p


def resolve_expanded_segments(graph):
    """Same resolution logic as the original collector's
    resolve_fixed_segments(): looks up each (u,v,key)'s REAL current
    attributes from the graph. A segment failing this is reported, not
    silently dropped or replaced with a guess. Only the first
    FORECAST_SEGMENT_COUNT entries of FIXED_SEGMENTS_EXPANDED are used."""
    resolved = []
    problems = []

    for seg in FIXED_SEGMENTS_EXPANDED[:FORECAST_SEGMENT_COUNT]:
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


# ---------------- quota protection (same pattern as the original collector) ----------------

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


# ---------------- restart-safe duplicate prevention (same pattern) ----------------

def load_already_written_keys():
    written = set()
    if not os.path.exists(OUTPUT_FILE):
        return written
    with open(OUTPUT_FILE, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            written.add((row.get("osm_u"), row.get("osm_v"), row.get("osm_key"), row.get("timestamp")))
    return written


def _validate_row(row: dict) -> tuple[bool, str]:
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
    print("=" * 70)
    print("EXPANDED FORECAST SEGMENT COLLECTOR — STATUS")
    print("=" * 70)
    print(f"Configured segments: {FORECAST_SEGMENT_COUNT} (of {len(FIXED_SEGMENTS_EXPANDED)} defined)")
    print(f"Configured interval: {FORECAST_INTERVAL_SECONDS}s ({FORECAST_INTERVAL_SECONDS/60:.1f} min)")
    print(f"Estimated requests/day: {MAX_REQUESTS_PER_DAY} "
          f"({FORECAST_SEGMENT_COUNT} segments x {_cycles_per_day:.1f} cycles/day)")

    if not os.path.exists(OUTPUT_FILE):
        print()
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
    for r in rows:
        k = (r["osm_u"], r["osm_v"], r["osm_key"], r["timestamp"])
        dup_check[k] = dup_check.get(k, 0) + 1
    duplicates = sum(c - 1 for c in dup_check.values() if c > 1)

    parsed_ts = sorted(datetime.fromisoformat(t) for t in timestamps)
    avg_interval_min = None
    if len(parsed_ts) >= 2:
        gaps = [(parsed_ts[i + 1] - parsed_ts[i]).total_seconds() / 60 for i in range(len(parsed_ts) - 1)]
        avg_interval_min = sum(gaps) / len(gaps)

    print()
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Total observations (rows): {len(rows)}")
    print(f"  OK: {len(ok_rows)}   FAILED: {len(failed_rows)}")
    print(f"Unique segments: {len(segments)} (expected {FORECAST_SEGMENT_COUNT})")
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
    segments, problems = resolve_expanded_segments(graph)

    print("=" * 70)
    print("EXPANDED FORECAST SEGMENT COLLECTOR")
    print("=" * 70)
    print(f"Configured segments: {FORECAST_SEGMENT_COUNT} (of {len(FIXED_SEGMENTS_EXPANDED)} defined)")
    print(f"Configured interval: {FORECAST_INTERVAL_SECONDS}s ({FORECAST_INTERVAL_SECONDS/60:.1f} min)")
    print(f"Estimated requests/day: {MAX_REQUESTS_PER_DAY} "
          f"({FORECAST_SEGMENT_COUNT} segments x {_cycles_per_day:.1f} cycles/day)")
    print(f"Segments resolved from real graph: {len(segments)}/{FORECAST_SEGMENT_COUNT}")
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
                print(f"[{datetime.now().isoformat(timespec='seconds')}] Collecting {len(segments)} expanded segments...")
                rows, ok, failed, dup, invalid = collect_cycle(segments, already_written)
                save_rows(rows)
                quota["requests_made"] += len(segments)
                _save_quota_state(quota)
                print(f"  OK={ok} FAILED={failed} SKIPPED_DUPLICATE={dup} SKIPPED_INVALID={invalid} "
                      f"quota_used={quota['requests_made']}/{MAX_REQUESTS_PER_DAY}")

            if args.once:
                break

            time.sleep(FORECAST_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print()
        print("Collector stopped.")


if __name__ == "__main__":
    main()
