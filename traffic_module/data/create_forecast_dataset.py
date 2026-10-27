import pandas as pd


# ============================================================
# PATHS
# ============================================================

INPUT_FILE = r"C:\Users\ravip\OneDrive\Desktop\Banglore_traffic_Dataset.csv"

GNN_DATASET_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

OUTPUT_FILE = r"D:\major project\traffic_module\data\traffic_forecast_dataset.csv"


# ============================================================
# LOAD ORIGINAL TRAFFIC DATA
# ============================================================

print("Loading original traffic dataset...")

df = pd.read_csv(INPUT_FILE)

print("Original rows:", len(df))


# ============================================================
# LOAD EXISTING GNN ROAD FEATURES
# ============================================================

print("\nLoading road/OSM features...")

gnn_df = pd.read_csv(
    GNN_DATASET_FILE,
    usecols=[
        "Road/Intersection Name",
        "osm_node",
        "road_length_m",
        "node_degree"
    ]
)


# One road/location → one OSM mapping
gnn_df = gnn_df.drop_duplicates(
    "Road/Intersection Name"
)


# ============================================================
# MERGE ROAD FEATURES
# ============================================================

df = df.merge(
    gnn_df,
    on="Road/Intersection Name",
    how="inner"
)


print(
    "Rows after OSM mapping:",
    len(df)
)


# ============================================================
# DATE
# ============================================================

df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)


# ============================================================
# NUMERIC SPEED
# ============================================================

df["Average Speed"] = pd.to_numeric(
    df["Average Speed"],
    errors="coerce"
)


# ============================================================
# REMOVE INVALID ROWS
# ============================================================

df = df.dropna(
    subset=[
        "Date",
        "Road/Intersection Name",
        "Average Speed",
        "osm_node"
    ]
).copy()


# ============================================================
# SORT BY LOCATION + DATE
# ============================================================

df = df.sort_values(
    [
        "Road/Intersection Name",
        "Date"
    ]
).reset_index(
    drop=True
)


# ============================================================
# CREATE NEXT-DAY TARGET
# ============================================================

print(
    "\nCreating next-day speed target..."
)


df["target_speed_next_day"] = (

    df.groupby(
        "Road/Intersection Name"
    )["Average Speed"]

    .shift(-1)

)


df["target_date"] = (

    df.groupby(
        "Road/Intersection Name"
    )["Date"]

    .shift(-1)

)


# ============================================================
# CHECK DATE DIFFERENCE
# ============================================================

df["days_ahead"] = (

    df["target_date"]
    - df["Date"]

).dt.days


# Only keep genuine next-day observations
df = df[
    df["days_ahead"] == 1
].copy()


# ============================================================
# REMOVE MISSING TARGETS
# ============================================================

df = df.dropna(
    subset=[
        "target_speed_next_day"
    ]
).copy()


# ============================================================
# CALENDAR FEATURES
# ============================================================

df["day_of_week"] = (

    df["Date"]
    .dt.dayofweek
    .astype(float)

)


df["is_weekend"] = (

    df["day_of_week"] >= 5

).astype(float)


df["month"] = (

    df["Date"]
    .dt.month
    .astype(float)

)


# ============================================================
# RESET INDEX
# ============================================================

df = df.reset_index(
    drop=True
)


# ============================================================
# FINAL INFORMATION
# ============================================================

print(
    "\n========================================"
)

print(
    "FORECAST DATASET CREATED"
)

print(
    "========================================"
)

print(
    "Rows:",
    len(df)
)

print(
    "Locations:",
    df["Road/Intersection Name"].nunique()
)

print(
    "Input date:",
    df["Date"].min()
)

print(
    "Target date:",
    df["target_date"].min(),
    "to",
    df["target_date"].max()
)


# ============================================================
# CHECK REQUIRED FEATURES
# ============================================================

required_columns = [

    "Traffic Volume",
    "Average Speed",
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
    "day_of_week",
    "is_weekend",
    "month",
    "target_speed_next_day"

]


print(
    "\nRequired columns check:"
)


for column in required_columns:

    if column in df.columns:

        print(
            "OK  -",
            column
        )

    else:

        print(
            "MISSING -",
            column
        )


# ============================================================
# SHOW EXAMPLES
# ============================================================

print(
    "\nExample forecasts:"
)

print(

    df[
        [
            "Date",
            "Road/Intersection Name",
            "Average Speed",
            "road_length_m",
            "node_degree",
            "target_date",
            "target_speed_next_day"
        ]
    ]

    .head(20)

    .to_string(
        index=False
    )

)


# ============================================================
# SAVE
# ============================================================

df.to_csv(
    OUTPUT_FILE,
    index=False
)


print(
    "\nSaved to:"
)

print(
    OUTPUT_FILE
)