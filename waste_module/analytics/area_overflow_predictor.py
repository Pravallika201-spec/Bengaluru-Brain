"""
============================================================
BENGALURU AREA-LEVEL OVERFLOW RISK PREDICTOR
============================================================

Input:
    bengaluru_temporal_predictions.gpkg
    bengaluru_grid_area_mapping.csv
    bengaluru_area_boundaries.gpkg

Output:
    bengaluru_area_overflow_predictions.csv
    bengaluru_area_overflow_predictions.gpkg

Purpose:
    Convert grid-level temporal waste predictions into
    area-level overflow-risk intelligence.
============================================================
"""

import os
import numpy as np
import pandas as pd
import geopandas as gpd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

PROCESSED_DIR = os.path.join(
    BASE_DIR,
    "waste_module",
    "data",
    "processed"
)

TEMPORAL_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_temporal_predictions.gpkg"
)

MAPPING_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_grid_area_mapping.csv"
)

BOUNDARIES_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_boundaries.gpkg"
)

OUTPUT_CSV = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_overflow_predictions.csv"
)

OUTPUT_GPKG = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_overflow_predictions.gpkg"
)


# ============================================================
# LOAD TEMPORAL PREDICTIONS
# ============================================================

def load_temporal_predictions():

    print("\nLoading temporal waste predictions...")

    if not os.path.exists(TEMPORAL_FILE):
        raise FileNotFoundError(
            f"\nTemporal prediction file not found:\n"
            f"{TEMPORAL_FILE}"
        )

    gdf = gpd.read_file(
        TEMPORAL_FILE,
        layer="temporal_predictions"
    )

    print(
        f"Prediction rows: {len(gdf):,}"
    )

    print(
        f"Unique grid cells: "
        f"{gdf['Grid_ID'].nunique():,}"
    )

    return gdf


# ============================================================
# LOAD GRID → AREA MAPPING
# ============================================================

def load_area_mapping():

    print("\nLoading grid-area mapping...")

    if not os.path.exists(MAPPING_FILE):
        raise FileNotFoundError(
            f"\nGrid-area mapping not found:\n"
            f"{MAPPING_FILE}"
        )

    mapping = pd.read_csv(
        MAPPING_FILE
    )

    print(
        f"Mapping rows: {len(mapping):,}"
    )

    print(
        f"Unique areas: "
        f"{mapping['area_name'].nunique():,}"
    )

    required_columns = [
        "Grid_ID",
        "area_osm_id",
        "area_name",
        "area_admin_level"
    ]

    missing = [
        col
        for col in required_columns
        if col not in mapping.columns
    ]

    if missing:
        raise ValueError(
            "\nMissing columns in grid-area mapping:\n"
            + "\n".join(missing)
        )

    mapping = mapping[
        required_columns
    ].copy()

    # --------------------------------------------------------
    # IMPORTANT:
    # Normalize area_osm_id.
    #
    # CSV files commonly load numeric OSM IDs as strings,
    # while GeoPackages may load them as integers.
    # --------------------------------------------------------

    mapping["area_osm_id"] = pd.to_numeric(
        mapping["area_osm_id"],
        errors="coerce"
    )

    mapping = mapping.dropna(
        subset=["area_osm_id"]
    )

    mapping["area_osm_id"] = (
        mapping["area_osm_id"]
        .astype("int64")
    )

    mapping["area_admin_level"] = pd.to_numeric(
        mapping["area_admin_level"],
        errors="coerce"
    )

    mapping = mapping.drop_duplicates(
        subset=["Grid_ID"]
    )

    return mapping


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_data(predictions, mapping):

    print(
        "\nPreparing prediction data..."
    )

    required_columns = [
        "Grid_ID",
        "prediction_date",
        "predicted_daily_waste_kg",
        "temporal_waste_score",
        "predicted_waste_risk",
        "predicted_collection_priority"
    ]

    missing = [
        col
        for col in required_columns
        if col not in predictions.columns
    ]

    if missing:

        raise ValueError(
            "\nMissing required columns:\n"
            + "\n".join(missing)
        )

    predictions = predictions[
        required_columns
    ].copy()

    predictions["prediction_date"] = pd.to_datetime(
        predictions["prediction_date"],
        errors="coerce"
    )

    predictions[
        "predicted_daily_waste_kg"
    ] = pd.to_numeric(
        predictions["predicted_daily_waste_kg"],
        errors="coerce"
    )

    predictions[
        "temporal_waste_score"
    ] = pd.to_numeric(
        predictions["temporal_waste_score"],
        errors="coerce"
    )

    predictions = predictions.dropna(
        subset=[
            "Grid_ID",
            "prediction_date",
            "predicted_daily_waste_kg",
            "temporal_waste_score"
        ]
    )

    print(
        f"Valid prediction rows: "
        f"{len(predictions):,}"
    )

    print(
        f"Prediction dates: "
        f"{predictions['prediction_date'].min().date()} "
        f"to "
        f"{predictions['prediction_date'].max().date()}"
    )

    # --------------------------------------------------------
    # Normalize Grid_ID
    # --------------------------------------------------------

    predictions["Grid_ID"] = (
        predictions["Grid_ID"]
        .astype(str)
        .str.strip()
    )

    mapping["Grid_ID"] = (
        mapping["Grid_ID"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    print(
        "\nMerging predictions with administrative areas..."
    )

    merged = predictions.merge(
        mapping,
        on="Grid_ID",
        how="left"
    )

    unmatched = merged[
        "area_name"
    ].isna().sum()

    print(
        f"Merged rows: {len(merged):,}"
    )

    print(
        f"Matched predictions: "
        f"{len(merged) - unmatched:,}"
    )

    print(
        f"Unmatched predictions: "
        f"{unmatched:,}"
    )

    if unmatched > 0:

        raise ValueError(
            "Some grid predictions could not be mapped "
            "to an administrative area."
        )

    return merged


# ============================================================
# CALCULATE AREA FEATURES
# ============================================================

def calculate_area_features(data):

    print(
        "\nCalculating area-level temporal features..."
    )

    grouped = (
        data
        .groupby(
            [
                "area_osm_id",
                "area_name",
                "area_admin_level",
                "prediction_date"
            ],
            as_index=False
        )
        .agg(
            Grid_Cell_Count=(
                "Grid_ID",
                "nunique"
            ),

            Total_Predicted_Waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),

            Average_Predicted_Waste_kg=(
                "predicted_daily_waste_kg",
                "mean"
            ),

            Maximum_Predicted_Waste_kg=(
                "predicted_daily_waste_kg",
                "max"
            ),

            Average_Temporal_Score=(
                "temporal_waste_score",
                "mean"
            ),

            Maximum_Temporal_Score=(
                "temporal_waste_score",
                "max"
            )
        )
    )

    return grouped


# ============================================================
# CALCULATE OVERFLOW RISK
# ============================================================

def calculate_overflow_risk(data):

    print(
        "\nCalculating area-level overflow risk..."
    )

    # --------------------------------------------------------
    # Normalize waste within each prediction date
    # --------------------------------------------------------

    data["Waste_Percentage"] = (
        data.groupby("prediction_date")
        ["Total_Predicted_Waste_kg"]
        .transform(
            lambda x:
            x.rank(
                pct=True
            ) * 100
        )
    )

    # --------------------------------------------------------
    # Normalize temporal score
    # --------------------------------------------------------

    data["Score_Percentage"] = (
        data.groupby("prediction_date")
        ["Average_Temporal_Score"]
        .transform(
            lambda x:
            x.rank(
                pct=True
            ) * 100
        )
    )

    # --------------------------------------------------------
    # Normalize peak waste
    # --------------------------------------------------------

    data["Peak_Percentage"] = (
        data.groupby("prediction_date")
        ["Maximum_Predicted_Waste_kg"]
        .transform(
            lambda x:
            x.rank(
                pct=True
            ) * 100
        )
    )

    # --------------------------------------------------------
    # Composite overflow index
    #
    # Waste      = 50%
    # Peak waste = 30%
    # Score      = 20%
    # --------------------------------------------------------

    data["Overflow_Index"] = (
        0.50 * data["Waste_Percentage"]
        +
        0.30 * data["Peak_Percentage"]
        +
        0.20 * data["Score_Percentage"]
    )

    # --------------------------------------------------------
    # Risk classification
    # --------------------------------------------------------

    def classify_risk(value):

        if value >= 85:
            return "CRITICAL"

        elif value >= 65:
            return "HIGH"

        elif value >= 40:
            return "MEDIUM"

        else:
            return "LOW"

    data["Area_Overflow_Risk"] = (
        data["Overflow_Index"]
        .apply(classify_risk)
    )

    # --------------------------------------------------------
    # Numeric risk score
    # --------------------------------------------------------

    data["Overflow_Risk_Score"] = (
        data["Overflow_Index"]
        .round(2)
    )

    return data


# ============================================================
# CALCULATE COLLECTION PRIORITY
# ============================================================

def calculate_collection_priority(data):

    print(
        "\nCalculating collection priority..."
    )

    def priority(row):

        risk = row["Area_Overflow_Risk"]
        waste = row["Waste_Percentage"]

        if risk == "CRITICAL":
            return "URGENT"

        if risk == "HIGH":
            return "HIGH"

        if risk == "MEDIUM":

            if waste >= 60:
                return "HIGH"

            return "MEDIUM"

        return "LOW"

    data["Collection_Priority"] = (
        data.apply(
            priority,
            axis=1
        )
    )

    return data


# ============================================================
# AREA RANKING
# ============================================================

def calculate_area_rank(data):

    print(
        "\nCalculating area rankings..."
    )

    data["Waste_Rank"] = (
        data.groupby("prediction_date")
        ["Total_Predicted_Waste_kg"]
        .rank(
            ascending=False,
            method="dense"
        )
        .astype(int)
    )

    return data


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(data):

    print(
        "\nSaving area-level overflow predictions..."
    )

    output = data.copy()

    output = output.sort_values(
        [
            "prediction_date",
            "Waste_Rank"
        ]
    )

    output.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print(
        f"\nCSV saved to:\n"
        f"{OUTPUT_CSV}"
    )


# ============================================================
# CREATE AREA GEOMETRY
# ============================================================

def create_area_geodata(data):

    print(
        "\nCreating area-level GeoPackage..."
    )

    if not os.path.exists(BOUNDARIES_FILE):

        raise FileNotFoundError(
            f"\nArea boundaries file not found:\n"
            f"{BOUNDARIES_FILE}"
        )

    boundaries = gpd.read_file(
        BOUNDARIES_FILE
    )

    print(
        f"Boundary areas loaded: "
        f"{len(boundaries):,}"
    )

    # --------------------------------------------------------
    # Keep required boundary columns
    # --------------------------------------------------------

    boundaries = boundaries[
        [
            "osm_id",
            "name",
            "admin_level",
            "geometry"
        ]
    ].copy()

    boundaries = boundaries.rename(
        columns={
            "osm_id": "area_osm_id",
            "name": "area_name",
            "admin_level": "area_admin_level"
        }
    )

    # ========================================================
    # IMPORTANT FIX
    # ========================================================
    #
    # The previous error was:
    #
    # ValueError:
    # You are trying to merge on str and int64 columns
    # for key 'area_osm_id'
    #
    # Force BOTH dataframes to use int64.
    # ========================================================

    print(
        "\nNormalizing area OSM IDs..."
    )

    boundaries["area_osm_id"] = pd.to_numeric(
        boundaries["area_osm_id"],
        errors="coerce"
    )

    data["area_osm_id"] = pd.to_numeric(
        data["area_osm_id"],
        errors="coerce"
    )

    boundaries = boundaries.dropna(
        subset=["area_osm_id"]
    )

    data = data.dropna(
        subset=["area_osm_id"]
    )

    boundaries["area_osm_id"] = (
        boundaries["area_osm_id"]
        .astype("int64")
    )

    data["area_osm_id"] = (
        data["area_osm_id"]
        .astype("int64")
    )

    # --------------------------------------------------------
    # Normalize area names
    # --------------------------------------------------------

    boundaries["area_name"] = (
        boundaries["area_name"]
        .astype(str)
        .str.strip()
    )

    data["area_name"] = (
        data["area_name"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Normalize admin level
    # --------------------------------------------------------

    boundaries["area_admin_level"] = pd.to_numeric(
        boundaries["area_admin_level"],
        errors="coerce"
    )

    data["area_admin_level"] = pd.to_numeric(
        data["area_admin_level"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Latest prediction day
    # --------------------------------------------------------

    latest_date = data[
        "prediction_date"
    ].max()

    latest = data[
        data["prediction_date"] == latest_date
    ].copy()

    print(
        f"Latest prediction date: "
        f"{latest_date.date()}"
    )

    print(
        f"Latest area predictions: "
        f"{len(latest):,}"
    )

    # --------------------------------------------------------
    # Check key compatibility
    # --------------------------------------------------------

    print(
        "\nMerge key types:"
    )

    print(
        f"  Boundary area_osm_id: "
        f"{boundaries['area_osm_id'].dtype}"
    )

    print(
        f"  Prediction area_osm_id: "
        f"{latest['area_osm_id'].dtype}"
    )

    # --------------------------------------------------------
    # Merge boundaries with latest predictions
    # --------------------------------------------------------

    result = boundaries.merge(
        latest,
        on=[
            "area_osm_id",
            "area_name",
            "area_admin_level"
        ],
        how="left",
        suffixes=(
            "_boundary",
            ""
        )
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    matched = (
        result["Total_Predicted_Waste_kg"]
        .notna()
        .sum()
    )

    unmatched = (
        result["Total_Predicted_Waste_kg"]
        .isna()
        .sum()
    )

    print(
        f"\nBoundary areas: {len(boundaries):,}"
    )

    print(
        f"Areas with predictions: {matched:,}"
    )

    print(
        f"Areas without predictions: {unmatched:,}"
    )

    # --------------------------------------------------------
    # Keep only areas with predictions
    # --------------------------------------------------------

    result = result[
        result["Total_Predicted_Waste_kg"]
        .notna()
    ].copy()

    # --------------------------------------------------------
    # Re-create GeoDataFrame explicitly
    # --------------------------------------------------------

    result = gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=boundaries.crs
    )

    # --------------------------------------------------------
    # Remove existing output if present
    # --------------------------------------------------------

    if os.path.exists(OUTPUT_GPKG):

        try:
            os.remove(
                OUTPUT_GPKG
            )

        except PermissionError:

            print(
                "\nWARNING:"
            )

            print(
                "Existing GeoPackage is currently "
                "being used by another program."
            )

            raise

    # --------------------------------------------------------
    # Save GeoPackage
    # --------------------------------------------------------

    result.to_file(
        OUTPUT_GPKG,
        layer="area_overflow_predictions",
        driver="GPKG"
    )

    print(
        f"\nGeoPackage saved to:\n"
        f"{OUTPUT_GPKG}"
    )

    return result


# ============================================================
# DISPLAY RESULTS
# ============================================================

def display_results(data):

    latest_date = data[
        "prediction_date"
    ].max()

    latest = data[
        data["prediction_date"] == latest_date
    ].copy()

    latest = latest.sort_values(
        "Total_Predicted_Waste_kg",
        ascending=False
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "AREA-LEVEL OVERFLOW INTELLIGENCE"
    )

    print(
        "=" * 70
    )

    print(
        f"\nPrediction date: "
        f"{latest_date.date()}"
    )

    print(
        f"\nTotal administrative areas: "
        f"{latest['area_name'].nunique():,}"
    )

    # --------------------------------------------------------
    # Risk distribution
    # --------------------------------------------------------

    print(
        "\nOverflow risk distribution:"
    )

    print(
        latest[
            "Area_Overflow_Risk"
        ]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------------
    # Collection priority
    # --------------------------------------------------------

    print(
        "\nCollection priority:"
    )

    print(
        latest[
            "Collection_Priority"
        ]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------------
    # Top areas
    # --------------------------------------------------------

    print(
        "\nTop 20 areas by predicted waste:"
    )

    display_columns = [
        "area_name",
        "Grid_Cell_Count",
        "Total_Predicted_Waste_kg",
        "Average_Predicted_Waste_kg",
        "Maximum_Predicted_Waste_kg",
        "Average_Temporal_Score",
        "Overflow_Risk_Score",
        "Area_Overflow_Risk",
        "Collection_Priority",
        "Waste_Rank"
    ]

    print(
        latest[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )

    # --------------------------------------------------------
    # Total waste
    # --------------------------------------------------------

    total_waste = latest[
        "Total_Predicted_Waste_kg"
    ].sum()

    print(
        f"\nTotal predicted waste: "
        f"{total_waste:,.2f} kg/day"
    )

    print(
        f"≈ "
        f"{total_waste / 1000:,.2f} tonnes/day"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "BENGALURU AREA-LEVEL OVERFLOW RISK PREDICTOR"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Step 1
    # --------------------------------------------------------

    predictions = (
        load_temporal_predictions()
    )

    # --------------------------------------------------------
    # Step 2
    # --------------------------------------------------------

    mapping = (
        load_area_mapping()
    )

    # --------------------------------------------------------
    # Step 3
    # --------------------------------------------------------

    data = prepare_data(
        predictions,
        mapping
    )

    # --------------------------------------------------------
    # Step 4
    # --------------------------------------------------------

    data = calculate_area_features(
        data
    )

    # --------------------------------------------------------
    # Step 5
    # --------------------------------------------------------

    data = calculate_overflow_risk(
        data
    )

    # --------------------------------------------------------
    # Step 6
    # --------------------------------------------------------

    data = calculate_collection_priority(
        data
    )

    # --------------------------------------------------------
    # Step 7
    # --------------------------------------------------------

    data = calculate_area_rank(
        data
    )

    # --------------------------------------------------------
    # Step 8
    # --------------------------------------------------------

    save_csv(
        data
    )

    # --------------------------------------------------------
    # Step 9
    # --------------------------------------------------------

    create_area_geodata(
        data
    )

    # --------------------------------------------------------
    # Step 10
    # --------------------------------------------------------

    display_results(
        data
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "AREA-LEVEL OVERFLOW PREDICTION COMPLETED"
    )

    print(
        "=" * 70
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()