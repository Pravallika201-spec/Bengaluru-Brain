import os
import pandas as pd
import geopandas as gpd


# =========================================================
# FILE PATHS
# =========================================================

SATELLITE_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_features.csv"
)

WASTE_FILE = (
    "waste_module/data/processed/"
    "bengaluru_waste_estimates.gpkg"
)

OUTPUT_DIR = (
    "waste_module/satellite/outputs"
)

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_waste_dataset.csv"
)


# =========================================================
# LOAD SATELLITE DATA
# =========================================================

def load_satellite_data():

    print("\nLoading satellite dataset...")

    if not os.path.exists(SATELLITE_FILE):

        raise FileNotFoundError(
            f"\nSatellite dataset was not found:\n"
            f"{SATELLITE_FILE}"
        )

    satellite = pd.read_csv(
        SATELLITE_FILE
    )

    print(
        "Satellite rows:",
        len(satellite)
    )

    print(
        "Satellite columns:"
    )

    print(
        satellite.columns.tolist()
    )

    return satellite


# =========================================================
# LOAD WASTE DATA
# =========================================================

def load_waste_data():

    print(
        "\nLoading waste estimation dataset..."
    )

    if not os.path.exists(WASTE_FILE):

        raise FileNotFoundError(
            f"\nWaste dataset was not found:\n"
            f"{WASTE_FILE}"
        )

    waste = gpd.read_file(
        WASTE_FILE
    )

    print(
        "Waste rows:",
        len(waste)
    )

    print(
        "Waste columns:"
    )

    print(
        waste.columns.tolist()
    )

    return waste


# =========================================================
# PREPARE GRID IDs
# =========================================================

def prepare_grid_id(
    satellite,
    waste
):

    print(
        "\nPreparing Grid_ID values..."
    )

    if "Grid_ID" not in satellite.columns:

        raise ValueError(
            "Grid_ID is missing from "
            "the satellite dataset."
        )

    if "Grid_ID" not in waste.columns:

        raise ValueError(
            "Grid_ID is missing from "
            "the waste dataset."
        )

    satellite["Grid_ID"] = (
        satellite["Grid_ID"]
        .astype(str)
        .str.strip()
    )

    waste["Grid_ID"] = (
        waste["Grid_ID"]
        .astype(str)
        .str.strip()
    )

    print(
        "Grid_ID preparation completed."
    )

    return satellite, waste


# =========================================================
# CHECK DUPLICATE GRID IDs
# =========================================================

def check_duplicates(
    satellite,
    waste
):

    print(
        "\nChecking duplicate Grid_ID values..."
    )

    satellite_duplicates = (
        satellite["Grid_ID"]
        .duplicated()
        .sum()
    )

    waste_duplicates = (
        waste["Grid_ID"]
        .duplicated()
        .sum()
    )

    print(
        "Satellite duplicate Grid_IDs:",
        satellite_duplicates
    )

    print(
        "Waste duplicate Grid_IDs:",
        waste_duplicates
    )

    if satellite_duplicates > 0:

        raise ValueError(
            "Duplicate Grid_ID values found "
            "in satellite dataset."
        )

    if waste_duplicates > 0:

        raise ValueError(
            "Duplicate Grid_ID values found "
            "in waste dataset."
        )


# =========================================================
# MERGE DATASETS
# =========================================================

def merge_datasets(
    satellite,
    waste
):

    print(
        "\nMerging satellite and waste datasets..."
    )

    merged = satellite.merge(
        waste,
        on="Grid_ID",
        how="left",
        suffixes=(
            "_satellite",
            "_waste"
        )
    )

    print(
        "Merged rows:",
        len(merged)
    )

    return merged


# =========================================================
# CHECK MERGE QUALITY
# =========================================================

def check_merge_quality(
    merged
):

    print(
        "\nChecking merge quality..."
    )

    total_rows = len(
        merged
    )

    if total_rows == 0:

        raise ValueError(
            "Merged dataset contains "
            "zero rows."
        )

    # Check whether waste information
    # successfully matched.

    possible_columns = [
        "predicted_daily_waste_kg",
        "waste_score",
        "Waste_Score",
        "Overflow_Risk",
        "collection_priority"
    ]

    found_columns = []

    for column in possible_columns:

        if column in merged.columns:

            found_columns.append(
                column
            )

    if found_columns:

        print(
            "\nWaste-related columns found:"
        )

        for column in found_columns:

            missing = (
                merged[column]
                .isna()
                .sum()
            )

            available = (
                total_rows - missing
            )

            print(
                f"{column}: "
                f"{available}/{total_rows} "
                f"available"
            )

    else:

        print(
            "\nWarning: No standard waste "
            "columns were detected."
        )


# =========================================================
# CHECK SATELLITE FEATURES
# =========================================================

def check_satellite_features(
    merged
):

    print(
        "\nChecking satellite features..."
    )

    expected_features = [
        "B2",
        "B3",
        "B4",
        "B8",
        "B11",
        "B12",
        "NDVI",
        "NDBI",
        "NDWI"
    ]

    print(
        "\nSatellite feature availability:"
    )

    for feature in expected_features:

        if feature in merged.columns:

            missing = (
                merged[feature]
                .isna()
                .sum()
            )

            available = (
                len(merged) - missing
            )

            print(
                f"{feature}: "
                f"{available}/{len(merged)} "
                f"available"
            )

        else:

            print(
                f"{feature}: NOT FOUND"
            )


# =========================================================
# DISPLAY DATASET SUMMARY
# =========================================================

def display_summary(
    merged
):

    print(
        "\nDataset summary:"
    )

    print(
        "Total grid cells:",
        len(merged)
    )

    print(
        "Total columns:",
        len(merged.columns)
    )

    print(
        "\nFirst 5 rows:"
    )

    # Display only a useful subset
    # if the columns exist.

    preferred_columns = [
        "Grid_ID",
        "B2",
        "B3",
        "B4",
        "B8",
        "B11",
        "B12",
        "NDVI",
        "NDBI",
        "NDWI",
        "predicted_daily_waste_kg",
        "waste_score",
        "Waste_Score"
    ]

    display_columns = [
        column
        for column in preferred_columns
        if column in merged.columns
    ]

    if display_columns:

        print(
            merged[
                display_columns
            ].head()
        )

    else:

        print(
            merged.head()
        )


# =========================================================
# SAVE DATASET
# =========================================================

def save_dataset(
    merged
):

    print(
        "\nSaving satellite-waste dataset..."
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    merged.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nDataset saved successfully:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "Rows:",
        len(merged)
    )

    print(
        "Columns:",
        len(merged.columns)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU SATELLITE + WASTE "
        "DATA FUSION ENGINE"
    )

    print("=" * 60)

    # -----------------------------------------------------
    # STEP 1
    # Load satellite dataset
    # -----------------------------------------------------

    satellite = (
        load_satellite_data()
    )

    # -----------------------------------------------------
    # STEP 2
    # Load existing waste dataset
    # -----------------------------------------------------

    waste = (
        load_waste_data()
    )

    # -----------------------------------------------------
    # STEP 3
    # Prepare Grid_ID
    # -----------------------------------------------------

    satellite, waste = (
        prepare_grid_id(
            satellite,
            waste
        )
    )

    # -----------------------------------------------------
    # STEP 4
    # Check duplicates
    # -----------------------------------------------------

    check_duplicates(
        satellite,
        waste
    )

    # -----------------------------------------------------
    # STEP 5
    # Merge
    # -----------------------------------------------------

    merged = (
        merge_datasets(
            satellite,
            waste
        )
    )

    # -----------------------------------------------------
    # STEP 6
    # Check merge quality
    # -----------------------------------------------------

    check_merge_quality(
        merged
    )

    # -----------------------------------------------------
    # STEP 7
    # Check satellite features
    # -----------------------------------------------------

    check_satellite_features(
        merged
    )

    # -----------------------------------------------------
    # STEP 8
    # Display summary
    # -----------------------------------------------------

    display_summary(
        merged
    )

    # -----------------------------------------------------
    # STEP 9
    # Save final dataset
    # -----------------------------------------------------

    save_dataset(
        merged
    )

    # -----------------------------------------------------
    # COMPLETE
    # -----------------------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    print(
        "SATELLITE + WASTE FUSION COMPLETED"
    )

    print(
        "=" * 60
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()