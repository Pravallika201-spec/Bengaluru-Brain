"""
============================================================
BENGALURU AREA-LEVEL DYNAMIC WASTE ROUTE OPTIMIZER
============================================================

Input:
    bengaluru_area_overflow_predictions.gpkg

Output:
    bengaluru_area_collection_routes.csv
    bengaluru_area_collection_routes.gpkg

Purpose:
    Convert area-level overflow predictions into
    priority-based dynamic collection routes.
============================================================
"""

import os
import math
import pandas as pd
import geopandas as gpd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

PROCESSED_DIR = os.path.join(
    BASE_DIR,
    "waste_module",
    "data",
    "processed"
)

INPUT_GPKG = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_overflow_predictions.gpkg"
)

OUTPUT_CSV = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_collection_routes.csv"
)

OUTPUT_GPKG = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_collection_routes.gpkg"
)

NUMBER_OF_TRUCKS = 50

TARGET_RISKS = [
    "CRITICAL",
    "HIGH"
]


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):

    R = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c


# ============================================================
# LOAD AREA PREDICTIONS
# ============================================================

def load_predictions():

    print("\nLoading area overflow predictions...")

    if not os.path.exists(INPUT_GPKG):
        raise FileNotFoundError(
            f"\nInput file not found:\n{INPUT_GPKG}"
        )

    gdf = gpd.read_file(
        INPUT_GPKG,
        layer="area_overflow_predictions"
    )

    print(
        f"Areas loaded: {len(gdf):,}"
    )

    print(
        f"Prediction date: "
        f"{gdf['prediction_date'].min()} "
        f"to "
        f"{gdf['prediction_date'].max()}"
    )

    return gdf


# ============================================================
# SELECT PRIORITY AREAS
# ============================================================

def select_priority_areas(gdf):

    print("\nSelecting priority collection areas...")

    latest_date = gdf["prediction_date"].max()

    data = gdf[
        gdf["prediction_date"] == latest_date
    ].copy()

    data = data[
        data["Area_Overflow_Risk"].isin(
            TARGET_RISKS
        )
    ].copy()

    # Critical first, then high.
    risk_order = {
        "CRITICAL": 1,
        "HIGH": 2
    }

    data["_risk_order"] = (
        data["Area_Overflow_Risk"]
        .map(risk_order)
    )

    data = data.sort_values(
        [
            "_risk_order",
            "Overflow_Risk_Score",
            "Total_Predicted_Waste_kg"
        ],
        ascending=[
            True,
            False,
            False
        ]
    )

    data = data.drop(
        columns=["_risk_order"]
    )

    print(
        f"Priority areas selected: {len(data):,}"
    )

    print("\nRisk distribution:")

    print(
        data[
            "Area_Overflow_Risk"
        ]
        .value_counts()
        .to_string()
    )

    return data.reset_index(drop=True)


# ============================================================
# CREATE AREA CENTROIDS
# ============================================================

def create_centroids(data):

    print("\nCalculating area centroids...")

    data = data.copy()

    # Project to metric CRS before centroid calculation.
    metric = data.to_crs(
        "EPSG:32643"
    )

    centroids = metric.geometry.centroid

    centroids = gpd.GeoSeries(
        centroids,
        crs="EPSG:32643"
    ).to_crs(
        "EPSG:4326"
    )

    data["Latitude"] = centroids.y.values
    data["Longitude"] = centroids.x.values

    return data


# ============================================================
# CREATE TRUCKS
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
# ASSIGN AREAS TO TRUCKS
# ============================================================

def assign_trucks(data):

    print("\nAssigning priority areas to trucks...")

    data = data.copy()

    trucks = create_trucks()

    truck_load = {
        truck: 0.0
        for truck in trucks
    }

    truck_count = {
        truck: 0
        for truck in trucks
    }

    data["truck_id"] = None

    for idx, row in data.iterrows():

        eligible = [
            truck
            for truck in trucks
            if truck_count[truck] < 20
        ]

        if not eligible:
            eligible = trucks

        selected = min(
            eligible,
            key=lambda truck:
                truck_load[truck]
        )

        data.loc[
            idx,
            "truck_id"
        ] = selected

        truck_load[selected] += float(
            row[
                "Total_Predicted_Waste_kg"
            ]
        )

        truck_count[selected] += 1

    print(
        "Trucks used:",
        data["truck_id"].nunique()
    )

    return data


# ============================================================
# BUILD ROUTES
# ============================================================

def build_routes(data):

    print("\nBuilding geographical routes...")

    records = []

    for truck_id, group in data.groupby(
        "truck_id"
    ):

        group = group.copy()

        remaining = group.copy()

        previous_lat = None
        previous_lon = None

        sequence = 1

        total_distance = 0.0
        total_waste = 0.0

        while len(remaining) > 0:

            # First point = highest risk/waste.
            if previous_lat is None:

                idx = remaining[
                    "Overflow_Risk_Score"
                ].idxmax()

            else:

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

                idx = min(
                    distances,
                    key=lambda x: x[1]
                )[0]

            row = remaining.loc[idx]

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
                    "Total_Predicted_Waste_kg"
                ]
            )

            total_distance += distance
            total_waste += waste

            records.append(
                {
                    "area_osm_id":
                        row["area_osm_id"],

                    "area_name":
                        row["area_name"],

                    "truck_id":
                        truck_id,

                    "route_sequence":
                        sequence,

                    "Latitude":
                        lat,

                    "Longitude":
                        lon,

                    "predicted_waste_kg":
                        waste,

                    "overflow_risk_score":
                        row[
                            "Overflow_Risk_Score"
                        ],

                    "overflow_risk":
                        row[
                            "Area_Overflow_Risk"
                        ],

                    "collection_priority":
                        row[
                            "Collection_Priority"
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

            remaining = remaining.drop(idx)

            sequence += 1

        # Add route totals.
        route_count = sequence - 1

        for record in records:

            if record["truck_id"] == truck_id:

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
                    "route_area_count"
                ] = route_count

    return pd.DataFrame(records)


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(routes):

    routes.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print(
        f"\nCSV saved to:\n{OUTPUT_CSV}"
    )


# ============================================================
# SAVE GEOPACKAGE
# ============================================================

def save_geopackage(routes):

    print("\nCreating route GeoPackage...")

    geometry = gpd.points_from_xy(
        routes["Longitude"],
        routes["Latitude"]
    )

    route_gdf = gpd.GeoDataFrame(
        routes.copy(),
        geometry=geometry,
        crs="EPSG:4326"
    )

    route_gdf.to_file(
        OUTPUT_GPKG,
        layer="area_collection_routes",
        driver="GPKG"
    )

    print(
        f"GeoPackage saved to:\n{OUTPUT_GPKG}"
    )


# ============================================================
# DISPLAY SUMMARY
# ============================================================

def display_summary(routes):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "AREA-LEVEL DYNAMIC ROUTING SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        "\nCollection areas:",
        routes["area_name"].nunique()
    )

    print(
        "Trucks used:",
        routes["truck_id"].nunique()
    )

    print(
        "Total priority waste:",
        f"{routes['predicted_waste_kg'].sum():,.2f}",
        "kg/day"
    )

    print(
        "\nRisk distribution:"
    )

    print(
        routes[
            "overflow_risk"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nTop collection areas:"
    )

    top = routes.sort_values(
        "predicted_waste_kg",
        ascending=False
    ).head(15)

    print(
        top[
            [
                "area_name",
                "predicted_waste_kg",
                "overflow_risk",
                "collection_priority",
                "truck_id",
                "route_sequence"
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\nTruck summary:"
    )

    summary = (
        routes
        .groupby("truck_id")
        .agg(
            areas=(
                "area_name",
                "count"
            ),
            waste_kg=(
                "predicted_waste_kg",
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
        summary.head(10).to_string()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "BENGALURU AREA-LEVEL "
        "DYNAMIC WASTE ROUTE OPTIMIZER"
    )

    print("=" * 70)

    data = load_predictions()

    data = select_priority_areas(
        data
    )

    data = create_centroids(
        data
    )

    data = assign_trucks(
        data
    )

    routes = build_routes(
        data
    )

    save_csv(
        routes
    )

    save_geopackage(
        routes
    )

    display_summary(
        routes
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "AREA-LEVEL ROUTING COMPLETED"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()