import os
import pickle
import pandas as pd
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

LIVE_FILE = "live_traffic_history.csv"

MODEL_FILE = "realtime_traffic_baseline.pkl"

OUTPUT_FILE = "latest_traffic_predictions.csv"


# ============================================================
# LOAD LIVE DATA
# ============================================================

print("=" * 60)
print("LIVE TRAFFIC PREDICTION")
print("=" * 60)

if not os.path.exists(LIVE_FILE):
    print("ERROR: live traffic file not found.")
    raise SystemExit(1)


df = pd.read_csv(
    LIVE_FILE
)


# ============================================================
# LOAD MODEL
# ============================================================

if not os.path.exists(MODEL_FILE):
    print("ERROR: model file not found.")
    raise SystemExit(1)


with open(
    MODEL_FILE,
    "rb"
) as file:

    package = pickle.load(file)


model = package["model"]

feature_columns = package[
    "feature_columns"
]

location_codes = package[
    "location_codes"
]


# ============================================================
# DATETIME
# ============================================================

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    errors="coerce"
)


# ============================================================
# KEEP SUCCESSFUL API RESULTS
# ============================================================

df["current_speed_kmh"] = pd.to_numeric(
    df["current_speed_kmh"],
    errors="coerce"
)

df["free_flow_speed_kmh"] = pd.to_numeric(
    df["free_flow_speed_kmh"],
    errors="coerce"
)

df["current_travel_time_sec"] = pd.to_numeric(
    df["current_travel_time_sec"],
    errors="coerce"
)

df["free_flow_travel_time_sec"] = pd.to_numeric(
    df["free_flow_travel_time_sec"],
    errors="coerce"
)

df["delay_sec"] = pd.to_numeric(
    df["delay_sec"],
    errors="coerce"
)

df["delay_percent"] = pd.to_numeric(
    df["delay_percent"],
    errors="coerce"
)

df["confidence"] = pd.to_numeric(
    df["confidence"],
    errors="coerce"
)


df = df[
    (df["status"] == "OK")
    &
    df["current_speed_kmh"].notna()
].copy()


# ============================================================
# GET LATEST OBSERVATION FOR EACH LOCATION
# ============================================================

latest = (
    df.sort_values("timestamp")
      .groupby("traffic_location")
      .tail(1)
      .copy()
)


# ============================================================
# TIME FEATURES
# ============================================================

latest["hour"] = (
    latest["timestamp"].dt.hour
)

latest["minute"] = (
    latest["timestamp"].dt.minute
)

latest["day_of_week"] = (
    latest["timestamp"].dt.dayofweek
)

latest["is_weekend"] = (
    latest["day_of_week"] >= 5
).astype(int)

latest["minutes_since_midnight"] = (
    latest["hour"] * 60
    +
    latest["minute"]
)


# ============================================================
# LOCATION ENCODING
# ============================================================

latest["location_code"] = (
    latest["traffic_location"]
    .map(location_codes)
)


# ============================================================
# HANDLE UNKNOWN LOCATIONS
# ============================================================

latest["location_code"] = (
    latest["location_code"]
    .fillna(-1)
)


# ============================================================
# CHECK REQUIRED FEATURES
# ============================================================

missing_features = [
    column
    for column in feature_columns
    if column not in latest.columns
]


if missing_features:

    print(
        "Missing features:",
        missing_features
    )

    raise SystemExit(1)


# ============================================================
# REMOVE INCOMPLETE ROWS
# ============================================================

prediction_data = latest.dropna(
    subset=feature_columns
).copy()


# ============================================================
# RANDOM FOREST PREDICTION
# ============================================================

X = prediction_data[
    feature_columns
]


prediction_data[
    "predicted_speed_ml"
] = model.predict(X)


# ============================================================
# PERSISTENCE PREDICTION
# ============================================================

prediction_data[
    "predicted_speed_persistence"
] = prediction_data[
    "current_speed_kmh"
]


# ============================================================
# USE BETTER MODEL
# ============================================================

# Based on our current test:
#
# Persistence MAE = 1.375 km/h
# Random Forest MAE = 2.048 km/h
#
# Therefore persistence is currently the
# more accurate short-term predictor.

prediction_data[
    "predicted_next_speed_kmh"
] = prediction_data[
    "predicted_speed_persistence"
]


# ============================================================
# CALCULATE TRAFFIC STATUS
# ============================================================

def traffic_status(delay):

    if pd.isna(delay):
        return "UNKNOWN"

    if delay >= 60:
        return "CRITICAL"

    if delay >= 40:
        return "HEAVY"

    if delay >= 20:
        return "MODERATE"

    if delay > 0:
        return "LIGHT"

    return "FREE FLOW"


prediction_data[
    "traffic_status"
] = prediction_data[
    "delay_percent"
].apply(
    traffic_status
)


# ============================================================
# CONFIDENCE LEVEL
# ============================================================

def confidence_level(value):

    if pd.isna(value):
        return "UNKNOWN"

    if value >= 0.90:
        return "HIGH"

    if value >= 0.70:
        return "MEDIUM"

    return "LOW"


prediction_data[
    "confidence_level"
] = prediction_data[
    "confidence"
].apply(
    confidence_level
)


# ============================================================
# FINAL OUTPUT
# ============================================================

output_columns = [

    "timestamp",

    "traffic_location",

    "latitude",
    "longitude",

    "current_speed_kmh",

    "free_flow_speed_kmh",

    "delay_sec",

    "delay_percent",

    "traffic_status",

    "predicted_speed_ml",

    "predicted_next_speed_kmh",

    "confidence",

    "confidence_level",

    "road_closure"
]


output_columns = [
    column
    for column in output_columns
    if column in prediction_data.columns
]


result = prediction_data[
    output_columns
].sort_values(
    "traffic_location"
)


# ============================================================
# SAVE
# ============================================================

result.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# DISPLAY
# ============================================================

print()

print(
    "Prediction time:",
    datetime.now()
)

print(
    "Locations:",
    len(result)
)

print()

print(
    result[
        [
            "traffic_location",
            "current_speed_kmh",
            "predicted_next_speed_kmh",
            "delay_percent",
            "traffic_status",
            "confidence_level"
        ]
    ].to_string(
        index=False
    )
)


print()

print("=" * 60)

print(
    "LIVE PREDICTION COMPLETE"
)

print("=" * 60)

print(
    "Saved to:",
    OUTPUT_FILE
)