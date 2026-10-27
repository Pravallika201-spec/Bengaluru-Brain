"""
Land Use Intelligence Engine
Urban Predictive Intelligence System
"""

import geopandas as gpd
import pandas as pd
import osmnx as ox

from waste_module.config import (
    GRID_GEOJSON,
    LANDUSE_OUTPUT,
)


def load_grid():
    print("Loading Urban Digital Mesh...")
    return gpd.read_file(GRID_GEOJSON)


def download_landuse():
    print("Downloading Bengaluru land-use data from OpenStreetMap...")

    tags = {
        "landuse": True,
        "leisure": True,
        "amenity": True,
    }

    gdf = ox.features_from_place(
        "Bengaluru, Karnataka, India",
        tags=tags
    )

    return gdf


def main():

    grid = load_grid()

    landuse = download_landuse()

    print(f"Grid Cells      : {len(grid):,}")
    print(f"OSM Features    : {len(landuse):,}")

    landuse.to_file("waste_module/data/osm_landuse.geojson",
                    driver="GeoJSON")

    pd.DataFrame(landuse.drop(columns="geometry")).to_csv(
        LANDUSE_OUTPUT,
        index=False
    )

    print("\nLand-use data downloaded successfully!")


if __name__ == "__main__":
    main()