import os
import geopandas as gpd


# ============================================================
# BENGALURU GRID → AREA MAPPING ENGINE
# ============================================================


# ============================================================
# PATH CONFIGURATION
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)


# IMPORTANT:
# Data is inside:
# UrbanPredictiveIntelligence/
#     waste_module/
#         data/

GRID_FILE = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "data",
    "bengaluru_grid.geojson"
)


AREA_FILE = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "data",
    "processed",
    "bengaluru_area_boundaries.gpkg"
)


OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "data",
    "processed"
)


OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bengaluru_grid_area_mapping.gpkg"
)


OUTPUT_CSV = os.path.join(
    OUTPUT_DIR,
    "bengaluru_grid_area_mapping.csv"
)


# ============================================================
# LOAD GRID
# ============================================================

def load_grid():

    print("\nLoading Bengaluru grid...")

    if not os.path.exists(GRID_FILE):

        raise FileNotFoundError(
            f"\nGrid file not found:\n{GRID_FILE}"
        )

    grid = gpd.read_file(
        GRID_FILE
    )

    print(
        f"Grid cells loaded: {len(grid):,}"
    )

    print(
        f"Grid CRS: {grid.crs}"
    )

    return grid


# ============================================================
# LOAD AREA BOUNDARIES
# ============================================================

def load_area_boundaries():

    print("\nLoading Bengaluru area boundaries...")

    if not os.path.exists(AREA_FILE):

        raise FileNotFoundError(
            f"\nArea boundary file not found:\n{AREA_FILE}"
        )

    areas = gpd.read_file(
        AREA_FILE
    )

    print(
        f"Areas loaded: {len(areas):,}"
    )

    print(
        f"Area CRS: {areas.crs}"
    )

    return areas


# ============================================================
# PREPARE CRS
# ============================================================

def prepare_crs(grid, areas):

    print(
        "\nPreparing coordinate systems..."
    )

    if grid.crs != areas.crs:

        print(
            "CRS mismatch detected."
        )

        areas = areas.to_crs(
            grid.crs
        )

    print(
        f"Working CRS: {grid.crs}"
    )

    return grid, areas


# ============================================================
# CREATE GRID REPRESENTATIVE POINTS
# ============================================================

def create_centroids(grid):

    print(
        "\nCreating grid representative points..."
    )

    grid = grid.copy()

    # Representative point is safer than centroid
    # because it remains inside the grid polygon.

    grid[
        "grid_point"
    ] = grid.geometry.representative_point()

    return grid


# ============================================================
# SPATIAL JOIN
# ============================================================

def map_grid_to_areas(grid, areas):

    print(
        "\nMapping grid cells to administrative areas..."
    )

    # --------------------------------------------------------
    # Copy grid
    # --------------------------------------------------------

    points = grid.copy()

    # Use representative points for mapping

    points = points.set_geometry(
        "grid_point"
    )

    # --------------------------------------------------------
    # Keep only required area fields
    #
    # Rename BEFORE spatial join to avoid collisions
    # with the grid's existing "name" column.
    # --------------------------------------------------------

    area_columns = areas[
        [
            "osm_id",
            "name",
            "admin_level",
            "geometry"
        ]
    ].copy()

    area_columns = area_columns.rename(
        columns={
            "osm_id": "area_osm_id",
            "name": "area_name",
            "admin_level": "area_admin_level"
        }
    )

    # --------------------------------------------------------
    # Spatial join
    # --------------------------------------------------------

    mapped = gpd.sjoin(
        points,
        area_columns,
        how="left",
        predicate="within"
    )

    # --------------------------------------------------------
    # Remove spatial join helper column
    # --------------------------------------------------------

    if "index_right" in mapped.columns:

        mapped = mapped.drop(
            columns=[
                "index_right"
            ]
        )

    # --------------------------------------------------------
    # Remove representative point
    # --------------------------------------------------------

    if "grid_point" in mapped.columns:

        mapped = mapped.drop(
            columns=[
                "grid_point"
            ]
        )

    return mapped


# ============================================================
# VALIDATE MAPPING
# ============================================================

def validate_mapping(mapped):

    print(
        "\nValidating grid-area mapping..."
    )

    # --------------------------------------------------------
    # Make sure area_name exists
    # --------------------------------------------------------

    if "area_name" not in mapped.columns:

        print(
            "\nERROR: area_name column was not created."
        )

        print(
            "\nAvailable columns:"
        )

        print(
            mapped.columns.tolist()
        )

        raise ValueError(
            "Spatial mapping did not create 'area_name'."
        )

    # --------------------------------------------------------
    # Total grid cells
    # --------------------------------------------------------

    total = len(
        mapped
    )

    # --------------------------------------------------------
    # Mapped cells
    # --------------------------------------------------------

    mapped_count = (
        mapped[
            "area_name"
        ]
        .notna()
        .sum()
    )

    # --------------------------------------------------------
    # Unmapped cells
    # --------------------------------------------------------

    unmapped_count = (
        mapped[
            "area_name"
        ]
        .isna()
        .sum()
    )

    print(
        f"Total grid cells: {total:,}"
    )

    print(
        f"Mapped grid cells: {mapped_count:,}"
    )

    print(
        f"Unmapped grid cells: {unmapped_count:,}"
    )

    # --------------------------------------------------------
    # Mapping coverage
    # --------------------------------------------------------

    if total > 0:

        percentage = (
            mapped_count
            /
            total
            *
            100
        )

        print(
            f"Mapping coverage: {percentage:.2f}%"
        )

    # --------------------------------------------------------
    # Grid cells per area
    # --------------------------------------------------------

    print(
        "\nGrid cells per area:"
    )

    counts = (
        mapped[
            mapped[
                "area_name"
            ].notna()
        ]
        [
            "area_name"
        ]
        .value_counts()
    )

    print(
        counts.head(20).to_string()
    )

    # --------------------------------------------------------
    # Unique areas
    # --------------------------------------------------------

    unique_areas = (
        mapped[
            "area_name"
        ]
        .dropna()
        .nunique()
    )

    print(
        f"\nUnique mapped areas: "
        f"{unique_areas:,}"
    )

    return mapped


# ============================================================
# SAVE MAPPING
# ============================================================

def save_mapping(mapped):

    print(
        "\nSaving grid-area mapping..."
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Save GeoPackage
    # --------------------------------------------------------

    mapped.to_file(
        OUTPUT_FILE,
        layer="grid_area_mapping",
        driver="GPKG"
    )

    print(
        "\nGeoPackage saved to:"
    )

    print(
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    csv_data = mapped.drop(
        columns="geometry",
        errors="ignore"
    )

    csv_data.to_csv(
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
# DISPLAY RESULTS
# ============================================================

def display_results(mapped):

    print(
        "\n"
        +
        "=" * 70
    )

    print(
        "GRID → AREA MAPPING RESULTS"
    )

    print(
        "=" * 70
    )

    display_columns = [
        "Grid_ID",
        "area_name",
        "area_osm_id",
        "area_admin_level"
    ]

    display_columns = [
        column
        for column in display_columns
        if column in mapped.columns
    ]

    print(
        "\nSample mapping:"
    )

    print(
        mapped[
            display_columns
        ]
        .head(30)
        .to_string(
            index=False
        )
    )

    print(
        "\n"
        +
        "=" * 70
    )

    print(
        "GRID → AREA MAPPING COMPLETED"
    )

    print(
        "=" * 70
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "BENGALURU GRID → AREA MAPPING ENGINE"
    )

    print(
        "=" * 70
    )

    # Step 1
    grid = load_grid()

    # Step 2
    areas = load_area_boundaries()

    # Step 3
    grid, areas = prepare_crs(
        grid,
        areas
    )

    # Step 4
    grid = create_centroids(
        grid
    )

    # Step 5
    mapped = map_grid_to_areas(
        grid,
        areas
    )

    # Step 6
    mapped = validate_mapping(
        mapped
    )

    # Step 7
    save_mapping(
        mapped
    )

    # Step 8
    display_results(
        mapped
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()