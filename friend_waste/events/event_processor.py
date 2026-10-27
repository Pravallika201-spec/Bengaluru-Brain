"""
BENGALURU EVENT PROCESSING ENGINE

Purpose:
    Convert raw event information into spatial event features
    for the 3,053 Bengaluru waste-prediction grids.

Flow:

    Event dataset
          ↓
    Bengaluru grid
          ↓
    Spatial matching
          ↓
    Distance to event
          ↓
    Event intensity
          ↓
    Grid-level event features
"""

import pandas as pd
import geopandas as gpd
import numpy as np

from pathlib import Path
from shapely.geometry import Point


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]

EVENT_FILE = (
    BASE_DIR
    / "satellite"
    / "outputs"
    / "bengaluru_events.csv"
)

GRID_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "bengaluru_grid_features.gpkg"
)

OUTPUT_DIR = (
    BASE_DIR
    / "satellite"
    / "outputs"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_event_features.csv"
)


# ============================================================
# CONSTANTS
# ============================================================

# Approximate event influence radius.
# This is NOT a festival-specific multiplier.
#
# It simply determines how far an event may influence
# surrounding grids.

EVENT_INFLUENCE_RADIUS_KM = 2.0


# ============================================================
# LOAD EVENTS
# ============================================================

def load_events():

    print("\nLoading event dataset...")

    if not EVENT_FILE.exists():

        raise FileNotFoundError(
            f"\nEvent file not found:\n{EVENT_FILE}"
        )

    df = pd.read_csv(
        EVENT_FILE
    )

    print(
        f"Events loaded: {len(df)}"
    )

    return df


# ============================================================
# LOAD GRID
# ============================================================

def load_grid():

    print("\nLoading Bengaluru grid...")

    if not GRID_FILE.exists():

        raise FileNotFoundError(
            f"\nGrid file not found:\n{GRID_FILE}"
        )

    gdf = gpd.read_file(
        GRID_FILE
    )

    print(
        f"Grid rows: {len(gdf)}"
    )

    print(
        f"Unique grids: "
        f"{gdf['Grid_ID'].nunique()}"
    )

    return gdf


# ============================================================
# CREATE EVENT GEOMETRY
# ============================================================

def create_event_geometry(events):

    print(
        "\nCreating event coordinates..."
    )

    events = events.copy()

    events["latitude"] = pd.to_numeric(
        events["latitude"],
        errors="coerce"
    )

    events["longitude"] = pd.to_numeric(
        events["longitude"],
        errors="coerce"
    )

    events = events.dropna(
        subset=[
            "latitude",
            "longitude"
        ]
    ).copy()

    geometry = [
        Point(lon, lat)
        for lon, lat
        in zip(
            events["longitude"],
            events["latitude"]
        )
    ]

    event_gdf = gpd.GeoDataFrame(
        events,
        geometry=geometry,
        crs="EPSG:4326"
    )

    print(
        f"Events with valid coordinates: "
        f"{len(event_gdf)}"
    )

    return event_gdf


# ============================================================
# CALCULATE EVENT INTENSITY
# ============================================================

def calculate_event_intensity(events):

    events = events.copy()

    # --------------------------------------------------------
    # Attendance-based intensity
    # --------------------------------------------------------

    attendance = pd.to_numeric(
        events["expected_attendance"],
        errors="coerce"
    )

    # Use logarithmic scaling so extremely large events
    # do not completely dominate smaller events.

    attendance_score = np.log1p(
        attendance.fillna(0)
    )

    if attendance_score.max() > 0:

        attendance_score = (
            attendance_score
            / attendance_score.max()
        )

    else:

        attendance_score = 0

    # --------------------------------------------------------
    # Existing event intensity
    # --------------------------------------------------------

    provided_intensity = pd.to_numeric(
        events["event_intensity"],
        errors="coerce"
    )

    if provided_intensity.notna().any():

        provided_intensity = (
            provided_intensity
            .fillna(
                provided_intensity
                .median()
            )
        )

        if provided_intensity.max() > 0:

            provided_intensity = (
                provided_intensity
                / provided_intensity.max()
            )

    else:

        provided_intensity = 0

    # --------------------------------------------------------
    # Combined intensity
    # --------------------------------------------------------

    events["calculated_event_intensity"] = (
        0.7 * attendance_score
        +
        0.3 * provided_intensity
    )

    return events


# ============================================================
# CONVERT GRID TO CENTROIDS
# ============================================================

def create_grid_centroids(grid):

    print(
        "\nCreating grid centroids..."
    )

    grid = grid.copy()

    # Ensure geographic CRS

    if grid.crs is None:

        print(
            "Grid CRS missing. "
            "Assuming EPSG:4326."
        )

        grid = grid.set_crs(
            "EPSG:4326"
        )

    # Convert to geographic coordinates

    grid_wgs84 = grid.to_crs(
        "EPSG:4326"
    )

    grid_wgs84["grid_centroid"] = (
        grid_wgs84.geometry.centroid
    )

    grid_wgs84["grid_latitude"] = (
        grid_wgs84
        ["grid_centroid"]
        .y
    )

    grid_wgs84["grid_longitude"] = (
        grid_wgs84
        ["grid_centroid"]
        .x
    )

    return grid_wgs84


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)

    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        +
        np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    c = (
        2
        * np.arcsin(
            np.sqrt(a)
        )
    )

    earth_radius_km = 6371.0

    return earth_radius_km * c


# ============================================================
# GENERATE GRID EVENT FEATURES
# ============================================================

def generate_event_features(
    grid,
    events
):

    print(
        "\nCalculating event influence "
        "for every Bengaluru grid..."
    )

    results = []

    # --------------------------------------------------------
    # Prepare event arrays
    # --------------------------------------------------------

    event_lat = events[
        "latitude"
    ].to_numpy()

    event_lon = events[
        "longitude"
    ].to_numpy()

    event_intensity = events[
        "calculated_event_intensity"
    ].to_numpy()

    # --------------------------------------------------------
    # Process each grid
    # --------------------------------------------------------

    total_grids = len(grid)

    for index, row in grid.iterrows():

        grid_id = row["Grid_ID"]

        lat = row["grid_latitude"]

        lon = row["grid_longitude"]

        # -----------------------------------------------
        # Distance to every event
        # -----------------------------------------------

        distances = haversine_distance(
            lat,
            lon,
            event_lat,
            event_lon
        )

        # -----------------------------------------------
        # Find events within influence radius
        # -----------------------------------------------

        nearby = (
            distances
            <= EVENT_INFLUENCE_RADIUS_KM
        )

        nearby_distances = distances[
            nearby
        ]

        nearby_intensities = (
            event_intensity[
                nearby
            ]
        )

        # -----------------------------------------------
        # Number of nearby events
        # -----------------------------------------------

        event_count = len(
            nearby_distances
        )

        # -----------------------------------------------
        # Nearest event
        # -----------------------------------------------

        if len(distances) > 0:

            nearest_distance = float(
                np.min(distances)
            )

        else:

            nearest_distance = np.nan

        # -----------------------------------------------
        # Event influence
        # -----------------------------------------------

        if event_count > 0:

            # Distance decay:
            #
            # closer event → stronger influence

            distance_decay = (
                1
                /
                (
                    1
                    +
                    nearby_distances
                )
            )

            influence = np.sum(
                nearby_intensities
                *
                distance_decay
            )

        else:

            influence = 0.0

        # -----------------------------------------------
        # Event active indicator
        # -----------------------------------------------

        event_active = (
            1
            if event_count > 0
            else 0
        )

        # -----------------------------------------------
        # Maximum nearby event intensity
        # -----------------------------------------------

        if event_count > 0:

            max_intensity = float(
                np.max(
                    nearby_intensities
                )
            )

        else:

            max_intensity = 0.0

        # -----------------------------------------------
        # Store result
        # -----------------------------------------------

        results.append(
            {
                "Grid_ID": grid_id,
                "event_active": event_active,
                "nearby_event_count": event_count,
                "nearest_event_distance_km":
                    nearest_distance,
                "event_influence_score":
                    influence,
                "max_event_intensity":
                    max_intensity,
            }
        )

        # -----------------------------------------------
        # Progress
        # -----------------------------------------------

        if (
            (index + 1) % 500 == 0
            or index + 1 == total_grids
        ):

            print(
                f"Processed "
                f"{index + 1}/{total_grids} grids"
            )

    return pd.DataFrame(
        results
    )


# ============================================================
# SAVE
# ============================================================

def save_features(df):

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        f"\nEvent features saved:\n"
        f"{OUTPUT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "BENGALURU EVENT → GRID "
        "PROCESSING ENGINE"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    events = load_events()

    grid = load_grid()

    # --------------------------------------------------------
    # Check whether events exist
    # --------------------------------------------------------

    if events.empty:

        print(
            "\nNo events available."
        )

        print(
            "Creating zero-event features "
            "for all grids."
        )

        result = pd.DataFrame(
            {
                "Grid_ID":
                    grid["Grid_ID"],
                "event_active": 0,
                "nearby_event_count": 0,
                "nearest_event_distance_km":
                    np.nan,
                "event_influence_score": 0.0,
                "max_event_intensity": 0.0,
            }
        )

        save_features(result)

        print(
            "\nEvent processing completed."
        )

        return

    # --------------------------------------------------------
    # Event geometry
    # --------------------------------------------------------

    events = create_event_geometry(
        events
    )

    # --------------------------------------------------------
    # Event intensity
    # --------------------------------------------------------

    events = calculate_event_intensity(
        events
    )

    # --------------------------------------------------------
    # Grid centroids
    # --------------------------------------------------------

    grid = create_grid_centroids(
        grid
    )

    # --------------------------------------------------------
    # Generate features
    # --------------------------------------------------------

    result = generate_event_features(
        grid,
        events
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_features(
        result
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT FEATURE SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        f"\nGrid rows: {len(result)}"
    )

    print(
        f"Grids affected by events: "
        f"{result['event_active'].sum()}"
    )

    print(
        "\nEvent count distribution:"
    )

    print(
        result[
            "nearby_event_count"
        ].value_counts()
        .sort_index()
    )

    print(
        "\nTop event-influenced grids:"
    )

    print(
        result.sort_values(
            "event_influence_score",
            ascending=False
        )
        [
            [
                "Grid_ID",
                "event_active",
                "nearby_event_count",
                "nearest_event_distance_km",
                "event_influence_score",
                "max_event_intensity",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT PROCESSING COMPLETED"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()