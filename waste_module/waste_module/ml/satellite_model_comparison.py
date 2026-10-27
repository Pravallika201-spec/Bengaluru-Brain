import os
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)


# =========================================================
# PATHS
# =========================================================

INPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_waste_dataset.csv"
)

OUTPUT_DIR = (
    "waste_module/satellite/outputs"
)

RESULT_FILE = (
    "waste_module/satellite/outputs/"
    "model_comparison_results.csv"
)


# =========================================================
# TARGET
# =========================================================

TARGET = "estimated_daily_waste_kg"


# =========================================================
# SATELLITE FEATURES
# =========================================================

SATELLITE_FEATURES = [
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


# =========================================================
# LAND-USE FEATURES
# =========================================================

LANDUSE_FEATURES = [
    "residential_ratio",
    "commercial_ratio",
    "industrial_ratio",
    "institutional_ratio",
    "green_space_ratio",
    "agricultural_ratio",
    "recreational_ratio",
    "construction_ratio",
    "transport_ratio",
    "water_ratio",
    "waste_utility_ratio",
    "religious_ratio",
    "military_ratio",
    "other_ratio",
    "commercial_intensity",
    "residential_intensity",
    "industrial_intensity",
    "institutional_intensity",
    "recreational_intensity"
]


# =========================================================
# LOAD DATA
# =========================================================

def load_data():

    print("\nLoading dataset...")

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"Dataset not found:\n{INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    print("Rows:", len(df))
    print("Columns:", len(df.columns))

    return df


# =========================================================
# PREPARE FEATURES
# =========================================================

def prepare_features(df, features):

    X = df[features].copy()

    X = X.apply(
        pd.to_numeric,
        errors="coerce"
    )

    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    )

    X = X.fillna(
        X.median()
    )

    return X


# =========================================================
# TRAIN AND EVALUATE
# =========================================================

def train_and_evaluate(
    X,
    y,
    model_name
):

    print(
        f"\nTraining: {model_name}"
    )

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42
        )
    )

    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=18,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )

    model.fit(
        X_train,
        y_train
    )

    predictions = model.predict(
        X_test
    )

    mae = mean_absolute_error(
        y_test,
        predictions
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions
        )
    )

    r2 = r2_score(
        y_test,
        predictions
    )

    print(
        f"MAE  : {mae:.2f} kg"
    )

    print(
        f"RMSE : {rmse:.2f} kg"
    )

    print(
        f"R²   : {r2:.4f}"
    )

    return {
        "Model": model_name,
        "Features": len(X.columns),
        "MAE_kg": mae,
        "RMSE_kg": rmse,
        "R2": r2
    }


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)

    print(
        "SATELLITE VS LAND-USE "
        "WASTE PREDICTION COMPARISON"
    )

    print("=" * 60)

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    df = load_data()

    # -----------------------------------------------------
    # Check target
    # -----------------------------------------------------

    if TARGET not in df.columns:

        raise ValueError(
            f"Target '{TARGET}' not found."
        )

    y = pd.to_numeric(
        df[TARGET],
        errors="coerce"
    )

    # -----------------------------------------------------
    # Remove invalid target rows
    # -----------------------------------------------------

    valid = y.notna()

    df = df.loc[
        valid
    ].copy()

    y = y.loc[
        valid
    ]

    print(
        "\nValid target rows:",
        len(df)
    )

    # -----------------------------------------------------
    # Prepare three datasets
    # -----------------------------------------------------

    print(
        "\nPreparing feature groups..."
    )

    X_satellite = prepare_features(
        df,
        SATELLITE_FEATURES
    )

    X_landuse = prepare_features(
        df,
        LANDUSE_FEATURES
    )

    X_combined = prepare_features(
        df,
        SATELLITE_FEATURES
        + LANDUSE_FEATURES
    )

    # -----------------------------------------------------
    # Run models
    # -----------------------------------------------------

    results = []

    results.append(
        train_and_evaluate(
            X_satellite,
            y,
            "Satellite Only"
        )
    )

    results.append(
        train_and_evaluate(
            X_landuse,
            y,
            "Land-Use Only"
        )
    )

    results.append(
        train_and_evaluate(
            X_combined,
            y,
            "Satellite + Land-Use"
        )
    )

    # -----------------------------------------------------
    # Results table
    # -----------------------------------------------------

    results_df = pd.DataFrame(
        results
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "FINAL MODEL COMPARISON"
    )

    print(
        "=" * 60
    )

    print(
        results_df.to_string(
            index=False
        )
    )

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    results_df.to_csv(
        RESULT_FILE,
        index=False
    )

    print(
        "\nComparison saved to:"
    )

    print(
        RESULT_FILE
    )

    # -----------------------------------------------------
    # Best model
    # -----------------------------------------------------

    best = results_df.loc[
        results_df["R2"].idxmax()
    ]

    print(
        "\nBest model:"
    )

    print(
        best["Model"]
    )

    print(
        f"Best R²: {best['R2']:.4f}"
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "MODEL COMPARISON COMPLETED"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()