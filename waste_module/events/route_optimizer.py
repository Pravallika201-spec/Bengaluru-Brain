import os
import math
import pandas as pd
import numpy as np


# =========================================================
# PATHS
# =========================================================

OVERFLOW_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_overflow_risk_predictions.csv"
)

AREA_MAPPING_FILE = (
    "waste_module/data/processed/"
    "bengaluru_grid_area_mapping.csv"
)

OUTPUT_DIR = (
    "waste_module/data/processed"
)

OUTPUT_CSV = (
    "waste_module/data/processed/"
    "bengaluru_area_collection_routes.csv"
)


# =========================================================
# SETTINGS
# =========================================================

# Areas containing these risk levels are considered
# for collection routing.

ROUTING_RISK_LEVELS = [
    "CRITICAL",
    "HIGH"
]

# Maximum number of areas to include in the optimized
# collection route.
#
# This prevents a route containing every single area.
# Set to None if all HIGH + CRITICAL areas should be used.

MAX_ROUTE_AREAS = None


# =========================================================
# LOAD OVERFLOW PREDICTIONS
# =========================================================

def load_overflow_predictions():

    print("\nLoading overflow-risk predictions...")

    if not os.path.exists(OVERFLOW_FILE):

        raise FileNotFoundError(
            f"\nOverflow prediction file not found:\n"
            f"{OVERFLOW_FILE}"
        )

    df = pd.read_csv(
        OVERFLOW_FILE
    )

    print(
        "Overflow prediction rows:",
        len(df)
    )

    required_columns = [
        "Grid_ID",
        "Latitude",
        "Longitude",
        "predicted_daily_waste_kg",
        "overflow_risk_score",
        "overflow_risk",
        "overflow_collection_priority",
        "prediction_source",
        "prediction_confidence"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        print("\nMissing columns:")

        for column in missing:
            print(" -", column)

        raise ValueError(
            "Required overflow prediction columns are missing."
        )

    return df


# =========================================================
# LOAD GRID → AREA MAPPING
# =========================================================

def load_area_mapping():

    print("\nLoading grid-to-area mapping...")

    if not os.path.exists(AREA_MAPPING_FILE):

        raise FileNotFoundError(
            f"\nArea mapping file not found:\n"
            f"{AREA_MAPPING_FILE}"
        )

    df = pd.read_csv(
        AREA_MAPPING_FILE
    )

    print(
        "Mapping rows:",
        len(df)
    )

    required_columns = [
        "Grid_ID",
        "area_osm_id",
        "area_name",
        "area_admin_level"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        print("\nMissing area mapping columns:")

        for column in missing:
            print(" -", column)

        raise ValueError(
            "Required area mapping columns are missing."
        )

    return df[
        [
            "Grid_ID",
            "area_osm_id",
            "area_name",
            "area_admin_level"
        ]
    ].copy()


# =========================================================
# MERGE PREDICTIONS WITH AREA MAPPING
# =========================================================

def merge_predictions_with_areas(
    predictions,
    mapping
):

    print(
        "\nMapping grid predictions to Bengaluru areas..."
    )

    merged = predictions.merge(
        mapping,
        on="Grid_ID",
        how="left",
        validate="one_to_one"
    )

    unmatched = (
        merged["area_name"]
        .isna()
        .sum()
    )

    print(
        "Grids without area mapping:",
        unmatched
    )

    if unmatched > 0:

        raise ValueError(
            "Some grid predictions could not be mapped "
            "to an area."
        )

    print(
        "Mapped grids:",
        len(merged)
    )

    print(
        "Unique areas:",
        merged["area_name"].nunique()
    )

    return merged


# =========================================================
# AGGREGATE GRID PREDICTIONS TO AREA LEVEL
# =========================================================

def aggregate_to_areas(
    merged
):

    print(
        "\nAggregating waste predictions "
        "from grids to areas..."
    )

    # Make sure numeric fields are numeric.

    numeric_columns = [
        "Latitude",
        "Longitude",
        "predicted_daily_waste_kg",
        "overflow_risk_score",
        "overflow_collection_priority"
    ]

    for column in numeric_columns:

        merged[column] = pd.to_numeric(
            merged[column],
            errors="coerce"
        )

    # Remove rows without a valid prediction.

    merged = merged.dropna(
        subset=[
            "predicted_daily_waste_kg",
            "overflow_risk_score"
        ]
    )

    # -----------------------------------------------------
    # Area aggregation
    # -----------------------------------------------------

    area = (
        merged
        .groupby(
            [
                "area_osm_id",
                "area_name",
                "area_admin_level"
            ],
            as_index=False
        )
        .agg(
            Latitude=(
                "Latitude",
                "mean"
            ),

            Longitude=(
                "Longitude",
                "mean"
            ),

            predicted_daily_waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),

            average_grid_waste_kg=(
                "predicted_daily_waste_kg",
                "mean"
            ),

            overflow_risk_score=(
                "overflow_risk_score",
                "max"
            ),

            average_overflow_risk_score=(
                "overflow_risk_score",
                "mean"
            ),

            grid_count=(
                "Grid_ID",
                "count"
            ),

            critical_grid_count=(
                "overflow_risk",
                lambda x: (
                    x == "CRITICAL"
                ).sum()
            ),

            high_grid_count=(
                "overflow_risk",
                lambda x: (
                    x == "HIGH"
                ).sum()
            ),

            high_confidence_grid_count=(
                "prediction_confidence",
                lambda x: (
                    x == "HIGH"
                ).sum()
            ),

            fallback_grid_count=(
                "prediction_source",
                lambda x: (
                    x == "Land-use fallback"
                ).sum()
            )
        )
    )

    # -----------------------------------------------------
    # Determine area-level overflow risk
    # -----------------------------------------------------

    def classify_area_risk(score):

        if score >= 75:
            return "CRITICAL"

        elif score >= 50:
            return "HIGH"

        elif score >= 25:
            return "MEDIUM"

        else:
            return "LOW"

    area["overflow_risk"] = (
        area["overflow_risk_score"]
        .apply(classify_area_risk)
    )

    # -----------------------------------------------------
    # Area collection priority
    # -----------------------------------------------------

    priority_map = {
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4
    }

    area["collection_priority"] = (
        area["overflow_risk"]
        .map(priority_map)
    )

    # -----------------------------------------------------
    # Area prediction confidence
    # -----------------------------------------------------

    def confidence(row):

        if row["fallback_grid_count"] == row["grid_count"]:
            return "LOW"

        elif (
            row["high_confidence_grid_count"]
            / max(row["grid_count"], 1)
            >= 0.75
        ):
            return "HIGH"

        else:
            return "MEDIUM"

    area["prediction_confidence"] = (
        area.apply(
            confidence,
            axis=1
        )
    )

    print(
        "Unique areas generated:",
        len(area)
    )

    print(
        "\nArea overflow-risk distribution:"
    )

    print(
        area[
            "overflow_risk"
        ]
        .value_counts()
        .to_string()
    )

    return area


# =========================================================
# SELECT AREAS FOR COLLECTION
# =========================================================

def select_collection_areas(
    area
):

    print(
        "\nSelecting areas for collection routing..."
    )

    route = area[
        area["overflow_risk"].isin(
            ROUTING_RISK_LEVELS
        )
    ].copy()

    if route.empty:

        raise ValueError(
            "No HIGH or CRITICAL areas were found."
        )

    # Sort by collection priority first,
    # then overflow risk score,
    # then predicted waste.

    route = route.sort_values(
        by=[
            "collection_priority",
            "overflow_risk_score",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False,
            False
        ]
    )

    if MAX_ROUTE_AREAS is not None:

        route = route.head(
            MAX_ROUTE_AREAS
        )

    route = route.reset_index(
        drop=True
    )

    print(
        "Areas selected for routing:",
        len(route)
    )

    print(
        "\nSelected risk distribution:"
    )

    print(
        route[
            "overflow_risk"
        ]
        .value_counts()
        .to_string()
    )

    return route


# =========================================================
# HAVERSINE DISTANCE
# =========================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius_km = 6371.0

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)

    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(dlon / 2) ** 2
    )

    c = (
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )

    return (
        earth_radius_km
        *
        c
    )


# =========================================================
# FIND INITIAL ROUTE START
# =========================================================

def choose_starting_area(
    route
):

    # Start from the highest-priority,
    # highest-risk area.

    route = route.sort_values(
        by=[
            "collection_priority",
            "overflow_risk_score",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False,
            False
        ]
    )

    start_index = route.index[0]

    return start_index


# =========================================================
# NEAREST-NEIGHBOR ROUTE OPTIMIZATION
# =========================================================

def optimize_route(
    route
):

    print(
        "\nOptimizing area collection sequence..."
    )

    if len(route) <= 1:

        route["route_sequence"] = 1

        route["distance_from_previous_km"] = 0.0

        route[
            "cumulative_route_distance_km"
        ] = 0.0

        return route

    # Reset indexes.

    route = route.reset_index(
        drop=True
    )

    coordinates = route[
        [
            "Latitude",
            "Longitude"
        ]
    ].to_numpy()

    visited = set()

    optimized_indices = []

    # Start at highest-risk area.

    start = choose_starting_area(
        route
    )

    current = start

    optimized_indices.append(
        current
    )

    visited.add(
        current
    )

    # -----------------------------------------------------
    # Nearest-neighbor heuristic
    # -----------------------------------------------------

    while len(visited) < len(route):

        current_lat = coordinates[
            current
        ][0]

        current_lon = coordinates[
            current
        ][1]

        nearest_index = None
        nearest_distance = float("inf")

        for candidate in range(
            len(route)
        ):

            if candidate in visited:
                continue

            candidate_lat = coordinates[
                candidate
            ][0]

            candidate_lon = coordinates[
                candidate
            ][1]

            distance = haversine_distance(
                current_lat,
                current_lon,
                candidate_lat,
                candidate_lon
            )

            if distance < nearest_distance:

                nearest_distance = distance

                nearest_index = candidate

        current = nearest_index

        optimized_indices.append(
            current
        )

        visited.add(
            current
        )

    optimized = route.iloc[
        optimized_indices
    ].copy()

    optimized = optimized.reset_index(
        drop=True
    )

    # -----------------------------------------------------
    # Calculate route distances
    # -----------------------------------------------------

    distances = []

    cumulative_distance = 0.0

    for i in range(
        len(optimized)
    ):

        if i == 0:

            distance = 0.0

        else:

            distance = haversine_distance(
                optimized.loc[
                    i - 1,
                    "Latitude"
                ],

                optimized.loc[
                    i - 1,
                    "Longitude"
                ],

                optimized.loc[
                    i,
                    "Latitude"
                ],

                optimized.loc[
                    i,
                    "Longitude"
                ]
            )

        distances.append(
            distance
        )

        cumulative_distance += distance

    optimized[
        "route_sequence"
    ] = np.arange(
        1,
        len(optimized) + 1
    )

    optimized[
        "distance_from_previous_km"
    ] = distances

    optimized[
        "cumulative_route_distance_km"
    ] = np.cumsum(
        distances
    )

    return optimized


# =========================================================
# ADD ROUTE SUMMARY
# =========================================================

def add_route_summary(
    route
):

    print(
        "\nCalculating route summary..."
    )

    total_distance = (
        route[
            "distance_from_previous_km"
        ]
        .sum()
    )

    total_waste = (
        route[
            "predicted_daily_waste_kg"
        ]
        .sum()
    )

    average_risk = (
        route[
            "overflow_risk_score"
        ]
        .mean()
    )

    critical_areas = (
        route[
            "overflow_risk"
        ]
        .eq("CRITICAL")
        .sum()
    )

    high_areas = (
        route[
            "overflow_risk"
        ]
        .eq("HIGH")
        .sum()
    )

    route[
        "total_route_distance_km"
    ] = total_distance

    route[
        "total_route_waste_kg"
    ] = total_waste

    route[
        "average_route_risk_score"
    ] = average_risk

    route[
        "total_route_areas"
    ] = len(route)

    route[
        "critical_area_count"
    ] = critical_areas

    route[
        "high_area_count"
    ] = high_areas

    return route


# =========================================================
# SAVE ROUTE
# =========================================================

def save_route(
    route
):

    print(
        "\nSaving optimized area route..."
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    output_columns = [
        "route_sequence",
        "area_osm_id",
        "area_name",
        "area_admin_level",
        "Latitude",
        "Longitude",
        "grid_count",
        "predicted_daily_waste_kg",
        "average_grid_waste_kg",
        "overflow_risk_score",
        "average_overflow_risk_score",
        "overflow_risk",
        "collection_priority",
        "prediction_confidence",
        "critical_grid_count",
        "high_grid_count",
        "high_confidence_grid_count",
        "fallback_grid_count",
        "distance_from_previous_km",
        "cumulative_route_distance_km",
        "total_route_distance_km",
        "total_route_waste_kg",
        "average_route_risk_score",
        "total_route_areas",
        "critical_area_count",
        "high_area_count"
    ]

    route[
        output_columns
    ].to_csv(
        OUTPUT_CSV,
        index=False
    )

    print(
        "\nArea collection route saved:"
    )

    print(
        OUTPUT_CSV
    )

    return route


# =========================================================
# DISPLAY SUMMARY
# =========================================================

def display_summary(
    route
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BENGALURU AREA-LEVEL ROUTE "
        "OPTIMIZATION SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        "\nTotal areas in optimized route:",
        len(route)
    )

    print(
        "Total predicted waste:",
        f"{route['total_route_waste_kg'].iloc[0]:.2f}",
        "kg"
    )

    print(
        "Total route distance:",
        f"{route['total_route_distance_km'].iloc[0]:.2f}",
        "km"
    )

    print(
        "Average route risk score:",
        f"{route['average_route_risk_score'].iloc[0]:.2f}"
    )

    print(
        "Critical areas:",
        int(route["critical_area_count"].iloc[0])
    )

    print(
        "High-risk areas:",
        int(route["high_area_count"].iloc[0])
    )

    print(
        "\nRisk distribution:"
    )

    print(
        route[
            "overflow_risk"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nOptimized area sequence:"
    )

    print(
        route[
            [
                "route_sequence",
                "area_name",
                "predicted_daily_waste_kg",
                "overflow_risk",
                "overflow_risk_score",
                "distance_from_previous_km"
            ]
        ]
        .head(20)
        .to_string(
            index=False
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=" * 70
    )

    print(
        "BENGALURU AREA-LEVEL "
        "WASTE COLLECTION ROUTE OPTIMIZER"
    )

    print(
        "=" * 70
    )

    # -----------------------------------------------------
    # 1. Load latest overflow predictions
    # -----------------------------------------------------

    predictions = (
        load_overflow_predictions()
    )

    # -----------------------------------------------------
    # 2. Load grid → area mapping
    # -----------------------------------------------------

    mapping = (
        load_area_mapping()
    )

    # -----------------------------------------------------
    # 3. Map every grid to an area
    # -----------------------------------------------------

    merged = (
        merge_predictions_with_areas(
            predictions,
            mapping
        )
    )

    # -----------------------------------------------------
    # 4. Aggregate grid predictions to areas
    # -----------------------------------------------------

    areas = (
        aggregate_to_areas(
            merged
        )
    )

    # -----------------------------------------------------
    # 5. Select HIGH + CRITICAL areas
    # -----------------------------------------------------

    collection_areas = (
        select_collection_areas(
            areas
        )
    )

    # -----------------------------------------------------
    # 6. Optimize area sequence
    # -----------------------------------------------------

    optimized_route = (
        optimize_route(
            collection_areas
        )
    )

    # -----------------------------------------------------
    # 7. Add route statistics
    # -----------------------------------------------------

    optimized_route = (
        add_route_summary(
            optimized_route
        )
    )

    # -----------------------------------------------------
    # 8. Save
    # -----------------------------------------------------

    optimized_route = (
        save_route(
            optimized_route
        )
    )

    # -----------------------------------------------------
    # 9. Display
    # -----------------------------------------------------

    display_summary(
        optimized_route
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "AREA-LEVEL ROUTE OPTIMIZATION COMPLETED"
    )

    print(
        "=" * 70
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()