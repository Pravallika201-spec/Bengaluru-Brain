import os
import math
import pandas as pd
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_production_waste_predictions.csv"
)

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_dynamic_satellite_routes.csv"
)

NUMBER_OF_TRUCKS = 50

# Maximum number of collection grids assigned to each truck.
# This keeps routes manageable.
MAX_GRIDS_PER_TRUCK = 10

# Only HIGH and CRITICAL grids are collected in this
# first dynamic-routing stage.
TARGET_RISKS = [
    "CRITICAL",
    "HIGH"
]


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c


# ============================================================
# LOAD PREDICTIONS
# ============================================================

def load_predictions():

    print(
        "\nLoading satellite predictions..."
    )

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"\nInput file not found:\n"
            f"{INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Total prediction grids:",
        len(df)
    )

    required = [
        "Grid_ID",
        "Latitude",
        "Longitude",
        "predicted_daily_waste_kg",
        "waste_risk",
        "collection_priority"
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:

        raise ValueError(
            f"Missing required columns: {missing}"
        )

    return df


# ============================================================
# SELECT COLLECTION GRIDS
# ============================================================

def select_collection_grids(
    df
):

    print(
        "\nSelecting collection grids..."
    )

    selected = df[
        df["waste_risk"].isin(
            TARGET_RISKS
        )
    ].copy()

    selected = selected.sort_values(
        by=[
            "waste_risk",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False
        ]
    )

    # Critical first.
    selected["_risk_order"] = (
        selected["waste_risk"]
        .map(
            {
                "CRITICAL": 1,
                "HIGH": 2
            }
        )
    )

    selected = selected.sort_values(
        by=[
            "_risk_order",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False
        ]
    )

    selected = selected.drop(
        columns=["_risk_order"]
    )

    print(
        "Selected grids:",
        len(selected)
    )

    print(
        "\nSelected risk distribution:"
    )

    print(
        selected[
            "waste_risk"
        ].value_counts()
    )

    return selected.reset_index(
        drop=True
    )


# ============================================================
# CREATE TRUCK LIST
# ============================================================

def create_trucks():

    return [
        f"TRUCK_{i:02d}"
        for i in range(
            1,
            NUMBER_OF_TRUCKS + 1
        )
    ]


# ============================================================
# ASSIGN GRIDS TO TRUCKS
# ============================================================

def assign_trucks(
    df
):

    print(
        "\nAssigning collection grids "
        "to trucks..."
    )

    trucks = create_trucks()

    df = df.copy()

    df[
        "truck_id"
    ] = None

    # Greedy load balancing.
    #
    # The largest waste grids are assigned
    # to the currently least-loaded truck.

    truck_load = {
        truck: 0.0
        for truck in trucks
    }

    truck_count = {
        truck: 0
        for truck in trucks
    }

    for idx, row in df.iterrows():

        eligible = [
            truck
            for truck in trucks
            if truck_count[truck]
            < MAX_GRIDS_PER_TRUCK
        ]

        if not eligible:

            eligible = trucks

        selected_truck = min(
            eligible,
            key=lambda t: truck_load[t]
        )

        df.loc[
            idx,
            "truck_id"
        ] = selected_truck

        truck_load[
            selected_truck
        ] += float(
            row[
                "predicted_daily_waste_kg"
            ]
        )

        truck_count[
            selected_truck
        ] += 1

    print(
        "Trucks used:",
        df["truck_id"].nunique()
    )

    return df


# ============================================================
# BUILD ROUTE FOR EACH TRUCK
# ============================================================

def build_truck_routes(
    df
):

    print(
        "\nBuilding truck routes..."
    )

    route_records = []

    for truck_id, group in df.groupby(
        "truck_id"
    ):

        group = group.copy()

        # Start with highest predicted waste.
        remaining = group.copy()

        route_sequence = 1

        previous_lat = None
        previous_lon = None

        total_distance = 0.0
        total_waste = 0.0

        while len(remaining) > 0:

            if previous_lat is None:

                # First location:
                # choose highest predicted waste.

                idx = remaining[
                    "predicted_daily_waste_kg"
                ].idxmax()

            else:

                # Nearest-neighbour selection
                # from current location.

                distances = []

                for idx2, candidate in remaining.iterrows():

                    distance = haversine_km(
                        previous_lat,
                        previous_lon,
                        candidate["Latitude"],
                        candidate["Longitude"]
                    )

                    distances.append(
                        (
                            idx2,
                            distance
                        )
                    )

                # Select nearest location.

                idx = min(
                    distances,
                    key=lambda x: x[1]
                )[0]

            row = remaining.loc[
                idx
            ]

            lat = float(
                row["Latitude"]
            )

            lon = float(
                row["Longitude"]
            )

            if previous_lat is None:

                distance = 0.0

            else:

                distance = haversine_km(
                    previous_lat,
                    previous_lon,
                    lat,
                    lon
                )

            waste = float(
                row[
                    "predicted_daily_waste_kg"
                ]
            )

            total_distance += distance
            total_waste += waste

            route_records.append(
                {
                    "Grid_ID":
                        row["Grid_ID"],

                    "truck_id":
                        truck_id,

                    "route_sequence":
                        route_sequence,

                    "Latitude":
                        lat,

                    "Longitude":
                        lon,

                    "predicted_daily_waste_kg":
                        waste,

                    "waste_risk":
                        row["waste_risk"],

                    "collection_priority":
                        row[
                            "collection_priority"
                        ],

                    "distance_from_previous_km":
                        round(
                            distance,
                            3
                        )
                }
            )

            previous_lat = lat
            previous_lon = lon

            remaining = remaining.drop(
                idx
            )

            route_sequence += 1

        # Add route statistics.

        for record in route_records:

            if (
                record["truck_id"]
                == truck_id
            ):

                record[
                    "route_total_distance_km"
                ] = round(
                    total_distance,
                    3
                )

                record[
                    "route_total_waste_kg"
                ] = round(
                    total_waste,
                    2
                )

                record[
                    "route_grid_count"
                ] = route_sequence - 1

    return pd.DataFrame(
        route_records
    )


# ============================================================
# SAVE ROUTES
# ============================================================

def save_routes(
    routes
):

    print(
        "\nSaving dynamic routes..."
    )

    os.makedirs(
        os.path.dirname(
            OUTPUT_FILE
        ),
        exist_ok=True
    )

    routes.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nOutput saved:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# SUMMARY
# ============================================================

def display_summary(
    routes
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "DYNAMIC SATELLITE ROUTING SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        "\nCollection grids:",
        routes["Grid_ID"].nunique()
    )

    print(
        "Trucks:",
        routes["truck_id"].nunique()
    )

    print(
        "Total predicted waste:",
        round(
            routes[
                "predicted_daily_waste_kg"
            ].sum(),
            2
        ),
        "kg/day"
    )

    print(
        "\nRisk distribution:"
    )

    print(
        routes[
            "waste_risk"
        ].value_counts()
    )

    print(
        "\nTruck summary:"
    )

    truck_summary = (
        routes.groupby(
            "truck_id"
        )
        .agg(
            grids=(
                "Grid_ID",
                "count"
            ),
            waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),
            distance_km=(
                "route_total_distance_km",
                "first"
            )
        )
        .sort_values(
            "waste_kg",
            ascending=False
        )
    )

    print(
        truck_summary.head(
            10
        ).to_string()
    )

    print(
        "\nTop collection locations:"
    )

    top = routes.sort_values(
        "predicted_daily_waste_kg",
        ascending=False
    ).head(10)

    print(
        top[
            [
                "Grid_ID",
                "predicted_daily_waste_kg",
                "waste_risk",
                "truck_id",
                "route_sequence"
            ]
        ].to_string(
            index=False
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU DYNAMIC "
        "SATELLITE WASTE ROUTE OPTIMIZER"
    )

    print("=" * 60)

    # 1. Load predictions

    df = load_predictions()

    # 2. Select important grids

    selected = select_collection_grids(
        df
    )

    # 3. Assign trucks

    assigned = assign_trucks(
        selected
    )

    # 4. Generate routes

    routes = build_truck_routes(
        assigned
    )

    # 5. Save

    save_routes(
        routes
    )

    # 6. Summary

    display_summary(
        routes
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "DYNAMIC SATELLITE ROUTING COMPLETED"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()