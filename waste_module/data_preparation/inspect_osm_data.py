"""
Inspect extracted Bengaluru OSM data.

This script checks which OSM tags are actually present
before we build the land-use classification engine.
"""

import geopandas as gpd

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OSM_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "osm"
    / "bengaluru_osm_multipolygons.gpkg"
)


def main():

    print("=" * 60)
    print("BENGALURU OSM DATA INSPECTION")
    print("=" * 60)

    print("\nLoading extracted OSM data...")

    gdf = gpd.read_file(
        OSM_FILE,
        layer="multipolygons"
    )

    print(f"\nTotal features: {len(gdf):,}")

    print("\nColumns available:")
    print("-" * 40)

    for column in gdf.columns:
        print(column)

    print("\n" + "=" * 60)
    print("LANDUSE VALUES")
    print("=" * 60)

    if "landuse" in gdf.columns:

        print(
            gdf["landuse"]
            .value_counts(dropna=True)
            .head(30)
        )

    else:

        print("No 'landuse' column found.")

    print("\n" + "=" * 60)
    print("LEISURE VALUES")
    print("=" * 60)

    if "leisure" in gdf.columns:

        print(
            gdf["leisure"]
            .value_counts(dropna=True)
            .head(30)
        )

    else:

        print("No 'leisure' column found.")

    print("\n" + "=" * 60)
    print("AMENITY VALUES")
    print("=" * 60)

    if "amenity" in gdf.columns:

        print(
            gdf["amenity"]
            .value_counts(dropna=True)
            .head(30)
        )

    else:

        print("No 'amenity' column found.")

    print("\nInspection completed.")


if __name__ == "__main__":
    main()