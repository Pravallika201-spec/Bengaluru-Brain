import argparse
import os
import time
import requests
import pandas as pd
from datetime import datetime

# --single-shot lets this be triggered by an OS scheduler (cron / Windows
# Task Scheduler / systemd timer) instead of relying on this process's own
# infinite loop staying alive forever. This is the more robust "scheduled
# collector" pattern: if a scheduled run crashes, the *next* scheduled run
# still fires; an in-process infinite loop that crashes just silently dies.
# Default (no flag) behavior is unchanged for anyone already using the loop.
_parser = argparse.ArgumentParser(description="Bengaluru real-time traffic collector")
_parser.add_argument("--once", action="store_true",
                      help="Collect exactly one snapshot and exit (for cron/Task Scheduler) "
                           "instead of looping forever in-process.")
_args, _unknown = _parser.parse_known_args()
MAPPING_FILE = "traffic_location_mapping.csv"
OUTPUT_FILE = "live_traffic_history.csv"
TOMTOM_URL = (
    "https://api.tomtom.com/"
    "traffic/services/4/flowSegmentData/"
    "absolute/10/json"
)
INTERVAL_SECONDS = 300   
API_KEY = os.environ.get("TOMTOM_API_KEY")
if not API_KEY:
    print("=" * 60)
    print("ERROR: TOMTOM_API_KEY is not set.")
    print("=" * 60)
    print()
    print('Run:')
    print('$env:TOMTOM_API_KEY="YOUR_KEY"')
    print()
    raise SystemExit(1)
mapping = pd.read_csv(
    MAPPING_FILE
)
mapping = mapping[
    mapping["status"]
    .astype(str)
    .str.upper()
    == "MATCHED"
].copy()
mapping = mapping.dropna(
    subset=[
        "latitude",
        "longitude"
    ]
).copy()
print("=" * 60)
print("REAL-TIME TRAFFIC COLLECTOR")
print("=" * 60)
print(
    "Locations:",
    len(mapping)
)
print(
    "Interval:",
    INTERVAL_SECONDS // 60,
    "minutes"
)
print(
    "Output:",
    OUTPUT_FILE
)
print("=" * 60)
def get_live_traffic(
    latitude,
    longitude
):
    params = {
        "key": API_KEY,
        "point": f"{latitude},{longitude}"
    }
    try:
        response = requests.get(
            TOMTOM_URL,
            params=params,
            timeout=15
        )
        if response.status_code != 200:
            return {
                "status": "ERROR",
                "current_speed": None,
                "free_flow_speed": None,
                "current_travel_time": None,
                "free_flow_travel_time": None,
                "confidence": None,
                "road_closure": None,
                "http_status":
                    response.status_code
            }
        data = response.json()
        flow = data.get(
            "flowSegmentData",
            {}
        )
        return {
            "status": "OK",
            "current_speed":
                flow.get(
                    "currentSpeed"
                ),
            "free_flow_speed":
                flow.get(
                    "freeFlowSpeed"
                ),
            "current_travel_time":
                flow.get(
                    "currentTravelTime"
                ),
            "free_flow_travel_time":
                flow.get(
                    "freeFlowTravelTime"
                ),
            "confidence":
                flow.get(
                    "confidence"
                ),
            "road_closure":
                flow.get(
                    "roadClosure"
                ),
            "http_status":
                response.status_code
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "current_speed": None,
            "free_flow_speed": None,
            "current_travel_time": None,
            "free_flow_travel_time": None,
            "confidence": None,
            "road_closure": None,
            "http_status": None
        }
def collect_snapshot():
    timestamp = datetime.now()
    timestamp_text = timestamp.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    print()
    print(
        "=" * 60
    )
    print(
        "COLLECTING:",
        timestamp_text
    )
    print(
        "=" * 60
    )
    rows = []
    for position, (_, road) in enumerate(
        mapping.iterrows(),
        start=1
    ):
        location = road[
            "traffic_location"
        ]
        latitude = float(
            road["latitude"]
        )

        longitude = float(
            road["longitude"]
        )
        print(
            f"[{position}/{len(mapping)}] "
            f"{location}",
            end=" ... "
        )
        traffic = get_live_traffic(
            latitude,
            longitude
        )
        if traffic["status"] == "OK":
            print(
                f"{traffic['current_speed']} km/h"
            )
        else:
            print(
                f"ERROR "
                f"HTTP={traffic['http_status']}"
            )
        current_time = (
            traffic[
                "current_travel_time"
            ]
        )
        free_time = (
            traffic[
                "free_flow_travel_time"
            ]
        )
        if (
            current_time is not None
            and free_time is not None
        ):
            delay_seconds = (
                current_time
                - free_time
            )

            if free_time > 0:

                delay_percent = (
                    delay_seconds
                    / free_time
                ) * 100
            else:
                delay_percent = 0
        else:
            delay_seconds = None
            delay_percent = None
        rows.append({
            "timestamp":
                timestamp_text,
            "traffic_location":
                location,
            "latitude":
                latitude,
            "longitude":
                longitude,
            "nearest_node":
                road["nearest_node"],
            "current_speed_kmh":
                traffic[
                    "current_speed"
                ],
            "free_flow_speed_kmh":
                traffic[
                    "free_flow_speed"
                ],
            "current_travel_time_sec":
                current_time,
            "free_flow_travel_time_sec":
                free_time,
            "delay_sec":
                delay_seconds,
            "delay_percent":
                delay_percent,
            "confidence":
                traffic[
                    "confidence"
                ],
            "road_closure":
                traffic[
                    "road_closure"
                ],
            "status":
                traffic[
                    "status"
                ],
            "http_status":
                traffic[
                    "http_status"
                ]
        })
    return pd.DataFrame(rows)
def save_snapshot(
    snapshot
):
    file_exists = os.path.exists(
        OUTPUT_FILE
    )
    snapshot.to_csv(
        OUTPUT_FILE,
        mode="a",
        header=not file_exists,
        index=False
    )
print()
print(
    "Starting continuous collection..."
)
print(
    "Press Ctrl+C to stop."
)
print()
if _args.once:
    print("Running in --once mode (single snapshot, for cron/Task Scheduler).")
try:
    while True:
        snapshot = collect_snapshot()
        save_snapshot(
            snapshot
        )
        successful = (
            snapshot["status"]
            == "OK"
        ).sum()
        print()
        print(
            "Snapshot saved."
        )
        print(
            "Successful:",
            successful,
            "/",
            len(snapshot)
        )
        print(
            "Total rows stored:",
            len(
                pd.read_csv(
                    OUTPUT_FILE
                )
            )
        )
        if _args.once:
            break
        print()
        print(
            f"Waiting "
            f"{INTERVAL_SECONDS // 60} "
            f"minutes..."
        )
        time.sleep(
            INTERVAL_SECONDS
        )
except KeyboardInterrupt:
    print()
    print("=" * 60)
    print("COLLECTOR STOPPED")
    print("=" * 60)

    if os.path.exists(
        OUTPUT_FILE
    ):
        df = pd.read_csv(
            OUTPUT_FILE
        )
        print(
            "Total observations:",
            len(df)
        )
        print(
            "Total snapshots:",
            df["timestamp"].nunique()
        )
        print(
            "Saved to:",
            os.path.abspath(
                OUTPUT_FILE
            )
        )
















