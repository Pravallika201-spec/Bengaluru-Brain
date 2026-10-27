"""
SEPARATE forecasting-only collector built on the SAME real curated
location list (traffic_location_mapping.csv) and the SAME TomTom
flowSegmentData call and CSV field schema as the existing
collect_live_traffic_history.py — that file is NOT modified, its
citywide-rotation behavior over every MATCHED row is preserved exactly
as-is.

This script instead polls a SMALL, FIXED, NEVER-ROTATED set of 8 real
MATCHED locations from the same mapping file, every 5 minutes, forever
(or --once), writing to its own separate output file
(forecast_locations_history.csv — never mixed into live_traffic_history.csv).

Why a fixed 8, not all 39: the existing collector visiting every location
per cycle means any ONE location is only revisited once per full sweep —
fine for citywide breadth, but the opposite of what a T+120-ahead
supervised dataset needs (dense, frequent, same-location observations).
See traffic_module/backend/forecasting/README.md for the measured
readiness audit that motivated this trade-off.
"""
import argparse
import csv
import json
import os
import time
from datetime import date, datetime

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(HERE, "traffic_location_mapping.csv")
OUTPUT_FILE = os.path.join(HERE, "forecast_locations_history.csv")
QUOTA_STATE_FILE = os.path.join(HERE, "forecast_locations_quota_state.json")

TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
INTERVAL_SECONDS = 300  # unchanged from the existing collector — 5 minutes
API_KEY = os.environ.get("TOMTOM_API_KEY")

# Quota protection: 8 locations x 288 cycles/day = 2,304/day theoretical.
# The guard below refuses further requests once this many are made today,
# leaving headroom under a typical 2,500/day free-tier budget.
MAX_REQUESTS_PER_DAY = 2300

CSV_COLUMNS = [
    "timestamp", "traffic_location", "latitude", "longitude", "nearest_node",
    "current_speed_kmh", "free_flow_speed_kmh", "current_travel_time_sec",
    "free_flow_travel_time_sec", "delay_sec", "delay_percent", "confidence",
    "road_closure", "status", "http_status",
]

# The 8 fixed real MATCHED locations (from traffic_location_mapping.csv),
# chosen for being major, well-known, geographically-spread Bengaluru
# congestion points — see the accompanying report for the selection
# rationale for each. Only the NAME is fixed here; lat/lon/nearest_node
# are looked up fresh from the mapping file at every startup so a change
# to that file is always reflected honestly, never hardcoded stale here.
FIXED_LOCATION_NAMES = [
    "Silk Board Junction",
    "Hebbal Flyover",
    "Outer Ring Road",
    "Hosur Road",
    "Tumkur Road",
    "Marathahalli Bridge",
    "Bellary Road",
    "KR Puram",
]


def _parser():
    p = argparse.ArgumentParser(description="Forecasting-only fixed-8-location TomTom collector")
    p.add_argument("--once", action="store_true", help="Collect exactly one snapshot and exit")
    p.add_argument("--validate-only", action="store_true", help="Check the 8 locations with one real TomTom request each and exit, no CSV writes")
    p.add_argument("--status", action="store_true", help="Print the collection summary and exit, no API calls")
    return p


def resolve_fixed_locations():
    """Looks up each fixed name's REAL current row in the mapping file.
    A name that isn't MATCHED, or is missing lat/lon, is reported as a
    problem — never silently swapped for a guess."""
    mapping = pd.read_csv(MAPPING_FILE)
    resolved, problems = [], []

    for name in FIXED_LOCATION_NAMES:
        rows = mapping[mapping["traffic_location"] == name]
        if rows.empty:
            problems.append(f"{name}: not found in {MAPPING_FILE}")
            continue
        row = rows.iloc[0]
        if str(row.get("status", "")).upper() != "MATCHED":
            problems.append(f"{name}: status is '{row.get('status')}', not MATCHED")
            continue
        if pd.isna(row.get("latitude")) or pd.isna(row.get("longitude")):
            problems.append(f"{name}: missing latitude/longitude")
            continue
        resolved.append({
            "traffic_location": name,
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "nearest_node": row.get("nearest_node"),
        })

    return resolved, problems


def get_live_traffic(latitude, longitude):
    if not API_KEY:
        return {"status": "ERROR", "http_status": None, "current_speed": None, "free_flow_speed": None,
                "current_travel_time": None, "free_flow_travel_time": None, "confidence": None, "road_closure": None}
    params = {"key": API_KEY, "point": f"{latitude},{longitude}"}
    try:
        response = requests.get(TOMTOM_URL, params=params, timeout=15)
        if response.status_code != 200:
            return {"status": "ERROR", "http_status": response.status_code, "current_speed": None,
                    "free_flow_speed": None, "current_travel_time": None, "free_flow_travel_time": None,
                    "confidence": None, "road_closure": None}
        flow = response.json().get("flowSegmentData", {})
        return {
            "status": "OK", "http_status": response.status_code,
            "current_speed": flow.get("currentSpeed"), "free_flow_speed": flow.get("freeFlowSpeed"),
            "current_travel_time": flow.get("currentTravelTime"), "free_flow_travel_time": flow.get("freeFlowTravelTime"),
            "confidence": flow.get("confidence"), "road_closure": flow.get("roadClosure"),
        }
    except Exception:
        return {"status": "ERROR", "http_status": None, "current_speed": None, "free_flow_speed": None,
                "current_travel_time": None, "free_flow_travel_time": None, "confidence": None, "road_closure": None}


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
    with open(QUOTA_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


# ---------------- restart-safe duplicate prevention ----------------

def load_already_written_keys():
    written = set()
    if not os.path.exists(OUTPUT_FILE):
        return written
    with open(OUTPUT_FILE, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            written.add((row.get("traffic_location"), row.get("timestamp")))
    return written


def collect_snapshot(locations, already_written, timestamp_text=None):
    if timestamp_text is None:
        timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=" * 60)
    print("COLLECTING:", timestamp_text)
    print("=" * 60)

    rows = []
    successful = failed = skipped_duplicate = 0

    for position, loc in enumerate(locations, start=1):
        key = (loc["traffic_location"], timestamp_text)
        if key in already_written:
            skipped_duplicate += 1
            print(f"[{position}/{len(locations)}] {loc['traffic_location']} ... SKIPPED (already recorded for this timestamp)")
            continue

        print(f"[{position}/{len(locations)}] {loc['traffic_location']} ...", end=" ")
        traffic = get_live_traffic(loc["latitude"], loc["longitude"])

        if traffic["status"] == "OK":
            print(f"{traffic['current_speed']} km/h")
            successful += 1
        else:
            print(f"ERROR HTTP={traffic['http_status']}")
            failed += 1

        current_time = traffic["current_travel_time"]
        free_time = traffic["free_flow_travel_time"]
        if current_time is not None and free_time is not None:
            delay_seconds = current_time - free_time
            delay_percent = (delay_seconds / free_time) * 100 if free_time > 0 else 0
        else:
            delay_seconds = None
            delay_percent = None

        rows.append({
            "timestamp": timestamp_text,
            "traffic_location": loc["traffic_location"],
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "nearest_node": loc["nearest_node"],
            "current_speed_kmh": traffic["current_speed"],
            "free_flow_speed_kmh": traffic["free_flow_speed"],
            "current_travel_time_sec": current_time,
            "free_flow_travel_time_sec": free_time,
            "delay_sec": delay_seconds,
            "delay_percent": delay_percent,
            "confidence": traffic["confidence"],
            "road_closure": traffic["road_closure"],
            "status": traffic["status"],
            "http_status": traffic["http_status"],
        })
        already_written.add(key)
        time.sleep(0.2)

    return pd.DataFrame(rows, columns=CSV_COLUMNS), successful, failed, skipped_duplicate


def save_snapshot(snapshot_df):
    if snapshot_df.empty:
        return
    file_exists = os.path.exists(OUTPUT_FILE)
    snapshot_df.to_csv(OUTPUT_FILE, mode="a", header=not file_exists, index=False)


def print_status():
    if not os.path.exists(OUTPUT_FILE):
        print("No observations collected yet — output file does not exist:")
        print(f"  {OUTPUT_FILE}")
        return

    df = pd.read_csv(OUTPUT_FILE)
    print("=" * 60)
    print("FORECAST LOCATIONS COLLECTOR — SUMMARY")
    print("=" * 60)
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Selected 8 locations: {sorted(df['traffic_location'].unique().tolist())}")
    print(f"Successful requests (status=OK): {(df['status'] == 'OK').sum()}")
    print(f"Failed requests: {(df['status'] != 'OK').sum()}")
    print(f"Snapshots (unique timestamps): {df['timestamp'].nunique()}")
    print(f"Total rows: {len(df)}")
    print(f"Earliest timestamp: {df['timestamp'].min()}")
    print(f"Latest timestamp:   {df['timestamp'].max()}")

    dupes = df.duplicated(subset=["traffic_location", "timestamp"]).sum()
    print(f"Duplicate (location, timestamp) rows: {dupes}")

    quota = _load_quota_state()
    print(f"Quota today ({quota['date']}): {quota['requests_made']} / {MAX_REQUESTS_PER_DAY} requests used")


def main():
    args = _parser().parse_args()

    if args.status:
        print_status()
        return

    locations, problems = resolve_fixed_locations()

    print("=" * 60)
    print("FORECAST LOCATIONS COLLECTOR (fixed 8, no rotation)")
    print("=" * 60)
    print(f"Resolved {len(locations)}/{len(FIXED_LOCATION_NAMES)} fixed locations from {MAPPING_FILE}:")
    for loc in locations:
        print(f"  - {loc['traffic_location']}: ({loc['latitude']}, {loc['longitude']})")
    if problems:
        print("PROBLEMS (excluded):")
        for p in problems:
            print(f"  ! {p}")

    if args.validate_only:
        print()
        print("Validating each location with ONE real TomTom request (--validate-only)...")
        if not API_KEY:
            print("TOMTOM_API_KEY is not set — cannot validate. Set it and re-run --validate-only first.")
            return
        for loc in locations:
            result = get_live_traffic(loc["latitude"], loc["longitude"])
            status = "VALID" if result["status"] == "OK" else f"FAILED (HTTP {result['http_status']})"
            print(f"  - {loc['traffic_location']}: {status}")
        return

    if not API_KEY:
        print()
        print("ERROR: TOMTOM_API_KEY is not set.")
        print('Run: $env:TOMTOM_API_KEY="YOUR_KEY"')
        raise SystemExit(1)

    already_written = load_already_written_keys()
    print(f"Restart-safe: loaded {len(already_written)} existing (location,timestamp) keys from disk.")

    quota = _load_quota_state()

    print()
    print("Starting collection (Ctrl+C to stop)..." if not args.once else "Running --once (single snapshot).")

    try:
        while True:
            if quota["requests_made"] + len(locations) > MAX_REQUESTS_PER_DAY:
                print(f"QUOTA PROTECTION: {quota['requests_made']}/{MAX_REQUESTS_PER_DAY} used today — skipping this cycle.")
            else:
                snapshot, ok, failed, dup = collect_snapshot(locations, already_written)
                save_snapshot(snapshot)
                quota["requests_made"] += len(locations) - dup
                _save_quota_state(quota)
                print()
                print(f"Snapshot saved. Successful={ok} Failed={failed} SkippedDuplicate={dup}")
                if os.path.exists(OUTPUT_FILE):
                    print("Total rows stored:", len(pd.read_csv(OUTPUT_FILE)))
                print(f"Quota used: {quota['requests_made']}/{MAX_REQUESTS_PER_DAY}")

            if args.once:
                break

            print()
            print(f"Waiting {INTERVAL_SECONDS // 60} minutes...")
            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("COLLECTOR STOPPED")
        print("=" * 60)
        print_status()


if __name__ == "__main__":
    main()
