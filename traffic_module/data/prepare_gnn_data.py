

import pandas as pd
import numpy as np

INPUT_FILE = "traffic_gnn_dataset.csv"
OUTPUT_FILE = "gnn_training_data.csv"

print("Loading dataset...")
df = pd.read_csv(INPUT_FILE)

print("Original rows:", len(df))

# --------------------------------------------------
# TARGET
# --------------------------------------------------

df["target_speed"] = pd.to_numeric(
    df["target_speed"],
    errors="coerce"
)

# --------------------------------------------------
# NUMERIC FEATURES
# IMPORTANT:
# Average Speed is intentionally NOT included.
# It is the target we are predicting.
# --------------------------------------------------

numeric_features = [
    "Traffic Volume",
    "Travel Time Index",
    "Congestion Level",
    "Road Capacity Utilization",
    "Incident Reports",
    "Environmental Impact",
    "Public Transport Usage",
    "Traffic Signal Compliance",
    "Parking Usage",
    "Pedestrian and Cyclist Count",
    "road_length_m",
    "node_degree",
]

# --------------------------------------------------
# CATEGORICAL FEATURES
# --------------------------------------------------

categorical_features = [
    "Weather Conditions",
    "Roadwork and Construction Activity",
    "road_type",
]

# --------------------------------------------------
# CONVERT NUMERIC FEATURES
# --------------------------------------------------

for column in numeric_features:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )

# --------------------------------------------------
# HANDLE MISSING OSM ATTRIBUTES
# --------------------------------------------------

# Missing lanes/maxspeed are common in OSM.
# We do NOT invent values.
# We simply create explicit missing indicators.

df["lanes_missing"] = df["lanes"].isna().astype(int)
df["maxspeed_missing"] = df["maxspeed"].isna().astype(int)

df["lanes"] = pd.to_numeric(
    df["lanes"],
    errors="coerce"
)

df["maxspeed"] = pd.to_numeric(
    df["maxspeed"],
    errors="coerce"
)

# Fill missing numeric OSM attributes using
# dataset medians rather than fabricated values.

df["lanes"] = df["lanes"].fillna(
    df["lanes"].median()
)

df["maxspeed"] = df["maxspeed"].fillna(
    df["maxspeed"].median()
)

numeric_features += [
    "lanes",
    "maxspeed",
    "lanes_missing",
    "maxspeed_missing",
]

# --------------------------------------------------
# ENCODE CATEGORICAL FEATURES
# --------------------------------------------------

for column in categorical_features:

    df[column] = (
        df[column]
        .fillna("Unknown")
        .astype(str)
    )

encoded = pd.get_dummies(
    df[categorical_features],
    prefix=categorical_features,
    dtype=int
)

# --------------------------------------------------
# BUILD FINAL FEATURE DATASET
# --------------------------------------------------

features = df[numeric_features].copy()

features = pd.concat(
    [features, encoded],
    axis=1
)

# Target
features["target_speed"] = df["target_speed"]

# Remove rows where target is unavailable
features = features.dropna(
    subset=["target_speed"]
)

# --------------------------------------------------
# SAVE
# --------------------------------------------------

features.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n===================================")
print("GNN TRAINING DATA CREATED")
print("===================================")

print("Rows:", len(features))
print("Features:", len(features.columns) - 1)
print("Target: target_speed")

print("\nInput features:")
for column in features.columns:
    if column != "target_speed":
        print("-", column)

print("\nTarget statistics:")
print(
    features["target_speed"].describe()
)

print("\nSaved to:")
print(OUTPUT_FILE)