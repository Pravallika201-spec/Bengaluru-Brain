"""
BENGALURU EVENT-TO-GRID IMPACT ENGINE

Maps upcoming Bengaluru events to the existing Bengaluru
waste-management grid cells.

INPUT:
    waste_module/satellite/outputs/bengaluru_events.csv
    waste_module/data/processed/bengaluru_grid_features.gpkg

OUTPUT:
    waste_module/satellite/outputs/bengaluru_event_grid_impact.csv
"""

import math
from pathlib import Path

import pandas as pd
import geopandas as gpd


# ============================================================
# PATH CONFIGURATION
# ============================================================

# event_grid_mapper.py is located at:
#
# UrbanPredictiveIntelligence/
# └── waste_module/
#     └── events/
#         └── event_grid_mapper.py
#
# parents[0] = events
# parents[1] = waste_module
#
# Therefore we use parents[1].

WASTE_MODULE_DIR = Path(
    __file__
).resolve().parents[1]


# Event dataset created by event_ingestion.py
EVENT_FILE = (
    WASTE_MODULE_DIR
    / "satellite"
    / "outputs"
    / "bengaluru_events.csv"
)


# Existing 3,053-grid dataset
GRID_FILE = (
    WASTE_MODULE_DIR
    / "data"
    / "processed"
    / "bengaluru_grid_features.gpkg"
)


# Output directory
OUTPUT_DIR = (
    WASTE_MODULE_DIR
    / "satellite"
    / "outputs"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# Final event-grid mapping
OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_event_grid_impact.csv"
)


# ============================================================
# BENGALURU CITY CENTER FALLBACK
# ============================================================

# The current Karnataka Tourism event record gives
# "Bengaluru" but does not provide exact event coordinates.
#
# Therefore, until a precise venue is available, we use
# Bengaluru city center as a fallback location.

BENGALURU_CENTER_LAT = 12.9716
BENGALURU_CENTER_LON = 77.5946


# ============================================================
# EVENT IMPACT CONFIGURATION
# ============================================================

# Maximum distance from an event within which the event
# can influence a grid.

MAX_IMPACT_DISTANCE_KM = 10.0


# Event intensity multipliers.
#
# 1 = low
# 2 = medium
# 3 = high / major

INTENSITY_MULTIPLIER = {
    1: 0.05,
    2: 0.10,
    3: 0.20
}


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):
    """
    Calculate geographic distance between two points.

    Returns:
        Distance in kilometres.
    """

    earth_radius_km = 6371.0

    lat1 = math.radians(
        float(lat1)
    )

    lon1 = math.radians(
        float(lon1)
    )

    lat2 = math.radians(
        float(lat2)
    )

    lon2 = math.radians(
        float(lon2)
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )

    return (
        earth_radius_km * c
    )


# ============================================================
# LOAD EVENTS
# ============================================================

def load_events():

    print(
        "\nLoading event dataset..."
    )

    print(
        f"Event file:\n{EVENT_FILE}"
    )

    if not EVENT_FILE.exists():

        raise FileNotFoundError(
            "\nEvent file was not found.\n\n"
            f"Expected location:\n{EVENT_FILE}\n\n"
            "Run the event ingestion engine first:\n"
            "python -m waste_module.events.event_ingestion"
        )

    events = pd.read_csv(
        EVENT_FILE
    )

    print(
        f"Events loaded: {len(events)}"
    )

    if events.empty:

        print(
            "\nWARNING: Event dataset is empty."
        )

    return events


# ============================================================
# LOAD GRID
# ============================================================

def load_grid():

    print(
        "\nLoading Bengaluru grid..."
    )

    print(
        f"Grid file:\n{GRID_FILE}"
    )

    if not GRID_FILE.exists():

        raise FileNotFoundError(
            "\nGrid file was not found.\n\n"
            f"Expected location:\n{GRID_FILE}"
        )

    grid = gpd.read_file(
        GRID_FILE
    )

    print(
        f"Grid rows loaded: {len(grid)}"
    )

    if "Grid_ID" not in grid.columns:

        raise ValueError(
            "Grid_ID column was not found "
            "in the grid dataset."
        )

    print(
        f"Unique Grid_IDs: "
        f"{grid['Grid_ID'].nunique()}"
    )

    return grid


# ============================================================
# FIND GRID COORDINATE COLUMNS
# ============================================================

def find_coordinate_columns(
    grid
):

    latitude_candidates = [
        "Latitude",
        "latitude",
        "LATITUDE",
        "lat"
    ]

    longitude_candidates = [
        "Longitude",
        "longitude",
        "LONGITUDE",
        "lon"
    ]

    latitude_column = None
    longitude_column = None

    for column in latitude_candidates:

        if column in grid.columns:

            latitude_column = column
            break

    for column in longitude_candidates:

        if column in grid.columns:

            longitude_column = column
            break

    if (
        latitude_column is None
        or longitude_column is None
    ):

        raise ValueError(
            "\nCould not find latitude/longitude "
            "columns in the grid dataset.\n\n"
            f"Available columns:\n"
            f"{grid.columns.tolist()}"
        )

    return (
        latitude_column,
        longitude_column
    )


# ============================================================
# RESOLVE EVENT COORDINATES
# ============================================================

def resolve_event_coordinates(
    event
):
    """
    Determine the geographic coordinates of an event.

    Priority:

    1. Use event latitude/longitude if available.
    2. Otherwise use Bengaluru city center.

    Returns:
        latitude,
        longitude,
        coordinate_source
    """

    latitude = event.get(
        "latitude"
    )

    longitude = event.get(
        "longitude"
    )

    # --------------------------------------------------------
    # Try exact event coordinates
    # --------------------------------------------------------

    if (
        pd.notna(latitude)
        and
        pd.notna(longitude)
    ):

        try:

            latitude = float(
                latitude
            )

            longitude = float(
                longitude
            )

            # Basic Bengaluru geographic validation
            if (
                12.70 <= latitude <= 13.20
                and
                77.30 <= longitude <= 77.90
            ):

                return (
                    latitude,
                    longitude,
                    "event_coordinates"
                )

        except (
            ValueError,
            TypeError
        ):

            pass

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    return (
        BENGALURU_CENTER_LAT,
        BENGALURU_CENTER_LON,
        "bengaluru_city_center_fallback"
    )


# ============================================================
# CALCULATE EVENT IMPACT
# ============================================================

def calculate_event_impact(
    distance_km,
    intensity
):
    """
    Calculate spatial event impact.

    Impact decreases as the distance from the event
    increases.

    Formula:

        spatial_factor =
            1 - distance / maximum_distance

        event_impact =
            spatial_factor * intensity_factor
    """

    if distance_km > MAX_IMPACT_DISTANCE_KM:

        return 0.0

    # --------------------------------------------------------
    # Spatial decay
    # --------------------------------------------------------

    spatial_factor = (
        1.0
        -
        (
            distance_km
            /
            MAX_IMPACT_DISTANCE_KM
        )
    )

    spatial_factor = max(
        0.0,
        spatial_factor
    )

    # --------------------------------------------------------
    # Event intensity
    # --------------------------------------------------------

    try:

        intensity = int(
            intensity
        )

    except (
        ValueError,
        TypeError
    ):

        intensity = 1

    intensity_factor = (
        INTENSITY_MULTIPLIER.get(
            intensity,
            0.05
        )
    )

    # --------------------------------------------------------
    # Final event impact
    # --------------------------------------------------------

    impact = (
        spatial_factor
        *
        intensity_factor
    )

    return round(
        impact,
        6
    )


# ============================================================
# MAP EVENTS TO GRIDS
# ============================================================

def map_events_to_grids(
    events,
    grid
):

    print(
        "\nMapping events to Bengaluru grids..."
    )

    (
        latitude_column,
        longitude_column
    ) = find_coordinate_columns(
        grid
    )

    print(
        f"Grid latitude column: "
        f"{latitude_column}"
    )

    print(
        f"Grid longitude column: "
        f"{longitude_column}"
    )

    results = []

    # --------------------------------------------------------
    # Process every event
    # --------------------------------------------------------

    for _, event in events.iterrows():

        event_id = str(
            event.get(
                "event_id",
                "UNKNOWN"
            )
        )

        event_name = str(
            event.get(
                "event_name",
                "Unknown Event"
            )
        )

        event_type = str(
            event.get(
                "event_type",
                "Unknown"
            )
        )

        event_date = event.get(
            "start_datetime"
        )

        event_intensity = event.get(
            "event_intensity",
            1
        )

        try:

            event_intensity = int(
                event_intensity
            )

        except (
            ValueError,
            TypeError
        ):

            event_intensity = 1

        # ----------------------------------------------------
        # Resolve coordinates
        # ----------------------------------------------------

        (
            event_lat,
            event_lon,
            coordinate_source
        ) = resolve_event_coordinates(
            event
        )

        print(
            "\n----------------------------------------"
        )

        print(
            f"Event: {event_name}"
        )

        print(
            f"Event ID: {event_id}"
        )

        print(
            f"Event type: {event_type}"
        )

        print(
            f"Event date: {event_date}"
        )

        print(
            f"Event intensity: "
            f"{event_intensity}"
        )

        print(
            f"Event coordinates: "
            f"{event_lat:.6f}, "
            f"{event_lon:.6f}"
        )

        print(
            f"Coordinate source: "
            f"{coordinate_source}"
        )

        affected_count = 0

        # ----------------------------------------------------
        # Iterate through all 3,053 grids
        # ----------------------------------------------------

        for _, grid_row in grid.iterrows():

            try:

                grid_lat = float(
                    grid_row[
                        latitude_column
                    ]
                )

                grid_lon = float(
                    grid_row[
                        longitude_column
                    ]
                )

            except (
                ValueError,
                TypeError
            ):

                continue

            if (
                pd.isna(grid_lat)
                or
                pd.isna(grid_lon)
            ):

                continue

            # ------------------------------------------------
            # Distance
            # ------------------------------------------------

            distance_km = (
                haversine_distance(
                    event_lat,
                    event_lon,
                    grid_lat,
                    grid_lon
                )
            )

            # ------------------------------------------------
            # Ignore grids outside event radius
            # ------------------------------------------------

            if (
                distance_km
                >
                MAX_IMPACT_DISTANCE_KM
            ):

                continue

            # ------------------------------------------------
            # Event impact
            # ------------------------------------------------

            impact_factor = (
                calculate_event_impact(
                    distance_km,
                    event_intensity
                )
            )

            if impact_factor <= 0:

                continue

            affected_count += 1

            results.append({

                "event_id":
                    event_id,

                "event_name":
                    event_name,

                "event_type":
                    event_type,

                "event_date":
                    event_date,

                "Grid_ID":
                    grid_row[
                        "Grid_ID"
                    ],

                "grid_latitude":
                    grid_lat,

                "grid_longitude":
                    grid_lon,

                "event_latitude":
                    event_lat,

                "event_longitude":
                    event_lon,

                "distance_from_event_km":
                    round(
                        distance_km,
                        4
                    ),

                "event_intensity":
                    event_intensity,

                "coordinate_source":
                    coordinate_source,

                "event_impact_factor":
                    impact_factor
            })

        print(
            f"Affected grids: "
            f"{affected_count}"
        )

    return pd.DataFrame(
        results
    )


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_output(
    result
):

    result.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nEvent-grid impact dataset saved:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU EVENT-TO-GRID "
        "IMPACT ENGINE"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # Load event data
    # --------------------------------------------------------

    events = load_events()

    # --------------------------------------------------------
    # Load grid data
    # --------------------------------------------------------

    grid = load_grid()

    # --------------------------------------------------------
    # Stop if no events
    # --------------------------------------------------------

    if events.empty:

        print(
            "\nNo events available."
        )

        print(
            "Event-grid mapping cannot be performed."
        )

        return

    # --------------------------------------------------------
    # Map events
    # --------------------------------------------------------

    result = map_events_to_grids(
        events,
        grid
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_output(
        result
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT-GRID IMPACT SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        f"\nTotal events: "
        f"{len(events)}"
    )

    print(
        f"Total event-grid records: "
        f"{len(result)}"
    )

    if not result.empty:

        print(
            f"Unique affected grids: "
            f"{result['Grid_ID'].nunique()}"
        )

        print(
            "\nEvent distribution:"
        )

        print(
            result[
                "event_name"
            ].value_counts()
        )

        print(
            "\nImpact statistics:"
        )

        print(
            result[
                "event_impact_factor"
            ].describe()
        )

        # ----------------------------------------------------
        # Top affected grids
        # ----------------------------------------------------

        print(
            "\nTop 10 affected grids:"
        )

        top_grids = (
            result
            .sort_values(
                "event_impact_factor",
                ascending=False
            )
            .head(10)
        )

        print(
            top_grids[
                [
                    "event_id",
                    "event_name",
                    "Grid_ID",
                    "distance_from_event_km",
                    "event_intensity",
                    "event_impact_factor"
                ]
            ].to_string(
                index=False
            )
        )

    else:

        print(
            "\nNo grids were affected."
        )

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT-GRID MAPPING COMPLETED"
    )

    print(
        "=" * 60
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()