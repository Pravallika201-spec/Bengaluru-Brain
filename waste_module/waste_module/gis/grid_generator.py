import numpy as np
import geopandas as gpd
import pandas as pd

from shapely.geometry import box

from waste_module.config import (
    BOUNDARY_FILE,
    PROJECTED_CRS,
    GRID_SIZE_METERS,
    GRID_GEOJSON,
    GRID_CSV
)


def generate_urban_mesh():

    print("\nLoading Bengaluru boundary...")

    boundary = gpd.read_file(BOUNDARY_FILE)

    boundary = boundary.to_crs(PROJECTED_CRS)

    minx, miny, maxx, maxy = boundary.total_bounds

    print("Generating base grid...")

    polygons = []

    x_coords = np.arange(minx, maxx, GRID_SIZE_METERS)
    y_coords = np.arange(miny, maxy, GRID_SIZE_METERS)

    for x in x_coords:
        for y in y_coords:

            polygons.append(
                box(
                    x,
                    y,
                    x + GRID_SIZE_METERS,
                    y + GRID_SIZE_METERS
                )
            )

    grid = gpd.GeoDataFrame(
        geometry=polygons,
        crs=PROJECTED_CRS
    )

    print(f"Base Grid : {len(grid):,} cells")

    print("Clipping to Bengaluru boundary...")

    clipped = gpd.overlay(
        grid,
        boundary,
        how="intersection"
    )

    clipped = clipped.reset_index(drop=True)

    print(f"Remaining Cells : {len(clipped):,}")

    clipped["Grid_ID"] = [
        f"BG_{i:06d}"
        for i in range(1, len(clipped)+1)
    ]

    centroids = clipped.geometry.centroid

    clipped["Latitude"] = centroids.to_crs(4326).y

    clipped["Longitude"] = centroids.to_crs(4326).x

    clipped["Waste_Score"] = 0

    clipped["Overflow_Risk"] = 0

    clipped["Priority"] = 0

    clipped["Truck_ID"] = ""

    clipped["Status"] = "Pending"

    clipped.to_file(
        GRID_GEOJSON,
        driver="GeoJSON"
    )

    df = pd.DataFrame(clipped.drop(columns="geometry"))

    df.to_csv(
        GRID_CSV,
        index=False
    )

    print("\nUrban Digital Mesh Created Successfully!")

    print(f"GeoJSON : {GRID_GEOJSON}")

    print(f"CSV : {GRID_CSV}")