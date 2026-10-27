import os
import geopandas as gpd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

OSM_FILE = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "data",
    "osm",
    "bengaluru_osm_multipolygons.gpkg"
)

OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "data",
    "processed"
)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bengaluru_area_boundaries.gpkg"
)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BENGALURU AREA BOUNDARY EXTRACTION")
    print("=" * 70)

    print("\nLoading OSM multipolygons...")

    gdf = gpd.read_file(
        OSM_FILE,
        layer="multipolygons"
    )

    print(f"Total OSM features: {len(gdf):,}")

    # --------------------------------------------------------
    # Select administrative level 10 boundaries
    # --------------------------------------------------------

    areas = gdf[
        (gdf["boundary"] == "administrative") &
        (gdf["admin_level"].astype(str) == "10") &
        (gdf["name"].notna())
    ].copy()

    print(
        f"Administrative level 10 areas found: "
        f"{len(areas)}"
    )

    # --------------------------------------------------------
    # Keep required columns
    # --------------------------------------------------------

    areas = areas[
        [
            "osm_id",
            "name",
            "boundary",
            "admin_level",
            "geometry"
        ]
    ]

    # --------------------------------------------------------
    # Remove duplicate names
    # --------------------------------------------------------

    areas = areas.drop_duplicates(
        subset=["osm_id"]
    )

    # --------------------------------------------------------
    # Fix geometries
    # --------------------------------------------------------

    print("\nChecking geometries...")

    invalid = (~areas.geometry.is_valid).sum()

    print(
        f"Invalid geometries: {invalid}"
    )

    if invalid > 0:

        areas["geometry"] = (
            areas.geometry.make_valid()
        )

    # --------------------------------------------------------
    # CRS
    # --------------------------------------------------------

    print(
        f"CRS: {areas.crs}"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    areas.to_file(
        OUTPUT_FILE,
        layer="areas",
        driver="GPKG"
    )

    print("\nSaved area boundaries:")
    print(OUTPUT_FILE)

    print("\nSample areas:")

    print(
        areas[
            ["osm_id", "name", "admin_level"]
        ]
        .sort_values("name")
        .head(30)
        .to_string(index=False)
    )

    print("\n" + "=" * 70)
    print("AREA BOUNDARY EXTRACTION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
    