"""
============================================================
BENGALURU EVENT-AWARE AREA-LEVEL DYNAMIC ROUTE OPTIMIZER
============================================================

Pipeline:

    Event-aware grid predictions
            ↓
    Grid → Area spatial aggregation
            ↓
    Event-aware area waste
            ↓
    Area risk classification
            ↓
    Priority area selection
            ↓
    50-truck dynamic routing

Input:
    bengaluru_event_aware_waste_predictions.csv
    bengaluru_area_overflow_predictions.gpkg

Output:
    bengaluru_event_aware_area_collection_routes.csv
    bengaluru_event_aware_area_collection_routes.gpkg
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

SATELLITE_OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "waste_module",
    "satellite",
    "outputs"
)

PROCESSED_DIR = os.path.join(
    BASE_DIR,
    "waste_module",
    "data",
    "processed"
)

EVENT_GRID_FILE = os.path.join(
    SATELLITE_OUTPUT_DIR,
    "bengaluru_event_aware_waste_predictions.csv"
)

AREA_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_overflow_predictions.gpkg"
)

OUTPUT_CSV = os.path.join(
    PROCESSED_DIR,
    "bengaluru_event_aware_area_collection_routes.csv"
)

OUTPUT_GPKG = os.path.join(
    PROCESSED_DIR,
    "bengaluru_event_aware_area_collection_routes.gpkg"
)

NUMBER_OF_TRUCKS = 50

# Select top 30% highest-risk areas.
# This gives enough collection areas for dynamic routing.
PRIORITY_PERCENTILE = 70


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
# LOAD EVENT-AWARE GRID PREDICTIONS
# ============================================================

def load_event_aware_predictions():

    print(
        "\nLoading event-aware grid predictions..."
    )

    if not os.path.exists(EVENT_GRID_FILE):

        raise FileNotFoundError(
            f"\nEvent-aware prediction file not found:\n"
            f"{EVENT_GRID_FILE}\n\n"
            "Run:\n"
            "python -m waste_module.events.event_aware_waste_predictor"
        )

    df = pd.read_csv(
        EVENT_GRID_FILE
    )

    print(
        "Event-aware grids loaded:",
        f"{len(df):,}"
    )

    required = [
        "Grid_ID",
        "Latitude",
        "Longitude",
        "event_adjusted_waste_kg",
        "additional_event_waste_kg",
        "event_aware_waste_risk",
        "event_aware_collection_priority"
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:

        raise ValueError(
            f"\nMissing required columns:\n{missing}"
        )

    return df


# ============================================================
# LOAD AREA POLYGONS
# ============================================================

def load_areas():

    print(
        "\nLoading Bengaluru area boundaries..."
    )

    if not os.path.exists(AREA_FILE):

        raise FileNotFoundError(
            f"\nArea file not found:\n{AREA_FILE}"
        )

    areas = gpd.read_file(
        AREA_FILE,
        layer="area_overflow_predictions"
    )

    print(
        "Areas loaded:",
        f"{len(areas):,}"
    )

    required = [
        "area_osm_id",
        "area_name"
    ]

    missing = [
        col
        for col in required
        if col not in areas.columns
    ]

    if missing:

        raise ValueError(
            f"\nMissing area columns:\n{missing}"
        )

    return areas


# ============================================================
# ASSIGN GRIDS TO AREAS
# ============================================================

def aggregate_grids_to_areas(
    grids,
    areas
):

    print(
        "\nMapping event-aware grids to areas..."
    )

    # Create grid point geometries.
    grid_gdf = gpd.GeoDataFrame(
        grids.copy(),
        geometry=gpd.points_from_xy(
            grids["Longitude"],
            grids["Latitude"]
        ),
        crs="EPSG:4326"
    )

    # Ensure areas have a CRS.
    if areas.crs is None:

        areas = areas.set_crs(
            "EPSG:4326"
        )

    areas = areas.to_crs(
        "EPSG:4326"
    )

    # Keep only the information needed from areas.
    area_columns = [
        "area_osm_id",
        "area_name",
        "geometry"
    ]

    area_polygons = areas[
        area_columns
    ].copy()

    # Spatially assign every grid to an area.
    joined = gpd.sjoin(
        grid_gdf,
        area_polygons,
        how="left",
        predicate="within"
    )

    # Some points can fall just outside polygon boundaries.
    # Those grids are not used in area aggregation.
    unmatched = joined[
        joined["area_osm_id"].isna()
    ]

    print(
        "Grids assigned to areas:",
        f"{len(joined) - len(unmatched):,}"
    )

    print(
        "Unmatched grids:",
        f"{len(unmatched):,}"
    )

    joined = joined.dropna(
        subset=["area_osm_id"]
    )

    # Aggregate event-aware waste.
    aggregation = (
        joined
        .groupby(
            [
                "area_osm_id",
                "area_name"
            ]
        )
        .agg(
            Total_Event_Adjusted_Waste_kg=(
                "event_adjusted_waste_kg",
                "sum"
            ),

            Total_Additional_Event_Waste_kg=(
                "additional_event_waste_kg",
                "sum"
            ),

            Grid_Count=(
                "Grid_ID",
                "count"
            ),

            Event_Affected_Grid_Count=(
                "event_affected",
                "sum"
            ),

            Critical_Grid_Count=(
                "event_aware_waste_risk",
                lambda x:
                    (x == "CRITICAL").sum()
            ),

            High_Grid_Count=(
                "event_aware_waste_risk",
                lambda x:
                    (x == "HIGH").sum()
            )
        )
        .reset_index()
    )

    print(
        "Areas with event-aware predictions:",
        f"{len(aggregation):,}"
    )

    return aggregation


# ============================================================
# ATTACH AREA GEOMETRY
# ============================================================

def attach_area_geometry(
    aggregated,
    areas
):

    result = areas[
        [
            "area_osm_id",
            "area_name",
            "geometry"
        ]
    ].merge(
        aggregated,
        on=[
            "area_osm_id",
            "area_name"
        ],
        how="inner"
    )

    return gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=areas.crs
    )


# ============================================================
# CALCULATE EVENT-AWARE AREA RISK
# ============================================================

def calculate_area_risk(
    data
):

    print(
        "\nCalculating event-aware area risk..."
    )

    data = data.copy()

    # Waste percentile.
    data[
        "Waste_Percentile"
    ] = (
        data[
            "Total_Event_Adjusted_Waste_kg"
        ]
        .rank(
            pct=True
        )
    )

    # Event pressure.
    data[
        "Event_Waste_Percentile"
    ] = (
        data[
            "Total_Additional_Event_Waste_kg"
        ]
        .rank(
            pct=True
        )
    )

    # Combined score.
    #
    # 70% = total event-adjusted waste
    # 30% = additional event-generated waste
    #
    # This prevents an area with a large normal
    # waste load from being ignored during an event.

    data[
        "Event_Aware_Risk_Score"
    ] = (
        0.70
        * data[
            "Waste_Percentile"
        ]
        +
        0.30
        * data[
            "Event_Waste_Percentile"
        ]
    )

    def classify(score):

        if score >= 0.90:
            return "CRITICAL"

        if score >= 0.70:
            return "HIGH"

        if score >= 0.40:
            return "MEDIUM"

        return "LOW"

    data[
        "Event_Aware_Area_Risk"
    ] = data[
        "Event_Aware_Risk_Score"
    ].apply(
        classify
    )

    def priority(row):

        if row[
            "Event_Aware_Area_Risk"
        ] == "CRITICAL":

            return "P1 - Event Critical"

        if row[
            "Event_Aware_Area_Risk"
        ] == "HIGH":

            if row[
                "Total_Additional_Event_Waste_kg"
            ] > 0:

                return "P2 - Event High"

            return "P3 - High"

        return "P4 - Normal"

    data[
        "Event_Aware_Collection_Priority"
    ] = data.apply(
        priority,
        axis=1
    )

    print(
        "\nEvent-aware area risk distribution:"
    )

    print(
        data[
            "Event_Aware_Area_Risk"
        ]
        .value_counts()
        .to_string()
    )

    return data


# ============================================================
# SELECT PRIORITY AREAS
# ============================================================

def select_priority_areas(
    data
):

    print(
        "\nSelecting event-priority collection areas..."
    )

    selected = data[
        data[
            "Event_Aware_Area_Risk"
        ].isin(
            [
                "CRITICAL",
                "HIGH"
            ]
        )
    ].copy()

    selected = selected.sort_values(
        [
            "Event_Aware_Risk_Score",
            "Total_Event_Adjusted_Waste_kg"
        ],
        ascending=[
            False,
            False
        ]
    )

    print(
        "Priority areas selected:",
        f"{len(selected):,}"
    )

    print(
        "\nPriority risk distribution:"
    )

    print(
        selected[
            "Event_Aware_Area_Risk"
        ]
        .value_counts()
        .to_string()
    )

    return selected.reset_index(
        drop=True
    )


# ============================================================
# CREATE CENTROIDS
# ============================================================

def create_centroids(
    data
):

    print(
        "\nCalculating area centroids..."
    )

    data = data.copy()

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

    data[
        "Latitude"
    ] = centroids.y.values

    data[
        "Longitude"
    ] = centroids.x.values

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

def assign_trucks(
    data
):

    print(
        "\nAssigning event-priority areas to trucks..."
    )

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

    data[
        "truck_id"
    ] = None

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

        truck_load[
            selected
        ] += float(
            row[
                "Total_Event_Adjusted_Waste_kg"
            ]
        )

        truck_count[
            selected
        ] += 1

    print(
        "Trucks used:",
        data[
            "truck_id"
        ].nunique()
    )

    return data


# ============================================================
# BUILD GEOGRAPHICAL ROUTES
# ============================================================

def build_routes(
    data
):

    print(
        "\nBuilding event-aware geographical routes..."
    )

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

            if previous_lat is None:

                # First stop:
                # highest event-aware risk.
                idx = remaining[
                    "Event_Aware_Risk_Score"
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

            row = remaining.loc[
                idx
            ]

            lat = float(
                row[
                    "Latitude"
                ]
            )

            lon = float(
                row[
                    "Longitude"
                ]
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
                    "Total_Event_Adjusted_Waste_kg"
                ]
            )

            additional_waste = float(
                row[
                    "Total_Additional_Event_Waste_kg"
                ]
            )

            total_distance += distance
            total_waste += waste

            records.append(
                {
                    "area_osm_id":
                        row[
                            "area_osm_id"
                        ],

                    "area_name":
                        row[
                            "area_name"
                        ],

                    "truck_id":
                        truck_id,

                    "route_sequence":
                        sequence,

                    "Latitude":
                        lat,

                    "Longitude":
                        lon,

                    "event_adjusted_waste_kg":
                        round(
                            waste,
                            2
                        ),

                    "additional_event_waste_kg":
                        round(
                            additional_waste,
                            2
                        ),

                    "event_aware_risk_score":
                        round(
                            float(
                                row[
                                    "Event_Aware_Risk_Score"
                                ]
                            ),
                            4
                        ),

                    "overflow_risk":
                        row[
                            "Event_Aware_Area_Risk"
                        ],

                    "collection_priority":
                        row[
                            "Event_Aware_Collection_Priority"
                        ],

                    "event_affected_grids":
                        int(
                            row[
                                "Event_Affected_Grid_Count"
                            ]
                        ),

                    "critical_grids":
                        int(
                            row[
                                "Critical_Grid_Count"
                            ]
                        ),

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

            sequence += 1

        route_count = sequence - 1

        for record in records:

            if record[
                "truck_id"
            ] == truck_id:

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

    return pd.DataFrame(
        records
    )


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(
    routes
):

    routes.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print(
        "\nCSV saved to:"
    )

    print(
        OUTPUT_CSV
    )


# ============================================================
# SAVE GEOPACKAGE
# ============================================================

def save_geopackage(
    routes
):

    print(
        "\nCreating event-aware route GeoPackage..."
    )

    geometry = gpd.points_from_xy(
        routes[
            "Longitude"
        ],
        routes[
            "Latitude"
        ]
    )

    route_gdf = gpd.GeoDataFrame(
        routes.copy(),
        geometry=geometry,
        crs="EPSG:4326"
    )

    route_gdf.to_file(
        OUTPUT_GPKG,
        layer="event_aware_area_routes",
        driver="GPKG"
    )

    print(
        "GeoPackage saved to:"
    )

    print(
        OUTPUT_GPKG
    )


# ============================================================
# DISPLAY SUMMARY
# ============================================================

def display_summary(
    routes
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "EVENT-AWARE AREA ROUTING SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        "\nCollection areas:",
        routes[
            "area_name"
        ].nunique()
    )

    print(
        "Trucks used:",
        routes[
            "truck_id"
        ].nunique()
    )

    print(
        "Event-adjusted priority waste:",
        f"{routes['event_adjusted_waste_kg'].sum():,.2f}",
        "kg/day"
    )

    print(
        "Additional event waste in routes:",
        f"{routes['additional_event_waste_kg'].sum():,.2f}",
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
        "\nTop event-aware collection areas:"
    )

    top = routes.sort_values(
        [
            "event_adjusted_waste_kg"
        ],
        ascending=False
    ).head(15)

    print(
        top[
            [
                "area_name",
                "event_adjusted_waste_kg",
                "additional_event_waste_kg",
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
        .groupby(
            "truck_id"
        )
        .agg(
            areas=(
                "area_name",
                "count"
            ),
            event_adjusted_waste_kg=(
                "event_adjusted_waste_kg",
                "sum"
            ),
            distance_km=(
                "route_total_distance_km",
                "first"
            )
        )
        .sort_values(
            "event_adjusted_waste_kg",
            ascending=False
        )
    )

    print(
        summary.head(
            10
        ).to_string()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "BENGALURU EVENT-AWARE "
        "AREA-LEVEL DYNAMIC ROUTE OPTIMIZER"
    )

    print(
        "=" * 70
    )

    # 1. Load event-aware grid predictions.
    grids = load_event_aware_predictions()

    # 2. Load area polygons.
    areas = load_areas()

    # 3. Grid → area aggregation.
    aggregated = aggregate_grids_to_areas(
        grids,
        areas
    )

    # 4. Attach area geometry.
    data = attach_area_geometry(
        aggregated,
        areas
    )

    # 5. Calculate event-aware risk.
    data = calculate_area_risk(
        data
    )

    # 6. Select priority areas.
    priority = select_priority_areas(
        data
    )

    # 7. Calculate centroids.
    priority = create_centroids(
        priority
    )

    # 8. Assign trucks.
    priority = assign_trucks(
        priority
    )

    # 9. Build geographical routes.
    routes = build_routes(
        priority
    )

    # 10. Save CSV.
    save_csv(
        routes
    )

    # 11. Save GeoPackage.
    save_geopackage(
        routes
    )

    # 12. Summary.
    display_summary(
        routes
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "EVENT-AWARE AREA ROUTING COMPLETED"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()