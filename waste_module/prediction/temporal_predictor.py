"""
=========================================================
Urban Predictive Intelligence System
Temporal Waste Prediction Engine
=========================================================

Predicts waste generation for different times of the week
using the spatial baseline produced by waste_estimator.py.

This is a baseline temporal model.

When real historical waste observations become available,
this module can be replaced/augmented with a trained
ML/LSTM/XGBoost forecasting model.
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
    / "bengaluru_waste_estimates.gpkg"
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
    / "bengaluru_temporal_predictions.gpkg"
)


# =========================================================
# TEMPORAL MULTIPLIERS
# =========================================================

DAY_MULTIPLIERS = {

    "Monday": 1.00,

    "Tuesday": 1.00,

    "Wednesday": 1.02,

    "Thursday": 1.03,

    "Friday": 1.08,

    "Saturday": 1.15,

    "Sunday": 1.10,
}


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 65)
    print("BENGALURU TEMPORAL WASTE PREDICTION ENGINE")
    print("=" * 65)

    # -----------------------------------------------------
    # Load spatial waste estimates
    # -----------------------------------------------------

    print("\nLoading waste estimation dataset...")

    grid = gpd.read_file(
        INPUT_FILE,
        layer="waste_estimates"
    )

    print(
        f"Grid cells loaded: {len(grid):,}"
    )

    # -----------------------------------------------------
    # Create prediction dates
    # -----------------------------------------------------

    print(
        "\nGenerating prediction calendar..."
    )

    start_date = pd.Timestamp.today().normalize()

    prediction_dates = pd.date_range(
        start=start_date,
        periods=7,
        freq="D"
    )

    # -----------------------------------------------------
    # Create grid-date combinations
    # -----------------------------------------------------

    print(
        "\nCreating 7-day prediction horizon..."
    )

    grid["_temporary_key"] = 1

    dates = pd.DataFrame(
        {
            "prediction_date": prediction_dates,
            "_temporary_key": 1
        }
    )

    predictions = grid.merge(
        dates,
        on="_temporary_key"
    )

    predictions = predictions.drop(
        columns=["_temporary_key"]
    )

    # -----------------------------------------------------
    # Day of week
    # -----------------------------------------------------

    predictions["day_of_week"] = (
        predictions["prediction_date"]
        .dt.day_name()
    )

    predictions["day_multiplier"] = (
        predictions["day_of_week"]
        .map(DAY_MULTIPLIERS)
        .fillna(1.0)
    )

    # -----------------------------------------------------
    # Weekend indicator
    # -----------------------------------------------------

    predictions["is_weekend"] = (
        predictions["prediction_date"]
        .dt.dayofweek
        >= 5
    ).astype(int)

    # -----------------------------------------------------
    # Seasonal multiplier
    # -----------------------------------------------------
    #
    # Mild synthetic seasonal pattern.
    #
    # This is deliberately small because we don't want
    # seasonal assumptions to dominate the land-use signal.
    # -----------------------------------------------------

    predictions["month"] = (
        predictions["prediction_date"]
        .dt.month
    )

    predictions["seasonal_multiplier"] = (
        1.0
        + 0.05
        * np.sin(
            2
            * np.pi
            * predictions["month"]
            / 12
        )
    )

    # -----------------------------------------------------
    # Activity multiplier
    # -----------------------------------------------------

    predictions["activity_multiplier"] = 1.0

    predictions.loc[
        predictions["dominant_landuse"]
        .str.lower()
        .eq("commercial"),
        "activity_multiplier"
    ] = 1.10

    predictions.loc[
        predictions["dominant_landuse"]
        .str.lower()
        .eq("recreational"),
        "activity_multiplier"
    ] = 1.08

    predictions.loc[
        predictions["dominant_landuse"]
        .str.lower()
        .eq("institutional"),
        "activity_multiplier"
    ] = 1.03

    predictions.loc[
        predictions["dominant_landuse"]
        .str.lower()
        .eq("industrial"),
        "activity_multiplier"
    ] = 1.05

    # -----------------------------------------------------
    # Predicted waste
    # -----------------------------------------------------

    predictions["predicted_daily_waste_kg"] = (

        predictions["estimated_daily_waste_kg"]

        * predictions["day_multiplier"]

        * predictions["seasonal_multiplier"]

        * predictions["activity_multiplier"]
    )

    # -----------------------------------------------------
    # Prediction score
    # -----------------------------------------------------

    predictions["temporal_waste_score"] = (
        predictions["predicted_daily_waste_kg"]
        /
        predictions["estimated_daily_waste_kg"]
    )

    # -----------------------------------------------------
    # Prediction category
    # -----------------------------------------------------

    def classify_prediction(score):

        if score >= 1.15:
            return "Very High"

        elif score >= 1.08:
            return "High"

        elif score >= 1.02:
            return "Moderate"

        else:
            return "Normal"

    predictions["prediction_level"] = (
        predictions["temporal_waste_score"]
        .apply(classify_prediction)
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    print(
        "\nSaving temporal predictions..."
    )

    predictions.to_file(
        OUTPUT_FILE,
        layer="temporal_predictions",
        driver="GPKG"
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print("\n" + "=" * 65)

    print("\nPrediction dates:")

    print(
        predictions[
            "prediction_date"
        ]
        .drop_duplicates()
        .sort_values()
        .dt.strftime("%Y-%m-%d")
        .tolist()
    )

    print("\nPrediction level distribution:")

    print(
        predictions[
            "prediction_level"
        ]
        .value_counts()
    )

    print("\nAverage predicted waste by day:")

    daily_summary = (
        predictions
        .groupby(
            [
                "prediction_date",
                "day_of_week"
            ]
        )[
            "predicted_daily_waste_kg"
        ]
        .mean()
        .round(2)
    )

    print(
        daily_summary
    )

    print("\nSaved successfully:")

    print(OUTPUT_FILE)

    print("\n" + "=" * 65)
    print("TEMPORAL PREDICTION ENGINE COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()