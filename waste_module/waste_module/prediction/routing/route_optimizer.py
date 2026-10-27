"""
=========================================================
URBAN PREDICTIVE INTELLIGENCE SYSTEM
BENGALURU DYNAMIC WASTE COLLECTION ROUTE OPTIMIZER
=========================================================

Features:
1. Loads collection-priority predictions
2. Selects high-priority locations
3. Uses projected coordinates for accurate centroids
4. Assigns collection points to trucks
5. Builds nearest-neighbour collection routes
6. Calculates route distances
7. Saves results safely to GeoPackage
8. Produces a truck-level summary

No external routing API is used.
=========================================================
"""

from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

import geopandas as gpd
import pandas as pd


# =========================================================
# PROJECT PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

INPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_collection_priority.gpkg"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_collection_routes.gpkg"
)


# =========================================================
# PARAMETERS
# =========================================================

# We use a realistic planning capacity per truck.
TRUCK_CAPACITY_KG = 5000

# More trucks can be used if necessary.
NUMBER_OF_TRUCKS = 50

HIGH_PRIORITY_LEVELS = [
    "P1 - Immediate",
    "P2 - Urgent",
    "P3 - High"
]


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

    lat1 = radians(lat1)
    lon1 = radians(lon1)

    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return earth_radius_km * c


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("BENGALURU DYNAMIC WASTE COLLECTION ROUTE OPTIMIZER")
    print("=" * 70)

    # =====================================================
    # LOAD DATA
    # =====================================================

    print("\nLoading collection priority dataset...")

    print(
        f"Input file:\n{INPUT_FILE}"
    )

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            "\nCollection priority dataset was not found.\n\n"
            f"Expected:\n{INPUT_FILE}"
        )

    gdf = gpd.read_file(
        INPUT_FILE,
        layer="collection_priority"
    )

    print(
        f"Total records: {len(gdf):,}"
    )

    # =====================================================
    # CHECK REQUIRED COLUMNS
    # =====================================================

    required_columns = [
        "Grid_ID",
        "prediction_date",
        "predicted_daily_waste_kg",
        "collection_priority",
        "collection_priority_score"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in gdf.columns
    ]

    if missing_columns:

        raise ValueError(
            f"Missing columns: {missing_columns}"
        )

    # =====================================================
    # SELECT HIGH PRIORITY
    # =====================================================

    print(
        "\nSelecting high-priority collection locations..."
    )

    routes = gdf[
        gdf["collection_priority"]
        .isin(HIGH_PRIORITY_LEVELS)
    ].copy()

    print(
        f"High-priority records: {len(routes):,}"
    )

    if len(routes) == 0:

        raise ValueError(
            "No high-priority locations found."
        )

    # =====================================================
    # SELECT LATEST DATE
    # =====================================================

    latest_date = routes[
        "prediction_date"
    ].max()

    routes = routes[
        routes["prediction_date"]
        == latest_date
    ].copy()

    print(
        f"Routing date: {latest_date}"
    )

    print(
        f"Locations to route: {len(routes):,}"
    )

    # =====================================================
    # CLEAN WASTE VALUES
    # =====================================================

    routes[
        "predicted_daily_waste_kg"
    ] = pd.to_numeric(
        routes[
            "predicted_daily_waste_kg"
        ],
        errors="coerce"
    ).fillna(0)

    routes[
        "collection_priority_score"
    ] = pd.to_numeric(
        routes[
            "collection_priority_score"
        ],
        errors="coerce"
    ).fillna(0)

    # =====================================================
    # PROJECT TO METRIC CRS
    # =====================================================

    print(
        "\nProjecting grid geometries..."
    )

    # EPSG:32643 = UTM Zone 43N
    # Suitable for Bengaluru-area metric calculations.

    routes_projected = routes.to_crs(
        epsg=32643
    )

    # Accurate centroid calculation.

    centroids = (
        routes_projected
        .geometry
        .centroid
    )

    # Convert centroid back to WGS84.

    centroid_gdf = gpd.GeoDataFrame(
        geometry=centroids,
        crs="EPSG:32643"
    ).to_crs(
        epsg=4326
    )

    routes["longitude"] = (
        centroid_gdf.geometry.x.values
    )

    routes["latitude"] = (
        centroid_gdf.geometry.y.values
    )

    # =====================================================
    # SORT BY PRIORITY
    # =====================================================

    routes = routes.sort_values(
        "collection_priority_score",
        ascending=False
    ).reset_index(
        drop=True
    )

    # =====================================================
    # TRUCK ASSIGNMENT
    # =====================================================

    print(
        "\nAssigning locations to trucks..."
    )

    truck_loads = {
        truck_id: 0.0
        for truck_id in range(
            1,
            NUMBER_OF_TRUCKS + 1
        )
    }

    routes["truck_id"] = None

    unassigned_count = 0

    for index, row in routes.iterrows():

        waste = float(
            row[
                "predicted_daily_waste_kg"
            ]
        )

        assigned = False

        # Find truck with available capacity.

        available_trucks = sorted(
            truck_loads,
            key=truck_loads.get
        )

        for truck_id in available_trucks:

            remaining = (
                TRUCK_CAPACITY_KG
                -
                truck_loads[
                    truck_id
                ]
            )

            if waste <= remaining:

                routes.loc[
                    index,
                    "truck_id"
                ] = (
                    f"TRUCK_{truck_id:02d}"
                )

                truck_loads[
                    truck_id
                ] += waste

                assigned = True

                break

        # =================================================
        # Oversized location
        # =================================================

        if not assigned:

            # Find the least-loaded truck.

            truck_id = min(
                truck_loads,
                key=truck_loads.get
            )

            # Assign it anyway.

            routes.loc[
                index,
                "truck_id"
            ] = (
                f"TRUCK_{truck_id:02d}"
            )

            truck_loads[
                truck_id
            ] += waste

            unassigned_count += 1

    print(
        f"Locations assigned: {len(routes):,}"
    )

    if unassigned_count > 0:

        print(
            f"Capacity-overflow assignments: "
            f"{unassigned_count}"
        )

    # =====================================================
    # ROUTE SEQUENCE
    # =====================================================

    print(
        "\nOptimizing route sequence..."
    )

    routes["route_sequence"] = 0

    for truck_id in routes[
        "truck_id"
    ].unique():

        truck_indices = list(
            routes[
                routes["truck_id"]
                == truck_id
            ].index
        )

        if not truck_indices:

            continue

        # Start with highest-priority point.

        current = truck_indices.pop(0)

        sequence = 1

        routes.loc[
            current,
            "route_sequence"
        ] = sequence

        while truck_indices:

            current_lat = routes.loc[
                current,
                "latitude"
            ]

            current_lon = routes.loc[
                current,
                "longitude"
            ]

            nearest = min(
                truck_indices,
                key=lambda idx:
                haversine_distance(
                    current_lat,
                    current_lon,
                    routes.loc[
                        idx,
                        "latitude"
                    ],
                    routes.loc[
                        idx,
                        "longitude"
                    ]
                )
            )

            truck_indices.remove(
                nearest
            )

            sequence += 1

            routes.loc[
                nearest,
                "route_sequence"
            ] = sequence

            current = nearest

    # =====================================================
    # DISTANCE CALCULATION
    # =====================================================

    print(
        "\nCalculating route distances..."
    )

    routes[
        "distance_from_previous_km"
    ] = 0.0

    for truck_id in routes[
        "truck_id"
    ].unique():

        truck = routes[
            routes["truck_id"]
            == truck_id
        ].sort_values(
            "route_sequence"
        )

        previous_lat = None
        previous_lon = None

        for index, row in truck.iterrows():

            if previous_lat is not None:

                distance = haversine_distance(
                    previous_lat,
                    previous_lon,
                    row["latitude"],
                    row["longitude"]
                )

                routes.loc[
                    index,
                    "distance_from_previous_km"
                ] = distance

            previous_lat = row[
                "latitude"
            ]

            previous_lon = row[
                "longitude"
            ]

    # =====================================================
    # ROUTE TOTALS
    # =====================================================

    routes[
        "route_total_distance_km"
    ] = (
        routes
        .groupby("truck_id")[
            "distance_from_previous_km"
        ]
        .transform("sum")
    )

    routes[
        "route_total_waste_kg"
    ] = (
        routes
        .groupby("truck_id")[
            "predicted_daily_waste_kg"
        ]
        .transform("sum")
    )

    routes[
        "route_utilization_percent"
    ] = (
        routes[
            "route_total_waste_kg"
        ]
        /
        TRUCK_CAPACITY_KG
        * 100
    )

    # =====================================================
    # CLEAN FIELDS BEFORE SAVING
    # =====================================================

    print(
        "\nPreparing output dataset..."
    )

    # GeoPackage/OGR can sometimes reject problematic
    # pandas extension types. Convert routing fields
    # explicitly.

    routes["longitude"] = pd.to_numeric(
        routes["longitude"],
        errors="coerce"
    ).astype(float)

    routes["latitude"] = pd.to_numeric(
        routes["latitude"],
        errors="coerce"
    ).astype(float)

    routes["route_sequence"] = (
        pd.to_numeric(
            routes["route_sequence"],
            errors="coerce"
        )
        .fillna(0)
        .astype(int)
    )

    routes["truck_id"] = (
        routes["truck_id"]
        .fillna("UNASSIGNED")
        .astype(str)
    )

    # =====================================================
    # SAVE
    # =====================================================

    print(
        "\nSaving optimized routes..."
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Remove old output if present.

    if OUTPUT_FILE.exists():

        try:

            OUTPUT_FILE.unlink()

        except PermissionError:

            print(
                "\nWARNING: Output file is open."
            )

            print(
                "Close it in QGIS/VS Code and run again."
            )

            return

    # Save only safe fields.

    output_columns = [
        "Grid_ID",
        "prediction_date",
        "collection_priority",
        "collection_priority_score",
        "predicted_daily_waste_kg",
        "truck_id",
        "route_sequence",
        "latitude",
        "longitude",
        "distance_from_previous_km",
        "route_total_distance_km",
        "route_total_waste_kg",
        "route_utilization_percent",
        "geometry"
    ]

    output = routes[
        output_columns
    ].copy()

    output.to_file(
        OUTPUT_FILE,
        layer="collection_routes",
        driver="GPKG"
    )

    # =====================================================
    # SUMMARY
    # =====================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "TRUCK SUMMARY"
    )

    summary = (
        routes
        .groupby("truck_id")
        .agg(
            collection_points=(
                "Grid_ID",
                "count"
            ),
            total_waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),
            total_distance_km=(
                "distance_from_previous_km",
                "sum"
            )
        )
        .sort_values(
            "total_waste_kg",
            ascending=False
        )
    )

    summary[
        "utilization_percent"
    ] = (
        summary[
            "total_waste_kg"
        ]
        /
        TRUCK_CAPACITY_KG
        * 100
    )

    print(
        summary.round(2)
    )

    print(
        "\nTotal trucks used:"
    )

    print(
        routes[
            "truck_id"
        ].nunique()
    )

    print(
        "\nTotal collection locations:"
    )

    print(
        len(routes)
    )

    print(
        "\nTotal estimated route distance:"
    )

    print(
        round(
            routes[
                "distance_from_previous_km"
            ].sum(),
            2
        ),
        "km"
    )

    print(
        "\nTotal predicted waste:"
    )

    print(
        round(
            routes[
                "predicted_daily_waste_kg"
            ].sum(),
            2
        ),
        "kg"
    )

    print(
        "\nOutput saved to:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "ROUTE OPTIMIZATION COMPLETED SUCCESSFULLY"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":

    main()