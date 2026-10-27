import os
import joblib
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

MODEL_FILE = (
    "waste_module/satellite/outputs/"
    "satellite_waste_random_forest.joblib"
)

PREDICTION_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_waste_predictions.csv"
)


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
# TARGET
# =========================================================

TARGET = "estimated_daily_waste_kg"


# =========================================================
# LOAD DATA
# =========================================================

def load_data():

    print("\nLoading satellite-waste dataset...")

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"\nInput file not found:\n"
            f"{INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Rows:",
        len(df)
    )

    print(
        "Columns:",
        len(df.columns)
    )

    return df


# =========================================================
# CHECK FEATURES
# =========================================================

def check_features(df):

    print(
        "\nChecking required features..."
    )

    features = (
        SATELLITE_FEATURES
        + LANDUSE_FEATURES
    )

    missing = [
        feature
        for feature in features
        if feature not in df.columns
    ]

    if missing:

        print(
            "\nMissing features:"
        )

        for feature in missing:

            print(
                " -",
                feature
            )

        raise ValueError(
            "\nRequired features are missing."
        )

    if TARGET not in df.columns:

        raise ValueError(
            f"\nTarget column '{TARGET}' "
            "was not found."
        )

    print(
        "All required features found."
    )

    print(
        "Number of input features:",
        len(features)
    )


# =========================================================
# PREPARE DATA
# =========================================================

def prepare_data(df):

    print(
        "\nPreparing training data..."
    )

    features = (
        SATELLITE_FEATURES
        + LANDUSE_FEATURES
    )

    X = df[
        features
    ].copy()

    y = df[
        TARGET
    ].copy()

    # Convert everything to numeric.

    X = X.apply(
        pd.to_numeric,
        errors="coerce"
    )

    y = pd.to_numeric(
        y,
        errors="coerce"
    )

    # Replace infinite values.

    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    )

    y = y.replace(
        [np.inf, -np.inf],
        np.nan
    )

    # Remove rows where target is missing.

    valid_target = (
        y.notna()
    )

    X = X.loc[
        valid_target
    ]

    y = y.loc[
        valid_target
    ]

    # Fill missing feature values
    # with median values.

    X = X.fillna(
        X.median()
    )

    print(
        "Training rows:",
        len(X)
    )

    print(
        "Training features:",
        X.shape[1]
    )

    return X, y


# =========================================================
# TRAIN MODEL
# =========================================================

def train_model(
    X_train,
    y_train
):

    print(
        "\nTraining Random Forest model..."
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

    print(
        "Model training completed."
    )

    return model


# =========================================================
# EVALUATE MODEL
# =========================================================

def evaluate_model(
    model,
    X_test,
    y_test
):

    print(
        "\nEvaluating model..."
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
        "\nMODEL PERFORMANCE"
    )

    print(
        "------------------------------"
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

    return predictions


# =========================================================
# FEATURE IMPORTANCE
# =========================================================

def show_feature_importance(
    model,
    feature_names
):

    print(
        "\nFEATURE IMPORTANCE"
    )

    print(
        "------------------------------"
    )

    importance = pd.DataFrame(
        {
            "feature": feature_names,
            "importance": model.feature_importances_
        }
    )

    importance = importance.sort_values(
        "importance",
        ascending=False
    )

    print(
        importance.to_string(
            index=False
        )
    )

    return importance


# =========================================================
# SAVE MODEL
# =========================================================

def save_model(
    model
):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    joblib.dump(
        model,
        MODEL_FILE
    )

    print(
        "\nModel saved:"
    )

    print(
        MODEL_FILE
    )


# =========================================================
# SAVE PREDICTIONS
# =========================================================

def save_predictions(
    df,
    predictions,
    test_indices
):

    result = df.loc[
        test_indices
    ].copy()

    result[
        "satellite_predicted_waste_kg"
    ] = predictions

    result[
        "prediction_error_kg"
    ] = (
        result[
            TARGET
        ]
        - result[
            "satellite_predicted_waste_kg"
        ]
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    result.to_csv(
        PREDICTION_FILE,
        index=False
    )

    print(
        "\nPrediction file saved:"
    )

    print(
        PREDICTION_FILE
    )

    print(
        "Prediction rows:",
        len(result)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU SATELLITE-BASED "
        "WASTE PREDICTION ENGINE"
    )

    print("=" * 60)

    # -----------------------------------------------------
    # 1. Load data
    # -----------------------------------------------------

    df = load_data()

    # -----------------------------------------------------
    # 2. Check features
    # -----------------------------------------------------

    check_features(
        df
    )

    # -----------------------------------------------------
    # 3. Prepare data
    # -----------------------------------------------------

    X, y = prepare_data(
        df
    )

    # -----------------------------------------------------
    # 4. Train-test split
    # -----------------------------------------------------

    (
        X_train,
        X_test,
        y_train,
        y_test
    ) = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42
    )

    print(
        "\nDataset split:"
    )

    print(
        "Training rows:",
        len(X_train)
    )

    print(
        "Testing rows:",
        len(X_test)
    )

    # -----------------------------------------------------
    # 5. Train
    # -----------------------------------------------------

    model = train_model(
        X_train,
        y_train
    )

    # -----------------------------------------------------
    # 6. Evaluate
    # -----------------------------------------------------

    predictions = evaluate_model(
        model,
        X_test,
        y_test
    )

    # -----------------------------------------------------
    # 7. Feature importance
    # -----------------------------------------------------

    importance = show_feature_importance(
        model,
        X.columns
    )

    # -----------------------------------------------------
    # 8. Save model
    # -----------------------------------------------------

    save_model(
        model
    )

    # -----------------------------------------------------
    # 9. Save predictions
    # -----------------------------------------------------

    save_predictions(
        df,
        predictions,
        X_test.index
    )

    # -----------------------------------------------------
    # 10. Complete
    # -----------------------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    print(
        "SATELLITE WASTE PREDICTION COMPLETED"
    )

    print(
        "=" * 60
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()