import pandas as pd
import numpy as np


# ============================================================
# PATHS
# ============================================================

INPUT_FILE = r"D:\major project\traffic_module\data\traffic_forecast_dataset.csv"

OUTPUT_FILE = r"D:\major project\traffic_module\data\traffic_sequence_dataset.csv"


# ============================================================
# SETTINGS
# ============================================================

HISTORY_DAYS = 7


# ============================================================
# LOAD DATA
# ============================================================

print("Loading forecasting dataset...")

df = pd.read_csv(INPUT_FILE)

df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)

df["target_date"] = pd.to_datetime(
    df["target_date"],
    errors="coerce"
)

print("Rows:", len(df))


# ============================================================
# SORT
# ============================================================

df = df.sort_values(
    [
        "Road/Intersection Name",
        "Date"
    ]
).reset_index(drop=True)


# ============================================================
# FEATURES
# ============================================================

FEATURES = [
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
]


# ============================================================
# NUMERIC CONVERSION
# ============================================================

for column in FEATURES:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


df["target_speed_next_day"] = pd.to_numeric(
    df["target_speed_next_day"],
    errors="coerce"
)


# ============================================================
# CREATE SEQUENCES
# ============================================================

print(
    "\nCreating 7-day historical sequences..."
)


rows = []


for location, group in df.groupby(
    "Road/Intersection Name"
):

    group = group.sort_values(
        "Date"
    ).reset_index(drop=True)


    for i in range(
        HISTORY_DAYS,
        len(group)
    ):

        history = group.iloc[
            i - HISTORY_DAYS:i
        ]

        current = group.iloc[i]


        # ----------------------------------------------------
        # Make sure the 7 historical observations are
        # actually consecutive calendar days.
        # ----------------------------------------------------

        date_differences = (
            history["Date"]
            .diff()
            .dt.days
            .dropna()
        )

        if not all(
            date_differences == 1
        ):
            continue


        # ----------------------------------------------------
        # Target is the next day after current observation.
        # ----------------------------------------------------

        if pd.isna(
            current["target_speed_next_day"]
        ):
            continue


        # ----------------------------------------------------
        # Build one sequence row.
        # ----------------------------------------------------

        row = {

            "Road/Intersection Name":
                location,

            "Date":
                current["Date"],

            "target_date":
                current["target_date"],

            "target_speed_next_day":
                current["target_speed_next_day"],

        }


        # ----------------------------------------------------
        # Store each of the previous 7 days.
        # ----------------------------------------------------

        for day in range(
            HISTORY_DAYS
        ):

            historical_row = history.iloc[day]

            suffix = f"_d{day + 1}"


            for feature in FEATURES:

                row[
                    feature + suffix
                ] = historical_row[feature]


        rows.append(row)


# ============================================================
# DATAFRAME
# ============================================================

sequence_df = pd.DataFrame(
    rows
)


# ============================================================
# SORT
# ============================================================

if len(sequence_df) > 0:

    sequence_df = sequence_df.sort_values(
        "Date"
    ).reset_index(
        drop=True
    )


# ============================================================
# INFORMATION
# ============================================================

print(
    "\n========================================"
)

print(
    "SEQUENCE DATASET"
)

print(
    "========================================"
)

print(
    "Rows:",
    len(sequence_df)
)

print(
    "Locations:",
    sequence_df[
        "Road/Intersection Name"
    ].nunique()
)

print(
    "Input date:",
    sequence_df["Date"].min()
)

print(
    "Target date:",
    sequence_df["target_date"].min(),
    "to",
    sequence_df["target_date"].max()
)


# ============================================================
# YEAR DISTRIBUTION
# ============================================================

print(
    "\nYears:"
)

print(
    sequence_df[
        "Date"
    ]
    .dt.year
    .value_counts()
    .sort_index()
)


# ============================================================
# EXAMPLE
# ============================================================

print(
    "\nExample sequence:"
)

example_columns = [
    "Date",
    "Road/Intersection Name",
    "Average Speed_d1",
    "Average Speed_d2",
    "Average Speed_d3",
    "Average Speed_d4",
    "Average Speed_d5",
    "Average Speed_d6",
    "Average Speed_d7",
    "target_date",
    "target_speed_next_day",
]


print(
    sequence_df[
        example_columns
    ]
    .head(10)
    .to_string(index=False)
)


# ============================================================
# SAVE
# ============================================================

sequence_df.to_csv(
    OUTPUT_FILE,
    index=False
)


print(
    "\nSaved to:"
)

print(
    OUTPUT_FILE
)