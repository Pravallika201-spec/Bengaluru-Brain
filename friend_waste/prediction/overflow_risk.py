"""
=========================================================
Urban Predictive Intelligence System
Overflow Risk Prediction Engine
=========================================================

Combines spatial and temporal waste signals to estimate
the likelihood of waste overflow in each Bengaluru grid
cell.

IMPORTANT:
This is a baseline risk model. It should be calibrated
with real collection/bin-level observations when such
data becomes available.
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
    / "bengaluru_temporal_predictions.gpkg"
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
    / "bengaluru_overflow_risk.gpkg"
)


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("BENGALURU OVERFLOW RISK PREDICTION ENGINE")
    print("=" * 70)

    # -----------------------------------------------------
    # Load temporal predictions
    # -----------------------------------------------------

    print("\nLoading temporal prediction dataset...")

    gdf = gpd.read_file(
        INPUT_FILE,
        layer="temporal_predictions"
    )

    print(
        f"Prediction records loaded: {len(gdf):,}"
    )

    # -----------------------------------------------------
    # Normalize spatial waste score
    # -----------------------------------------------------

    print("\nPreparing risk indicators...")

    spatial_score = (
        gdf["predicted_waste_score"]
        .fillna(0)
        .clip(0, 100)
    )

    # -----------------------------------------------------
    # Temporal pressure
    # -----------------------------------------------------

    temporal_pressure = (
        gdf["temporal_waste_score"]
        .fillna(1.0)
        .clip(0.5, 2.0)
    )

    temporal_pressure_normalized = (
        (temporal_pressure - 0.5)
        / 1.5
        * 100
    )

    # -----------------------------------------------------
    # Commercial / activity pressure
    # -----------------------------------------------------

    commercial_pressure = (
        gdf["commercial_intensity"]
        .fillna(0)
        .clip(0, 1)
        * 100
    )

    recreational_pressure = (
        gdf["recreational_intensity"]
        .fillna(0)
        .clip(0, 1)
        * 100
    )

    institutional_pressure = (
        gdf["institutional_intensity"]
        .fillna(0)
        .clip(0, 1)
        * 100
    )

    # -----------------------------------------------------
    # Waste generation pressure
    # -----------------------------------------------------

    waste_pressure = (
        gdf["predicted_waste_intensity_normalized"]
        .fillna(0)
        .clip(0, 1)
        * 100
    )

    # -----------------------------------------------------
    # Combined overflow score
    # -----------------------------------------------------
    #
    # Weighted baseline model:
    #
    # 40% spatial waste intensity
    # 25% predicted waste pressure
    # 15% temporal pressure
    # 10% commercial activity
    # 5% recreational activity
    # 5% institutional activity
    #
    # These weights are initial assumptions and should
    # eventually be learned/calibrated from observations.
    # -----------------------------------------------------

    gdf["overflow_risk_score"] = (

        0.40 * spatial_score

        + 0.25 * waste_pressure

        + 0.15 * temporal_pressure_normalized

        + 0.10 * commercial_pressure

        + 0.05 * recreational_pressure

        + 0.05 * institutional_pressure
    )

    gdf["overflow_risk_score"] = (
        gdf["overflow_risk_score"]
        .clip(0, 100)
    )

    # -----------------------------------------------------
    # Risk level
    # -----------------------------------------------------

    def classify_risk(score):

        if score >= 80:
            return "Critical"

        elif score >= 65:
            return "Very High"

        elif score >= 50:
            return "High"

        elif score >= 30:
            return "Medium"

        else:
            return "Low"

    gdf["overflow_risk_level"] = (
        gdf["overflow_risk_score"]
        .apply(classify_risk)
    )

    # -----------------------------------------------------
    # Recommended collection action
    # -----------------------------------------------------

    def collection_action(level):

        if level == "Critical":
            return "Immediate Collection"

        elif level == "Very High":
            return "Collect Within 6 Hours"

        elif level == "High":
            return "Collect Within 12 Hours"

        elif level == "Medium":
            return "Schedule Collection"

        else:
            return "Routine Monitoring"

    gdf["recommended_action"] = (
        gdf["overflow_risk_level"]
        .apply(collection_action)
    )

    # -----------------------------------------------------
    # Priority rank
    # -----------------------------------------------------

    # Highest-risk cells get lowest rank number.

    gdf["overflow_priority_rank"] = (
        gdf["overflow_risk_score"]
        .rank(
            ascending=False,
            method="dense"
        )
        .astype(int)
    )

    # -----------------------------------------------------
    # High-risk indicator
    # -----------------------------------------------------

    gdf["high_risk_flag"] = (
        gdf["overflow_risk_score"] >= 65
    ).astype(int)

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    print("\nSaving overflow risk dataset...")

    gdf.to_file(
        OUTPUT_FILE,
        layer="overflow_risk",
        driver="GPKG"
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print("\n" + "=" * 70)

    print("\nOverflow risk distribution:")

    print(
        gdf[
            "overflow_risk_level"
        ]
        .value_counts()
    )

    print("\nRisk score statistics:")

    print(
        gdf[
            "overflow_risk_score"
        ]
        .describe()
        .round(2)
    )

    print("\nHigh-risk records:")

    print(
        gdf["high_risk_flag"]
        .sum()
    )

    print(
        f" out of {len(gdf):,} prediction records"
    )

    print("\nTop 10 highest-risk grid/date records:")

    top = (
        gdf[
            [
                "Grid_ID",
                "prediction_date",
                "overflow_risk_score",
                "overflow_risk_level",
                "recommended_action"
            ]
        ]
        .sort_values(
            "overflow_risk_score",
            ascending=False
        )
        .head(10)
    )

    print(top.to_string(index=False))

    print("\nSaved successfully:")

    print(OUTPUT_FILE)

    print("\n" + "=" * 70)
    print("OVERFLOW RISK ENGINE COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()