import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

TRAFFIC_FILE = r"D:\major project\bengaluru_traffic_segments.csv"


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("BENGALURU TRAFFIC COVERAGE ANALYSIS")
print("=" * 70)


# ============================================================
# LOAD DATA
# ============================================================

print()
print("Loading traffic data...")

df = pd.read_csv(TRAFFIC_FILE)

print("Rows:", len(df))


# ============================================================
# BASIC COVERAGE
# ============================================================

print()
print("=" * 70)
print("BASIC COVERAGE")
print("=" * 70)

print()
print("Unique edges:",
      df[["osm_u", "osm_v", "osm_key"]]
      .drop_duplicates()
      .shape[0])

print(
    "Unique road names:",
    df["road_name"].dropna().nunique()
)

print(
    "Unique highway types:",
    df["highway"].dropna().nunique()
)

print(
    "Unique locations:",
    df["latitude"].dropna().nunique()
)


# ============================================================
# SUCCESS / ERROR
# ============================================================

print()
print("=" * 70)
print("API STATUS")
print("=" * 70)

print()

print(
    df["status"]
    .value_counts(dropna=False)
)


# ============================================================
# TRAFFIC STATISTICS
# ============================================================

print()
print("=" * 70)
print("TRAFFIC STATISTICS")
print("=" * 70)

print()

for column in [
    "current_speed_kmh",
    "free_flow_speed_kmh",
    "speed_ratio",
    "delay_percent",
    "confidence"
]:

    if column in df.columns:

        values = pd.to_numeric(
            df[column],
            errors="coerce"
        )

        print()
        print(column)

        print(
            "  Min:",
            values.min()
        )

        print(
            "  Average:",
            values.mean()
        )

        print(
            "  Max:",
            values.max()
        )


# ============================================================
# ROAD TYPE DISTRIBUTION
# ============================================================

print()
print("=" * 70)
print("HIGHWAY TYPE DISTRIBUTION")
print("=" * 70)

print()

if "highway" in df.columns:

    print(
        df["highway"]
        .fillna("Unknown")
        .value_counts()
        .head(20)
    )


# ============================================================
# MOST CONGESTED ROADS
# ============================================================

print()
print("=" * 70)
print("MOST CONGESTED OBSERVATIONS")
print("=" * 70)

print()

congestion = df.copy()

congestion["delay_percent"] = pd.to_numeric(
    congestion["delay_percent"],
    errors="coerce"
)

congestion = congestion.sort_values(
    "delay_percent",
    ascending=False
)


columns_to_show = [
    "road_name",
    "highway",
    "current_speed_kmh",
    "free_flow_speed_kmh",
    "speed_ratio",
    "delay_percent",
    "confidence"
]

columns_to_show = [
    c for c in columns_to_show
    if c in congestion.columns
]

print(
    congestion[
        columns_to_show
    ].head(20).to_string(index=False)
)


# ============================================================
# TRAFFIC LEVEL CLASSIFICATION
# ============================================================

print()
print("=" * 70)
print("TRAFFIC LEVEL DISTRIBUTION")
print("=" * 70)


def classify_traffic(delay):

    if pd.isna(delay):
        return "UNKNOWN"

    if delay <= 5:
        return "FREE FLOW"

    elif delay <= 20:
        return "MODERATE"

    elif delay <= 50:
        return "HEAVY"

    else:
        return "CRITICAL"


df["traffic_level"] = (
    df["delay_percent"]
    .apply(classify_traffic)
)


print()

print(
    df["traffic_level"]
    .value_counts()
)


# ============================================================
# CLOSURES
# ============================================================

print()
print("=" * 70)
print("ROAD CLOSURES")
print("=" * 70)

print()

if "road_closure" in df.columns:

    closure = (
        df["road_closure"]
        .astype(str)
        .str.lower()
        .isin([
            "true",
            "1",
            "yes"
        ])
    )

    print(
        "Closed observations:",
        closure.sum()
    )

else:

    print(
        "road_closure column not found."
    )


# ============================================================
# SAVE ANALYSIS DATA
# ============================================================

OUTPUT_FILE = (
    r"D:\major project"
    r"\traffic_coverage_analysis.csv"
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 70)
print("TRAFFIC COVERAGE ANALYSIS COMPLETE")
print("=" * 70)

print()
print(
    "Analysis saved to:"
)

print(
    OUTPUT_FILE
)