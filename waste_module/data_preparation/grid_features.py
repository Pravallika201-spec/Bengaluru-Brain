"""
=========================================================
Urban Predictive Intelligence System
Bengaluru Grid Feature Engineering
=========================================================

Connects:
    Bengaluru Grid
        +
    OSM Land Use
        ↓
    Land-use area features
        ↓
    Land-use ratios
        ↓
    Dominant land use
=========================================================
"""

from pathlib import Path

import geopandas as gpd


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRID_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "bengaluru_grid.geojson"
)

LANDUSE_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_landuse.gpkg"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_grid_features.gpkg"
)


# =========================================================
# LAND-USE CATEGORIES
# =========================================================

LANDUSE_CLASSES = [
    "Residential",
    "Commercial",
    "Industrial",
    "Institutional",
    "Green_Space",
    "Agricultural",
    "Recreational",
    "Construction",
    "Transport",
    "Water",
    "Waste_Utility",
    "Religious",
    "Military",
    "Other",
]


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 65)
    print("BENGALURU GRID FEATURE ENGINE")
    print("=" * 65)

    # -----------------------------------------------------
    # Load grid
    # -----------------------------------------------------

    print("\nLoading Bengaluru grid...")

    grid = gpd.read_file(GRID_FILE)

    print(
        f"Grid cells: {len(grid):,}"
    )

    # -----------------------------------------------------
    # Verify Grid_ID
    # -----------------------------------------------------

    if "Grid_ID" not in grid.columns:

        raise ValueError(
            "Grid_ID column was not found in Bengaluru grid."
        )

    print(
        "Grid ID column found: Grid_ID"
    )

    # -----------------------------------------------------
    # Load land-use data
    # -----------------------------------------------------

    print("\nLoading classified land-use data...")

    landuse = gpd.read_file(
        LANDUSE_FILE,
        layer="landuse"
    )

    print(
        f"Land-use features: {len(landuse):,}"
    )

    # -----------------------------------------------------
    # Project to metric CRS
    # -----------------------------------------------------

    print(
        "\nProjecting data for area calculations..."
    )

    grid = grid.to_crs(32643)

    landuse = landuse.to_crs(32643)

    # Calculate grid area

    grid["grid_area_m2"] = (
        grid.geometry.area
    )

    # -----------------------------------------------------
    # Spatial intersection
    # -----------------------------------------------------

    print(
        "\nIntersecting grid with land use..."
    )

    intersection = gpd.overlay(
        grid[
            [
                "Grid_ID",
                "geometry"
            ]
        ],
        landuse[
            [
                "landuse_class",
                "geometry"
            ]
        ],
        how="intersection",
        keep_geom_type=True
    )

    print(
        f"Intersection features: "
        f"{len(intersection):,}"
    )

    # -----------------------------------------------------
    # Calculate intersection area
    # -----------------------------------------------------

    print(
        "\nCalculating land-use areas..."
    )

    intersection["area_m2"] = (
        intersection.geometry.area
    )

    # -----------------------------------------------------
    # Group by Grid_ID
    # -----------------------------------------------------

    grouped = (
        intersection
        .groupby(
            [
                "Grid_ID",
                "landuse_class"
            ],
            as_index=False
        )[
            "area_m2"
        ]
        .sum()
    )

    # -----------------------------------------------------
    # Convert to wide format
    # -----------------------------------------------------

    pivot = grouped.pivot(
        index="Grid_ID",
        columns="landuse_class",
        values="area_m2"
    )

    pivot = pivot.fillna(0)

    pivot = pivot.reset_index()

    # -----------------------------------------------------
    # Ensure every category exists
    # -----------------------------------------------------

    for category in LANDUSE_CLASSES:

        if category not in pivot.columns:

            pivot[category] = 0.0

    # -----------------------------------------------------
    # Rename area columns
    # -----------------------------------------------------

    area_columns = {}

    for category in LANDUSE_CLASSES:

        area_columns[category] = (
            f"{category.lower()}_area_m2"
        )

    pivot = pivot.rename(
        columns=area_columns
    )

    # -----------------------------------------------------
    # Merge with original grid
    # -----------------------------------------------------

    print(
        "\nMerging land-use features with grid..."
    )

    grid = grid.merge(
        pivot,
        on="Grid_ID",
        how="left"
    )

    # -----------------------------------------------------
    # Fill missing values
    # -----------------------------------------------------

    for category in LANDUSE_CLASSES:

        column = (
            f"{category.lower()}_area_m2"
        )

        grid[column] = (
            grid[column]
            .fillna(0)
        )

    # -----------------------------------------------------
    # Calculate ratios
    # -----------------------------------------------------

    print(
        "\nCalculating land-use ratios..."
    )

    for category in LANDUSE_CLASSES:

        area_column = (
            f"{category.lower()}_area_m2"
        )

        ratio_column = (
            f"{category.lower()}_ratio"
        )

        grid[ratio_column] = (
            grid[area_column]
            / grid["grid_area_m2"]
        )

    # -----------------------------------------------------
    # Determine dominant land use
    # -----------------------------------------------------

    ratio_columns = [
        f"{category.lower()}_ratio"
        for category in LANDUSE_CLASSES
    ]

    grid["dominant_landuse"] = (
        grid[ratio_columns]
        .idxmax(axis=1)
        .str.replace(
            "_ratio",
            "",
            regex=False
        )
    )

    # -----------------------------------------------------
    # Waste-relevant intensity features
    # -----------------------------------------------------

    grid["commercial_intensity"] = (
        grid["commercial_ratio"]
    )

    grid["residential_intensity"] = (
        grid["residential_ratio"]
    )

    grid["industrial_intensity"] = (
        grid["industrial_ratio"]
    )

    grid["institutional_intensity"] = (
        grid["institutional_ratio"]
    )

    grid["recreational_intensity"] = (
        grid["recreational_ratio"]
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    print(
        "\nSaving grid feature dataset..."
    )

    grid.to_file(
        OUTPUT_FILE,
        layer="grid_features",
        driver="GPKG"
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print(
        "\nDominant land-use distribution:"
    )

    print(
        grid["dominant_landuse"]
        .value_counts()
    )

    print(
        "\nFinal feature count:"
    )

    print(
        len(grid.columns),
        "columns"
    )

    print(
        "\nSaved successfully:"
    )

    print(
        OUTPUT_FILE
    )

    print("\n" + "=" * 65)
    print("GRID FEATURE ENGINE COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()