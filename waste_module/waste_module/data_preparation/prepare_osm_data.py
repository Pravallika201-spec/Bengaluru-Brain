"""
=========================================================
Urban Predictive Intelligence System
Local OpenStreetMap Data Preparation Engine

Purpose:
    Read the downloaded OSM PBF locally using GDAL/Pyogrio.
    Extract Bengaluru-relevant OSM features without Overpass.

=========================================================
"""

from pathlib import Path

import geopandas as gpd
import pyogrio

from waste_module.config import BOUNDARY_FILE


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

OSM_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "osm_data"
    / "southern-zone-260806.osm.pbf"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "osm"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ---------------------------------------------------------
# Load Bengaluru Boundary
# ---------------------------------------------------------

def load_bengaluru_boundary():

    print("\nLoading Bengaluru boundary...")

    boundary = gpd.read_file(BOUNDARY_FILE)

    # Convert to WGS84 because OSM data is normally
    # stored in geographic coordinates.
    boundary = boundary.to_crs(4326)

    # Merge multiple boundary features if necessary.
    boundary_geometry = boundary.geometry.union_all()

    print("Bengaluru boundary loaded.")

    return boundary_geometry


# ---------------------------------------------------------
# Check OSM File
# ---------------------------------------------------------

def check_osm_file():

    if not OSM_FILE.exists():

        raise FileNotFoundError(
            f"\nOSM file not found:\n{OSM_FILE}"
        )

    print("\nOSM PBF found:")
    print(OSM_FILE)

    print("\nAvailable OSM layers:")

    layers = pyogrio.list_layers(OSM_FILE)

    for layer in layers:

        print(
            f"  {layer[0]} "
            f"({layer[1]})"
        )


# ---------------------------------------------------------
# Extract Multipolygons
# ---------------------------------------------------------

def extract_multipolygons(boundary):

    print("\nReading OSM multipolygons...")

    gdf = gpd.read_file(
        OSM_FILE,
        layer="multipolygons"
    )

    print(
        f"Total OSM multipolygons: "
        f"{len(gdf):,}"
    )

    # Ensure coordinate system
    gdf = gdf.to_crs(4326)

    print("\nFiltering features around Bengaluru...")

    # First use bounding box to reduce processing.
    minx, miny, maxx, maxy = boundary.bounds

    gdf = gdf.cx[
        minx:maxx,
        miny:maxy
    ]

    print(
        f"Features inside Bengaluru bounding box: "
        f"{len(gdf):,}"
    )

    # Accurate spatial filtering.
    gdf = gdf[
        gdf.geometry.intersects(boundary)
    ].copy()

    print(
        f"Features intersecting Bengaluru: "
        f"{len(gdf):,}"
    )

    return gdf


# ---------------------------------------------------------
# Save Data
# ---------------------------------------------------------

def save_landuse_features(gdf):

    output_file = (
        OUTPUT_DIR
        / "bengaluru_osm_multipolygons.gpkg"
    )

    print("\nSaving Bengaluru OSM polygons...")

    gdf.to_file(
        output_file,
        layer="multipolygons",
        driver="GPKG"
    )

    print("\nSaved successfully:")
    print(output_file)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("LOCAL OSM DATA PREPARATION ENGINE")
    print("=" * 60)

    check_osm_file()

    boundary = load_bengaluru_boundary()

    multipolygons = extract_multipolygons(
        boundary
    )

    save_landuse_features(
        multipolygons
    )

    print("\n" + "=" * 60)
    print("LOCAL OSM PROCESSING COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()