"""
=========================================================
Urban Predictive Intelligence System
Collection Priority Engine
=========================================================

Converts overflow-risk predictions into an actionable
collection priority plan.

Output:
    - Collection priority score
    - Priority rank
    - Collection window
    - Estimated waste
    - Recommended action
    - Truck requirement estimate

This is a baseline decision-support model.
=========================================================
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import numpy as np


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_overflow_risk.gpkg"
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
    / "bengaluru_collection_priority.gpkg"
)


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("BENGALURU COLLECTION PRIORITY ENGINE")
    print("=" * 70)

    # -----------------------------------------------------
    # Load overflow predictions
    # -----------------------------------------------------

    print("\nLoading overflow-risk dataset...")

    gdf = gpd.read_file(
        INPUT_FILE,
        layer="overflow_risk"
    )

    print(
        f"Records loaded: {len(gdf):,}"
    )

    # -----------------------------------------------------
    # Ensure required columns exist
    # -----------------------------------------------------

    required_columns = [
        "Grid_ID",
        "prediction_date",
        "predicted_daily_waste_kg",
        "overflow_risk_score",
        "overflow_risk_level",
    ]

    missing = [
        column
        for column in required_columns
        if column not in gdf.columns
    ]

    if missing:

        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # -----------------------------------------------------
    # Clean values
    # -----------------------------------------------------

    gdf["overflow_risk_score"] = (
        pd.to_numeric(
            gdf["overflow_risk_score"],
            errors="coerce"
        )
        .fillna(0)
        .clip(0, 100)
    )

    gdf["predicted_daily_waste_kg"] = (
        pd.to_numeric(
            gdf["predicted_daily_waste_kg"],
            errors="coerce"
        )
        .fillna(0)
        .clip(lower=0)
    )

    # -----------------------------------------------------
    # Waste pressure score
    # -----------------------------------------------------

    max_waste = (
        gdf["predicted_daily_waste_kg"]
        .max()
    )

    if max_waste > 0:

        gdf["waste_pressure_score"] = (
            gdf["predicted_daily_waste_kg"]
            / max_waste
            * 100
        )

    else:

        gdf["waste_pressure_score"] = 0

    # -----------------------------------------------------
    # Priority score
    # -----------------------------------------------------
    #
    # 60% overflow risk
    # 30% predicted waste quantity
    # 10% temporal pressure
    #
    # Higher score = earlier collection.
    # -----------------------------------------------------

    temporal_score = (
        gdf["temporal_waste_score"]
        .fillna(1)
        .clip(0.5, 2)
    )

    temporal_score = (
        (temporal_score - 0.5)
        / 1.5
        * 100
    )

    gdf["collection_priority_score"] = (

        0.60
        * gdf["overflow_risk_score"]

        +

        0.30
        * gdf["waste_pressure_score"]

        +

        0.10
        * temporal_score
    )

    gdf["collection_priority_score"] = (
        gdf["collection_priority_score"]
        .clip(0, 100)
    )

    # -----------------------------------------------------
    # Priority category
    # -----------------------------------------------------

    def classify_priority(score):

        if score >= 80:
            return "P1 - Immediate"

        elif score >= 65:
            return "P2 - Urgent"

        elif score >= 50:
            return "P3 - High"

        elif score >= 30:
            return "P4 - Scheduled"

        else:
            return "P5 - Routine"

    gdf["collection_priority"] = (
        gdf["collection_priority_score"]
        .apply(classify_priority)
    )

    # -----------------------------------------------------
    # Collection window
    # -----------------------------------------------------

    def collection_window(priority):

        if priority == "P1 - Immediate":
            return "Within 3 Hours"

        elif priority == "P2 - Urgent":
            return "Within 6 Hours"

        elif priority == "P3 - High":
            return "Within 12 Hours"

        elif priority == "P4 - Scheduled":
            return "Within 24 Hours"

        else:
            return "Routine Cycle"

    gdf["recommended_collection_window"] = (
        gdf["collection_priority"]
        .apply(collection_window)
    )

    # -----------------------------------------------------
    # Recommended action
    # -----------------------------------------------------

    def action(priority):

        if priority == "P1 - Immediate":
            return "Dispatch nearest available truck"

        elif priority == "P2 - Urgent":
            return "Assign high-capacity collection truck"

        elif priority == "P3 - High":
            return "Include in next collection route"

        elif priority == "P4 - Scheduled":
            return "Schedule normal collection"

        else:
            return "Monitor"

    gdf["recommended_collection_action"] = (
        gdf["collection_priority"]
        .apply(action)
    )

    # -----------------------------------------------------
    # Estimated truck capacity requirement
    # -----------------------------------------------------
    #
    # Baseline assumption:
    # One truck trip is treated as approximately 5,000 kg.
    #
    # This should later be replaced with the actual
    # municipal vehicle capacity.
    # -----------------------------------------------------

    TRUCK_CAPACITY_KG = 5000

    gdf["estimated_truck_trips"] = np.ceil(
        gdf["predicted_daily_waste_kg"]
        / TRUCK_CAPACITY_KG
    ).astype(int)

    gdf["estimated_truck_trips"] = (
        gdf["estimated_truck_trips"]
        .clip(lower=1)
    )

    # -----------------------------------------------------
    # Priority rank
    # -----------------------------------------------------

    gdf["collection_rank"] = (
        gdf["collection_priority_score"]
        .rank(
            ascending=False,
            method="first"
        )
        .astype(int)
    )

    # -----------------------------------------------------
    # High-priority flag
    # -----------------------------------------------------

    gdf["dispatch_required"] = (
        gdf["collection_priority"]
        .isin(
            [
                "P1 - Immediate",
                "P2 - Urgent"
            ]
        )
        .astype(int)
    )

    # -----------------------------------------------------
    # Sort
    # -----------------------------------------------------

    gdf = gdf.sort_values(
        [
            "prediction_date",
            "collection_priority_score"
        ],
        ascending=[
            True,
            False
        ]
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    print(
        "\nSaving collection priority dataset..."
    )

    gdf.to_file(
        OUTPUT_FILE,
        layer="collection_priority",
        driver="GPKG"
    )

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    print("\n" + "=" * 70)

    print("\nCollection priority distribution:")

    print(
        gdf[
            "collection_priority"
        ]
        .value_counts()
    )

    print("\nDispatch-required records:")

    dispatch_count = (
        gdf["dispatch_required"]
        .sum()
    )

    print(
        f"{dispatch_count:,}"
    )

    print("\nEstimated total truck trips:")

    print(
        gdf[
            "estimated_truck_trips"
        ]
        .sum()
    )

    # -----------------------------------------------------
    # Top 20 collection locations
    # -----------------------------------------------------

    print(
        "\nTop 20 collection priorities:"
    )

    top_columns = [
        "Grid_ID",
        "prediction_date",
        "predicted_daily_waste_kg",
        "overflow_risk_score",
        "collection_priority_score",
        "collection_priority",
        "recommended_collection_window",
        "estimated_truck_trips"
    ]

    top20 = (
        gdf[
            top_columns
        ]
        .sort_values(
            "collection_priority_score",
            ascending=False
        )
        .head(20)
    )

    print(
        top20.to_string(
            index=False
        )
    )

    print("\nOutput saved to:")

    print(OUTPUT_FILE)

    print("\n" + "=" * 70)
    print("COLLECTION PRIORITY ENGINE COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()