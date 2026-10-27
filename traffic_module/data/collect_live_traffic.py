import os
import time
import requests
import pandas as pd
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_location_mapping.csv"

OUTPUT_FILE = r"D:\major project\traffic_module\data\live_traffic_data.csv"

TOMTOM_URL = (
    "https://api.tomtom.com/"
    "traffic/services/4/flowSegmentData/"
    "absolute/10/json"
)

API_KEY = os.environ.get("TOMTOM_API_KEY")


# ============================================================
# CHECK API KEY
# ============================================================

if not API_KEY:

    print("=" * 60)
    print("ERROR: TOMTOM_API_KEY is not set.")
    print("=" * 60)

    print()
    print("Run this first:")
    print()
    print('$env:TOMTOM_API_KEY="YOUR_TOMTOM_KEY"')
    print()

    raise SystemExit(1)


# ============================================================
# LOAD LOCATION MAPPING
# ============================================================

print()
print("=" * 60)
print("LOADING BENGALURU ROAD MAPPING")
print("=" * 60)

mapping = pd.read_csv(MAPPING_FILE)

print("Total locations:", len(mapping))


# Only use successfully matched locations.

mapping = mapping[
    mapping["status"].astype(str).str.upper() == "MATCHED"
].copy()

print("Matched locations:", len(mapping))


# Remove rows without coordinates.

mapping = mapping.dropna(
    subset=["latitude", "longitude"]
).copy()

print("Locations with coordinates:", len(mapping))


# ============================================================
# TOMTOM REQUEST FUNCTION
# ============================================================

def get_live_traffic(latitude, longitude):

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
                "http_status": response.status_code,
                "current_speed": None,
                "free_flow_speed": None,
                "current_travel_time": None,
                "free_flow_travel_time": None,
                "confidence": None,
                "road_closure": None
            }

        data = response.json()

        flow = data.get(
            "flowSegmentData",
            {}
        )

        return {
            "status": "OK",
            "http_status": response.status_code,
            "current_speed": flow.get("currentSpeed"),
            "free_flow_speed": flow.get("freeFlowSpeed"),
            "current_travel_time": flow.get("currentTravelTime"),
            "free_flow_travel_time": flow.get("freeFlowTravelTime"),
            "confidence": flow.get("confidence"),
            "road_closure": flow.get("roadClosure")
        }

    except Exception as e:

        return {
            "status": "ERROR",
            "http_status": None,
            "current_speed": None,
            "free_flow_speed": None,
            "current_travel_time": None,
            "free_flow_travel_time": None,
            "confidence": None,
            "road_closure": None
        }


# ============================================================
# COLLECT LIVE DATA
# ============================================================

print()
print("=" * 60)
print("COLLECTING LIVE BENGALURU TRAFFIC")
print("=" * 60)

results = []

timestamp = datetime.now().strftime(
    "%Y-%m-%d %H:%M:%S"
)

for index, row in mapping.iterrows():

    location = row["traffic_location"]

    latitude = float(
        row["latitude"]
    )

    longitude = float(
        row["longitude"]
    )

    print()
    print(
        f"[{len(results) + 1}/{len(mapping)}] "
        f"{location}"
    )

    print(
        f"Coordinates: "
        f"{latitude:.6f}, "
        f"{longitude:.6f}"
    )

    traffic = get_live_traffic(
        latitude,
        longitude
    )

    print(
        "Status:",
        traffic["status"]
    )

    if traffic["status"] == "OK":

        print(
            "Current speed:",
            traffic["current_speed"],
            "km/h"
        )

        print(
            "Free-flow speed:",
            traffic["free_flow_speed"],
            "km/h"
        )

        print(
            "Current travel time:",
            traffic["current_travel_time"],
            "seconds"
        )

        print(
            "Free-flow travel time:",
            traffic["free_flow_travel_time"],
            "seconds"
        )

        print(
            "Confidence:",
            traffic["confidence"]
        )

        print(
            "Road closure:",
            traffic["road_closure"]
        )

    results.append({

        "timestamp": timestamp,

        "traffic_location": location,

        "latitude": latitude,

        "longitude": longitude,

        "nearest_node": row["nearest_node"],

        "distance_m": row["distance_m"],

        "current_speed_kmh":
            traffic["current_speed"],

        "free_flow_speed_kmh":
            traffic["free_flow_speed"],

        "current_travel_time_sec":
            traffic["current_travel_time"],

        "free_flow_travel_time_sec":
            traffic["free_flow_travel_time"],

        "confidence":
            traffic["confidence"],

        "road_closure":
            traffic["road_closure"],

        "status":
            traffic["status"],

        "http_status":
            traffic["http_status"]
    })

    # Small delay between requests.

    time.sleep(0.2)


# ============================================================
# CREATE DATAFRAME
# ============================================================

live_df = pd.DataFrame(results)


# ============================================================
# CALCULATE DELAY
# ============================================================

live_df["delay_sec"] = (
    live_df["current_travel_time_sec"]
    -
    live_df["free_flow_travel_time_sec"]
)


live_df["delay_percent"] = 0.0

valid = (
    live_df["free_flow_travel_time_sec"].notna()
    &
    (live_df["free_flow_travel_time_sec"] > 0)
)


live_df.loc[valid, "delay_percent"] = (

    (
        live_df.loc[
            valid,
            "current_travel_time_sec"
        ]
        -
        live_df.loc[
            valid,
            "free_flow_travel_time_sec"
        ]
    )

    /

    live_df.loc[
        valid,
        "free_flow_travel_time_sec"
    ]

) * 100


# ============================================================
# SAVE
# ============================================================

live_df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("LIVE TRAFFIC COLLECTION COMPLETE")
print("=" * 60)

print(
    "Successful:",
    (live_df["status"] == "OK").sum()
)

print(
    "Failed:",
    (live_df["status"] != "OK").sum()
)

print()
print("Saved to:")
print(
    os.path.abspath(OUTPUT_FILE)
)


print()
print("=" * 60)
print("LIVE TRAFFIC SUMMARY")
print("=" * 60)

columns = [
    "traffic_location",
    "current_speed_kmh",
    "free_flow_speed_kmh",
    "delay_sec",
    "delay_percent",
    "confidence",
    "road_closure"
]

print(
    live_df[columns].to_string(
        index=False
    )
)
