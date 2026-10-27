"""
BENGALURU AREA-LEVEL WASTE AGGREGATION ENGINE

Purpose:
    Convert grid-level temporal waste predictions into
    administrative-area-level waste intelligence.

Inputs:
    1. bengaluru_grid_area_mapping.gpkg
    2. bengaluru_temporal_predictions.gpkg
    3. bengaluru_area_boundaries.gpkg

Outputs:
    1. bengaluru_area_waste_summary.csv
    2. bengaluru_area_waste_summary.gpkg
"""

import os
import warnings

import geopandas as gpd
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")


# ============================================================
# PATH CONFIGURATION
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

MAPPING_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_grid_area_mapping.gpkg"
)

TEMPORAL_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_temporal_predictions.gpkg"
)

AREA_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_boundaries.gpkg"
)

OUTPUT_CSV = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_waste_summary.csv"
)

OUTPUT_GPKG = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_waste_summary.gpkg"
)


# ============================================================
# HEADER
# ============================================================

def print_header():

    print("=" * 70)
    print("BENGALURU AREA-LEVEL WASTE AGGREGATION ENGINE")
    print("=" * 70)


# ============================================================
# LOAD GRID → AREA MAPPING
# ============================================================

def load_mapping():

    print("\nLoading grid-area mapping...")

    if not os.path.exists(MAPPING_FILE):

        raise FileNotFoundError(
            f"\nGrid-area mapping not found:\n{MAPPING_FILE}"
        )

    mapping = gpd.read_file(
        MAPPING_FILE
    )

    print(
        f"Mapping rows: {len(mapping):,}"
    )

    if "Grid_ID" not in mapping.columns:

        raise ValueError(
            "Grid_ID column missing from grid-area mapping."
        )

    if "area_name" not in mapping.columns:

        raise ValueError(
            "area_name column missing from grid-area mapping."
        )

    print(
        f"Unique areas: {mapping['area_name'].nunique():,}"
    )

    return mapping


# ============================================================
# LOAD TEMPORAL PREDICTIONS
# ============================================================

def load_temporal_predictions():

    print("\nLoading temporal waste predictions...")

    if not os.path.exists(TEMPORAL_FILE):

        raise FileNotFoundError(
            f"\nTemporal prediction file not found:\n{TEMPORAL_FILE}"
        )

    predictions = gpd.read_file(
        TEMPORAL_FILE
    )

    print(
        f"Prediction rows: {len(predictions):,}"
    )

    print(
        f"Unique grid cells: "
        f"{predictions['Grid_ID'].nunique():,}"
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
            "\nMissing required prediction columns:\n"
            + "\n".join(missing)
        )

    print("\nUsing actual prediction columns:")

    print(
        "  Waste:    predicted_daily_waste_kg"
    )

    print(
        "  Score:    temporal_waste_score"
    )

    print(
        "  Risk:     predicted_waste_risk"
    )

    print(
        "  Priority: predicted_collection_priority"
    )

    return predictions


# ============================================================
# PREPARE PREDICTION DATA
# ============================================================

def prepare_predictions(predictions):

    print(
        "\nPreparing prediction data..."
    )

    predictions = predictions.copy()

    # Convert date
    predictions["prediction_date"] = pd.to_datetime(
        predictions["prediction_date"],
        errors="coerce"
    )

    # Convert numeric fields
    numeric_columns = [
        "predicted_daily_waste_kg",
        "temporal_waste_score",
        "predicted_collection_priority"
    ]

    for col in numeric_columns:

        predictions[col] = pd.to_numeric(
            predictions[col],
            errors="coerce"
        )

    # Remove invalid Grid IDs
    predictions = predictions[
        predictions["Grid_ID"].notna()
    ].copy()

    # Fill missing numeric values
    predictions[
        "predicted_daily_waste_kg"
    ] = predictions[
        "predicted_daily_waste_kg"
    ].fillna(0)

    predictions[
        "temporal_waste_score"
    ] = predictions[
        "temporal_waste_score"
    ].fillna(0)

    predictions[
        "predicted_collection_priority"
    ] = predictions[
        "predicted_collection_priority"
    ].fillna(0)

    print(
        f"Valid prediction rows: {len(predictions):,}"
    )

    print(
        f"Prediction dates: "
        f"{predictions['prediction_date'].min().date()} "
        f"to "
        f"{predictions['prediction_date'].max().date()}"
    )

    return predictions


# ============================================================
# MERGE GRID PREDICTIONS WITH AREAS
# ============================================================

def merge_grid_area(mapping, predictions):

    print(
        "\nMerging grid predictions with administrative areas..."
    )

    # Only keep the area information needed
    area_info = mapping[
        [
            "Grid_ID",
            "area_osm_id",
            "area_name",
            "area_admin_level"
        ]
    ].copy()

    # Remove duplicate Grid_ID records
    area_info = area_info.drop_duplicates(
        subset=["Grid_ID"]
    )

    merged = predictions.merge(
        area_info,
        on="Grid_ID",
        how="left"
    )

    print(
        f"Merged rows: {len(merged):,}"
    )

    matched = merged[
        "area_name"
    ].notna().sum()

    print(
        f"Grid predictions matched: {matched:,}"
    )

    unmatched = (
        len(merged)
        -
        matched
    )

    print(
        f"Unmatched predictions: {unmatched:,}"
    )

    if matched == 0:

        raise ValueError(
            "No grid predictions were matched to administrative areas."
        )

    return merged


# ============================================================
# CLASSIFY AREA RISK
# ============================================================

def classify_area_risk(row):

    waste = row[
        "Total_Predicted_Waste_kg"
    ]

    risk = row[
        "Average_Temporal_Waste_Score"
    ]

    # Combined area-level risk logic
    #
    # The temporal score is normalized around 0-1,
    # while total waste depends on the number of
    # grid cells in the area.

    if risk >= 1.10:

        return "CRITICAL"

    elif risk >= 1.05:

        return "HIGH"

    elif risk >= 0.95:

        return "MEDIUM"

    else:

        return "LOW"


# ============================================================
# CLASSIFY COLLECTION PRIORITY
# ============================================================

def classify_collection_priority(row):

    risk = row[
        "Area_Risk_Category"
    ]

    waste = row[
        "Total_Predicted_Waste_kg"
    ]

    if risk == "CRITICAL":

        return "URGENT"

    elif risk == "HIGH":

        return "HIGH"

    elif risk == "MEDIUM":

        return "MEDIUM"

    else:

        return "NORMAL"


# ============================================================
# AGGREGATE BY AREA
# ============================================================

def aggregate_by_area(merged):

    print(
        "\nAggregating grid predictions by administrative area..."
    )

    grouped = (
        merged
        .groupby(
            [
                "area_name",
                "area_osm_id",
                "area_admin_level"
            ],
            dropna=False
        )
        .agg(
            Grid_Cell_Count=(
                "Grid_ID",
                "nunique"
            ),

            Prediction_Day_Count=(
                "prediction_date",
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

            Minimum_Predicted_Waste_kg=(
                "predicted_daily_waste_kg",
                "min"
            ),

            Average_Temporal_Waste_Score=(
                "temporal_waste_score",
                "mean"
            ),

            Maximum_Temporal_Waste_Score=(
                "temporal_waste_score",
                "max"
            ),

            Average_Collection_Priority=(
                "predicted_collection_priority",
                "mean"
            ),

            Maximum_Collection_Priority=(
                "predicted_collection_priority",
                "max"
            )
        )
        .reset_index()
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Total_Predicted_Waste_kg above sums ALL prediction dates.
    #
    # For operational planning we also calculate the
    # latest prediction day separately.
    # --------------------------------------------------------

    latest_date = merged[
        "prediction_date"
    ].max()

    latest = merged[
        merged["prediction_date"] == latest_date
    ].copy()

    latest_grouped = (
        latest
        .groupby(
            [
                "area_name",
                "area_osm_id",
                "area_admin_level"
            ],
            dropna=False
        )
        .agg(
            Latest_Day_Predicted_Waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),

            Latest_Day_Average_Waste_kg=(
                "predicted_daily_waste_kg",
                "mean"
            ),

            Latest_Day_Maximum_Waste_kg=(
                "predicted_daily_waste_kg",
                "max"
            ),

            Latest_Day_Average_Score=(
                "temporal_waste_score",
                "mean"
            )
        )
        .reset_index()
    )

    grouped = grouped.merge(
        latest_grouped,
        on=[
            "area_name",
            "area_osm_id",
            "area_admin_level"
        ],
        how="left"
    )

    grouped[
        "Area_Risk_Category"
    ] = grouped.apply(
        classify_area_risk,
        axis=1
    )

    grouped[
        "Collection_Priority"
    ] = grouped.apply(
        classify_collection_priority,
        axis=1
    )

    # Rank areas based on latest daily waste
    grouped[
        "Waste_Rank"
    ] = grouped[
        "Latest_Day_Predicted_Waste_kg"
    ].rank(
        ascending=False,
        method="min"
    )

    grouped[
        "Waste_Rank"
    ] = grouped[
        "Waste_Rank"
    ].astype(int)

    # Sort
    grouped = grouped.sort_values(
        "Latest_Day_Predicted_Waste_kg",
        ascending=False
    )

    return grouped


# ============================================================
# CREATE AREA GEOPACKAGE
# ============================================================

def create_area_geopackage(summary):

    print(
        "\nCreating area-level GeoPackage..."
    )

    if not os.path.exists(AREA_FILE):

        print(
            "\nArea boundary file not found."
        )

        print(
            "Skipping GeoPackage spatial output."
        )

        return

    boundaries = gpd.read_file(
        AREA_FILE
    )

    # Keep only necessary fields
    boundary_columns = [
        "osm_id",
        "name",
        "admin_level",
        "geometry"
    ]

    available = [
        col
        for col in boundary_columns
        if col in boundaries.columns
    ]

    boundaries = boundaries[
        available
    ].copy()

    boundaries = boundaries.rename(
        columns={
            "osm_id": "area_osm_id",
            "name": "area_name",
            "admin_level": "area_admin_level"
        }
    )

    # Remove duplicate area IDs
    boundaries = boundaries.drop_duplicates(
        subset=["area_osm_id"]
    )

    # Merge statistics with geometries
    spatial = boundaries.merge(
        summary,
        on=[
            "area_name",
            "area_osm_id",
            "area_admin_level"
        ],
        how="inner"
    )

    if len(spatial) == 0:

        print(
            "\nWARNING: No area geometries matched."
        )

        return

    # Fix invalid geometries if necessary
    invalid = (
        ~spatial.geometry.is_valid
    ).sum()

    if invalid > 0:

        print(
            f"Fixing {invalid} invalid geometries..."
        )

        spatial[
            "geometry"
        ] = spatial.geometry.make_valid()

    # Remove old output if it exists
    if os.path.exists(OUTPUT_GPKG):

        try:
            os.remove(
                OUTPUT_GPKG
            )

        except PermissionError:

            print(
                "\nWARNING: GeoPackage is currently open."
            )

            print(
                "Close it and run the script again."
            )

            return

    spatial.to_file(
        OUTPUT_GPKG,
        layer="area_waste_summary",
        driver="GPKG"
    )

    print(
        "\nGeoPackage saved to:"
    )

    print(
        OUTPUT_GPKG
    )


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(summary):

    print(
        "\nSaving area-level CSV..."
    )

    output = summary.copy()

    output.to_csv(
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

def display_results(summary):

    print("\n")
    print("=" * 70)
    print("AREA-LEVEL WASTE INTELLIGENCE")
    print("=" * 70)

    print(
        f"\nTotal administrative areas: "
        f"{len(summary):,}"
    )

    # --------------------------------------------------------
    # Risk distribution
    # --------------------------------------------------------

    print(
        "\nRisk distribution:"
    )

    print(
        summary[
            "Area_Risk_Category"
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
        summary[
            "Collection_Priority"
        ]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------------
    # Top areas
    # --------------------------------------------------------

    print(
        "\nTop 20 areas by latest predicted daily waste:"
    )

    display_columns = [
        "area_name",
        "Grid_Cell_Count",
        "Latest_Day_Predicted_Waste_kg",
        "Latest_Day_Average_Waste_kg",
        "Latest_Day_Maximum_Waste_kg",
        "Latest_Day_Average_Score",
        "Area_Risk_Category",
        "Collection_Priority",
        "Waste_Rank"
    ]

    print(
        summary[
            display_columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Overall waste
    # --------------------------------------------------------

    total_latest = summary[
        "Latest_Day_Predicted_Waste_kg"
    ].sum()

    print(
        f"\nTotal predicted waste "
        f"for latest prediction day: "
        f"{total_latest:,.2f} kg"
    )

    print(
        f"≈ {total_latest / 1000:,.2f} tonnes/day"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print_header()

    # --------------------------------------------------------
    # 1. Load mapping
    # --------------------------------------------------------

    mapping = load_mapping()

    # --------------------------------------------------------
    # 2. Load actual temporal predictions
    # --------------------------------------------------------

    predictions = load_temporal_predictions()

    # --------------------------------------------------------
    # 3. Prepare predictions
    # --------------------------------------------------------

    predictions = prepare_predictions(
        predictions
    )

    # --------------------------------------------------------
    # 4. Merge
    # --------------------------------------------------------

    merged = merge_grid_area(
        mapping,
        predictions
    )

    # --------------------------------------------------------
    # 5. Aggregate
    # --------------------------------------------------------

    summary = aggregate_by_area(
        merged
    )

    # --------------------------------------------------------
    # 6. Save CSV
    # --------------------------------------------------------

    save_csv(
        summary
    )

    # --------------------------------------------------------
    # 7. Create spatial output
    # --------------------------------------------------------

    create_area_geopackage(
        summary
    )

    # --------------------------------------------------------
    # 8. Display results
    # --------------------------------------------------------

    display_results(
        summary
    )

    print("\n")
    print("=" * 70)
    print("AREA-LEVEL AGGREGATION COMPLETED")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()