import pandas as pd
import numpy as np


INPUT_FILE = "live_traffic_history.csv"
OUTPUT_FILE = "realtime_prediction_dataset.csv"


print("=" * 60)
print("PREPARING REAL-TIME TRAFFIC DATASET")
print("=" * 60)


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_FILE)

print("Original rows:", len(df))


# ============================================================
# DATETIME
# ============================================================

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    errors="coerce"
)


# ============================================================
# REMOVE API FAILURES
# ============================================================

valid_status = (
    df["status"]
    .astype(str)
    .str.upper()
    == "OK"
)

valid_speed = (
    pd.to_numeric(
        df["current_speed_kmh"],
        errors="coerce"
    ).notna()
)

valid_free_flow = (
    pd.to_numeric(
        df["free_flow_speed_kmh"],
        errors="coerce"
    ).notna()
)

clean = df[
    valid_status
    & valid_speed
    & valid_free_flow
].copy()


print(
    "Valid rows:",
    len(clean)
)

print(
    "Removed rows:",
    len(df) - len(clean)
)


# ============================================================
# NUMERIC CONVERSION
# ============================================================

numeric_columns = [
    "current_speed_kmh",
    "free_flow_speed_kmh",
    "current_travel_time_sec",
    "free_flow_travel_time_sec",
    "delay_sec",
    "delay_percent",
    "confidence"
]


for column in numeric_columns:

    if column in clean.columns:

        clean[column] = pd.to_numeric(
            clean[column],
            errors="coerce"
        )


# ============================================================
# SORT CHRONOLOGICALLY
# ============================================================

clean = clean.sort_values(
    [
        "traffic_location",
        "timestamp"
    ]
).reset_index(
    drop=True
)


# ============================================================
# RECOMPUTE DELAY
# ============================================================

clean["delay_sec"] = (
    clean["current_travel_time_sec"]
    -
    clean["free_flow_travel_time_sec"]
)


valid_time = (
    clean["free_flow_travel_time_sec"]
    > 0
)


clean["delay_percent"] = np.nan


clean.loc[
    valid_time,
    "delay_percent"
] = (

    clean.loc[
        valid_time,
        "delay_sec"
    ]

    /

    clean.loc[
        valid_time,
        "free_flow_travel_time_sec"
    ]

) * 100


# ============================================================
# TIME FEATURES
# ============================================================

clean["hour"] = (
    clean["timestamp"].dt.hour
)

clean["minute"] = (
    clean["timestamp"].dt.minute
)

clean["day_of_week"] = (
    clean["timestamp"].dt.dayofweek
)

clean["is_weekend"] = (
    clean["day_of_week"] >= 5
).astype(int)


# Minutes since midnight

clean["minutes_since_midnight"] = (
    clean["hour"] * 60
    +
    clean["minute"]
)


# ============================================================
# CREATE NEXT OBSERVATION TARGET
# ============================================================

print()
print(
    "Creating next-observation target..."
)


clean["target_speed_next"] = (
    clean
    .groupby("traffic_location")
    ["current_speed_kmh"]
    .shift(-1)
)


clean["target_timestamp"] = (
    clean
    .groupby("traffic_location")
    ["timestamp"]
    .shift(-1)
)


# Calculate actual time gap

clean["time_gap_minutes"] = (

    clean["target_timestamp"]
    -
    clean["timestamp"]

).dt.total_seconds() / 60


# ============================================================
# KEEP REASONABLE TIME GAPS
# ============================================================

# Our collector normally runs every 5 minutes.
# Allow up to 15 minutes so temporary API failures
# don't destroy otherwise useful sequences.

clean = clean[
    clean["target_speed_next"].notna()
    &
    clean["target_timestamp"].notna()
    &
    (clean["time_gap_minutes"] <= 15)
].copy()


# ============================================================
# CREATE SPEED CHANGE
# ============================================================

clean["speed_change"] = (
    clean["target_speed_next"]
    -
    clean["current_speed_kmh"]
)


# ============================================================
# FINAL COLUMN ORDER
# ============================================================

output_columns = [

    "timestamp",
    "target_timestamp",

    "traffic_location",

    "latitude",
    "longitude",
    "nearest_node",

    "current_speed_kmh",
    "free_flow_speed_kmh",

    "current_travel_time_sec",
    "free_flow_travel_time_sec",

    "delay_sec",
    "delay_percent",

    "confidence",
    "road_closure",

    "hour",
    "minute",
    "day_of_week",
    "is_weekend",
    "minutes_since_midnight",

    "time_gap_minutes",

    "target_speed_next",
    "speed_change"
]


output_columns = [
    column
    for column in output_columns
    if column in clean.columns
]


result = clean[
    output_columns
].copy()


# ============================================================
# REMOVE DUPLICATES
# ============================================================

result = result.drop_duplicates(
    subset=[
        "timestamp",
        "traffic_location"
    ]
)


# ============================================================
# SAVE
# ============================================================

result.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("REAL-TIME DATASET CREATED")
print("=" * 60)

print(
    "Rows:",
    len(result)
)

print(
    "Locations:",
    result[
        "traffic_location"
    ].nunique()
)

print(
    "Input time:",
    result["timestamp"].min()
)

print(
    "Latest input time:",
    result["timestamp"].max()
)

print(
    "Target observations:",
    result["target_timestamp"].notna().sum()
)

print(
    "Missing values:",
    result.isna().sum().sum()
)

print()
print(
    "Time-gap distribution:"
)

print(
    result[
        "time_gap_minutes"
    ].describe()
)

print()
print(
    "Target speed statistics:"
)

print(
    result[
        "target_speed_next"
    ].describe()
)

print()
print(
    "Sample:"
)

print(
    result[
        [
            "timestamp",
            "target_timestamp",
            "traffic_location",
            "current_speed_kmh",
            "delay_percent",
            "target_speed_next"
        ]
    ]
    .head(20)
    .to_string(index=False)
)

print()
print(
    "Saved to:"
)

print(
    OUTPUT_FILE
)