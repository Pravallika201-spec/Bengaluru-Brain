"""
=========================================================
Urban Predictive Intelligence System
Waste Generation Estimation Engine
=========================================================

Creates a baseline waste-generation estimate for each
Bengaluru grid cell using land-use characteristics.

The estimates are spatial proxies and are NOT claimed to
be official municipal waste measurements.
=========================================================
"""

from pathlib import Path

import geopandas as gpd


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_grid_features.gpkg"
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
    / "bengaluru_waste_estimates.gpkg"
)


# =========================================================
# BASELINE WASTE INTENSITY
# =========================================================

WASTE_INTENSITY = {

    "residential": 0.80,

    "commercial": 1.50,

    "industrial": 1.20,

    "institutional": 1.00,

    "green_space": 0.20,

    "agricultural": 0.30,

    "recreational": 1.10,

    "construction": 1.40,

    "transport": 1.00,

    "water": 0.05,

    "waste_utility": 0.50,

    "religious": 0.90,

    "military": 0.70,

    "other": 0.40,
}


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 65)
    print("BENGALURU WASTE GENERATION ESTIMATION ENGINE")
    print("=" * 65)

    # -----------------------------------------------------
    # Load grid features
    # -----------------------------------------------------

    print("\nLoading grid feature dataset...")

    grid = gpd.read_file(
        INPUT_FILE,
        layer="grid_features"
    )

    print(
        f"Grid cells loaded: {len(grid):,}"
    )

    # -----------------------------------------------------
    # Weighted waste intensity
    # -----------------------------------------------------

    print(
        "\nCalculating waste-generation intensity..."
    )

    grid["predicted_waste_intensity"] = 0.0

    for landuse, weight in WASTE_INTENSITY.items():

        ratio_column = (
            f"{landuse}_ratio"
        )

        if ratio_column in grid.columns:

            grid["predicted_waste_intensity"] += (
                grid[ratio_column].fillna(0)
                * weight
            )

    # -----------------------------------------------------
    # Normalize intensity
    # -----------------------------------------------------

    min_intensity = (
        grid["predicted_waste_intensity"].min()
    )

    max_intensity = (
        grid["predicted_waste_intensity"].max()
    )

    if max_intensity > min_intensity:

        grid["predicted_waste_intensity_normalized"] = (
            (
                grid["predicted_waste_intensity"]
                - min_intensity
            )
            /
            (
                max_intensity
                - min_intensity
            )
        )

    else:

        grid["predicted_waste_intensity_normalized"] = 0.0

    # -----------------------------------------------------
    # Estimate daily waste
    # -----------------------------------------------------

    print(
        "\nEstimating baseline daily waste..."
    )

    grid_area_km2 = (
        grid["grid_area_m2"]
        / 1_000_000
    )

    grid["estimated_daily_waste_kg"] = (
        grid_area_km2
        * grid["predicted_waste_intensity"]
        * 1000
    )

    grid["estimated_daily_waste_kg"] = (
        grid["estimated_daily_waste_kg"]
        .clip(lower=1)
    )

    # -----------------------------------------------------
    # New prediction score
    #
    # IMPORTANT:
    # We use a different name from the existing
    # Waste_Score field in your original grid.
    # -----------------------------------------------------

    grid["predicted_waste_score"] = (
        grid["predicted_waste_intensity_normalized"]
        * 100
    )

    # -----------------------------------------------------
    # Risk classification
    # -----------------------------------------------------

    def classify_risk(score):

        if score >= 75:
            return "Very High"

        elif score >= 50:
            return "High"

        elif score >= 25:
            return "Medium"

        else:
            return "Low"

    grid["predicted_waste_risk"] = (
        grid["predicted_waste_score"]
        .apply(classify_risk)
    )

    # -----------------------------------------------------
    # Collection priority
    # -----------------------------------------------------

    def calculate_priority(score):

        if score >= 75:
            return 1

        elif score >= 50:
            return 2

        elif score >= 25:
            return 3

        else:
            return 4

    grid["predicted_collection_priority"] = (
        grid["predicted_waste_score"]
        .apply(calculate_priority)
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    print(
        "\nSaving waste estimation dataset..."
    )

    grid.to_file(
        OUTPUT_FILE,
        layer="waste_estimates",
        driver="GPKG"
    )

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    print("\n" + "=" * 65)

    print("\nWaste statistics:")

    print(
        grid[
            [
                "estimated_daily_waste_kg",
                "predicted_waste_score"
            ]
        ].describe()
    )

    print("\nRisk distribution:")

    print(
        grid[
            "predicted_waste_risk"
        ].value_counts()
    )

    print("\nCollection priority distribution:")

    print(
        grid[
            "predicted_collection_priority"
        ]
        .value_counts()
        .sort_index()
    )

    print("\nOutput file:")

    print(OUTPUT_FILE)

    print("\n" + "=" * 65)
    print("WASTE ESTIMATION ENGINE COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()