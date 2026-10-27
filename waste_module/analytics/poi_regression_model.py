"""
============================================================
OPTION 2 — POI-DENSITY REGRESSION MODEL
============================================================

An independent, non-satellite prediction of ward-level waste generation,
using land-use density features from OpenStreetMap (building counts,
commercial POI counts, ward area) instead of remote-sensing indices.

IMPORTANT METHODOLOGICAL NOTE — read this before presenting results:

  There is no ground-truth waste measurement available for Bengaluru's
  369 wards (no municipal weighbridge data at ward level). So this model
  is NOT validated against real-world measured waste. Instead, it is
  trained to predict the EXISTING satellite-based model's output
  (Total_Predicted_Waste_kg from area_overflow_predictor.py) from a
  completely independent set of input features (OSM building/POI density
  instead of satellite indices).

  This is a legitimate methodology — it is a form of CONVERGENT VALIDATION:
  if two independently-built models, using different data sources, largely
  agree on which wards are high-risk, that agreement is itself evidence
  the underlying signal is real. Where they disagree is equally useful —
  those wards are good candidates for field verification, since the two
  methods are picking up different things.

  Report this honestly as "cross-validation between two independent
  models," not as "the model was proven accurate" — it has NOT been
  checked against real-world ground truth, and that should be stated
  plainly if asked.

METHODOLOGICAL NOTE — why density, not raw totals:

  An earlier version of this script trained on raw totals (predicted_waste_kg)
  using raw counts (building count, POI count, ward area) as features. That
  produced a misleadingly high R^2 (~0.98) — but the Random Forest feature
  importances showed ward_area_km2 alone explained ~99% of it. That's because
  BOTH the satellite model's totals AND raw building/POI counts mechanically
  scale with ward size: a bigger ward has more grid cells (more total waste)
  and more physical space for buildings (more buildings), regardless of how
  dense or sparse it actually is. Training on raw values would let the model
  "succeed" by just recovering ward size, without the building/POI density
  signal doing any real work.

  This version instead trains on DENSITY (kg/km^2, buildings/km^2, POIs/km^2)
  for both features and target, removing that confound so the R^2 reported
  actually reflects whether land-use density predicts waste-generation
  intensity — the real hypothesis this model is meant to test.

Input:
    ward_osm_features.csv                       (from fetch_osm_ward_features.py)
    bengaluru_area_overflow_predictions.csv      (the existing satellite model's output)

Output:
    bengaluru_poi_regression_predictions.csv
    poi_regression_comparison.png                (predicted vs. satellite-model scatter)
============================================================
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)
PROCESSED_DIR = os.path.join(BASE_DIR, "waste_module", "data", "processed")

OSM_FEATURES_FILE = os.path.join(PROCESSED_DIR, "ward_osm_features.csv")
SATELLITE_PREDICTIONS_FILE = os.path.join(PROCESSED_DIR, "bengaluru_area_overflow_predictions.csv")
OUTPUT_FILE = os.path.join(PROCESSED_DIR, "bengaluru_poi_regression_predictions.csv")
CHART_FILE = os.path.join(PROCESSED_DIR, "poi_regression_comparison.png")

FEATURE_COLUMNS = ["residential_building_density", "commercial_poi_density"]
TARGET_COLUMN = "Total_Predicted_Waste_kg"
DENSITY_TARGET_COLUMN = "waste_density_kg_per_km2"


def load_data():
    print("\nLoading OSM features and satellite-model predictions...")

    if not os.path.exists(OSM_FEATURES_FILE):
        raise FileNotFoundError(
            f"\n{OSM_FEATURES_FILE} not found.\nRun fetch_osm_ward_features.py first."
        )
    if not os.path.exists(SATELLITE_PREDICTIONS_FILE):
        raise FileNotFoundError(
            f"\n{SATELLITE_PREDICTIONS_FILE} not found.\n"
            "Run area_overflow_predictor.py first (it produces the satellite-based "
            "predictions this script cross-validates against)."
        )

    osm = pd.read_csv(OSM_FEATURES_FILE)
    satellite = pd.read_csv(SATELLITE_PREDICTIONS_FILE)

    # Satellite predictions file has one row per ward per prediction_date —
    # use the latest date only, matching how the dashboard reads it.
    if "prediction_date" in satellite.columns:
        latest = satellite["prediction_date"].max()
        satellite = satellite[satellite["prediction_date"] == latest]
        print(f"Using satellite predictions for: {latest}")

    if TARGET_COLUMN not in satellite.columns:
        raise ValueError(
            f"\nExpected column '{TARGET_COLUMN}' not found in the satellite "
            f"predictions file. Columns found: {list(satellite.columns)}"
        )

    merged = osm.merge(
        satellite[["area_name", TARGET_COLUMN]],
        on="area_name", how="inner"
    )
    print(f"Wards with both OSM features and satellite predictions: {len(merged):,}")

    if len(merged) < 20:
        raise ValueError(
            f"Only {len(merged)} wards matched between the two files — check that "
            "area_name values line up between ward_osm_features.csv and the "
            "satellite predictions file."
        )

    # IMPORTANT: use DENSITY (per km^2), not raw counts/totals, for both the
    # features and the target. Raw counts and raw totals both mechanically
    # scale with ward area — a bigger ward has more buildings AND a bigger
    # predicted-waste total just because it covers more land, regardless of
    # how dense or sparse it actually is. Training on raw values would let
    # the model "succeed" by just recovering ward size, which doesn't test
    # what this model is actually meant to test: does building/POI DENSITY
    # predict waste-generation INTENSITY. Dividing everything through by
    # ward_area_km2 removes that confound from both sides.
    safe_area = merged["ward_area_km2"].replace(0, pd.NA)
    merged["residential_building_density"] = merged["residential_building_count"] / safe_area
    merged["commercial_poi_density"] = merged["commercial_poi_count"] / safe_area
    merged[DENSITY_TARGET_COLUMN] = merged[TARGET_COLUMN] / safe_area
    merged = merged.dropna(subset=FEATURE_COLUMNS + [DENSITY_TARGET_COLUMN])

    return merged


def train_models(df):
    print("\nTraining models...")
    print(f"Features (density-based, area confound removed): {FEATURE_COLUMNS}")
    print(f"Target: {DENSITY_TARGET_COLUMN}")

    X = df[FEATURE_COLUMNS]
    y = df[DENSITY_TARGET_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"Train set: {len(X_train)} wards, Test set: {len(X_test)} wards")

    results = {}

    lin = LinearRegression()
    lin.fit(X_train, y_train)
    lin_pred = lin.predict(X_test)
    results["Linear Regression"] = {
        "model": lin,
        "r2": r2_score(y_test, lin_pred),
        "mae": mean_absolute_error(y_test, lin_pred),
        "rmse": np.sqrt(mean_squared_error(y_test, lin_pred)),
    }

    rf = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)
    results["Random Forest"] = {
        "model": rf,
        "r2": r2_score(y_test, rf_pred),
        "mae": mean_absolute_error(y_test, rf_pred),
        "rmse": np.sqrt(mean_squared_error(y_test, rf_pred)),
        "feature_importances": dict(zip(FEATURE_COLUMNS, rf.feature_importances_)),
    }

    print("\nModel performance on held-out test set (predicting SATELLITE-MODEL")
    print("WASTE DENSITY, kg/km^2, from independent OSM density features):")
    for name, r in results.items():
        print(f"\n  {name}:")
        print(f"    R^2:  {r['r2']:.3f}")
        print(f"    MAE:  {r['mae']:.2f} kg/km^2")
        print(f"    RMSE: {r['rmse']:.2f} kg/km^2")

    if "feature_importances" in results["Random Forest"]:
        print("\n  Random Forest feature importances:")
        for feat, imp in sorted(results["Random Forest"]["feature_importances"].items(),
                                 key=lambda x: -x[1]):
            print(f"    {feat}: {imp:.3f}")

    # Use whichever model scored higher on R^2 for the final predictions
    best_name = max(results, key=lambda k: results[k]["r2"])
    print(f"\nUsing {best_name} for final predictions (higher R^2 on held-out test set).")
    return results[best_name]["model"], results, best_name


def generate_predictions(df, model):
    df = df.copy()
    df["poi_regression_predicted_density_kg_per_km2"] = model.predict(df[FEATURE_COLUMNS]).round(2)
    # Convert density back to a total-kg figure so this is directly comparable
    # to the other two models' kg/day outputs in the dashboard.
    df["poi_regression_predicted_waste_kg"] = (
        df["poi_regression_predicted_density_kg_per_km2"] * df["ward_area_km2"]
    ).round(2)
    df["difference_from_satellite_kg"] = (
        df["poi_regression_predicted_waste_kg"] - df[TARGET_COLUMN]
    ).round(2)
    df["percent_difference"] = (
        df["difference_from_satellite_kg"] / df[TARGET_COLUMN].replace(0, np.nan) * 100
    ).round(1)
    return df


def plot_comparison(df, best_name):
    print("\nGenerating comparison chart...")
    fig, ax = plt.subplots(figsize=(7, 7))

    # Plot in density terms — that's what was actually modeled, and it's the
    # fair, confound-free comparison (plotting totals here would just show
    # the ward-size correlation again, which is what we deliberately removed).
    x = df[DENSITY_TARGET_COLUMN]
    y = df["poi_regression_predicted_density_kg_per_km2"]

    ax.scatter(x, y, alpha=0.5, s=25, color="#1F4A38", edgecolors="white", linewidth=0.5)

    lims = [min(x.min(), y.min()), max(x.max(), y.max())]
    ax.plot(lims, lims, linestyle="--", color="#A83B2E", linewidth=1.3, label="Perfect agreement")

    ax.set_xlabel("Satellite-based waste density (kg/km² /day)")
    ax.set_ylabel(f"POI-regression predicted density (kg/km² /day) — {best_name}")
    ax.set_title("Cross-validation: POI-density model vs. satellite-based model\n(density, not totals — area confound removed)")
    ax.legend()
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    plt.savefig(CHART_FILE, dpi=150, facecolor="white")
    print(f"Saved chart to:\n{CHART_FILE}")


def main():
    print("=" * 70)
    print("OPTION 2 — POI-DENSITY REGRESSION MODEL")
    print("(independent of satellite imagery, cross-validated against it)")
    print("=" * 70)

    df = load_data()
    best_model, all_results, best_name = train_models(df)
    df = generate_predictions(df, best_model)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved predictions to:\n{OUTPUT_FILE}")

    plot_comparison(df, best_name)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    agree = (df["percent_difference"].abs() <= 20).sum()
    print(f"Wards where the two models agree within 20%: {agree} of {len(df)} "
          f"({agree/len(df)*100:.0f}%)")
    print("\nWards with the LARGEST disagreement between the two models")
    print("(good candidates for field verification):")
    print(df.reindex(df["percent_difference"].abs().sort_values(ascending=False).index)
          .head(10)[["area_name", TARGET_COLUMN, "poi_regression_predicted_waste_kg", "percent_difference"]]
          .to_string(index=False))

    print("\n" + "=" * 70)
    print("POI REGRESSION MODEL COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()