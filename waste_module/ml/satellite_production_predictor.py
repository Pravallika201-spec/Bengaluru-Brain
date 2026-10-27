import os
import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor


# =========================================================
# PATHS
# =========================================================

# ---------------------------------------------------------
# Fresh Sentinel-2 satellite features
# ---------------------------------------------------------

SATELLITE_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_features.csv"
)


# ---------------------------------------------------------
# Existing dataset containing:
# - land-use features
# - historical/training target
# ---------------------------------------------------------

TRAINING_DATASET = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_waste_dataset.csv"
)


# ---------------------------------------------------------
# Main trained satellite + land-use model
# ---------------------------------------------------------

MODEL_FILE = (
    "waste_module/satellite/outputs/"
    "satellite_waste_random_forest.joblib"
)


# ---------------------------------------------------------
# Output
# ---------------------------------------------------------

OUTPUT_DIR = (
    "waste_module/satellite/outputs"
)

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_production_waste_predictions.csv"
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
# COMPLETE MODEL FEATURES
# =========================================================

FEATURES = (
    SATELLITE_FEATURES
    + LANDUSE_FEATURES
)


# =========================================================
# LOAD FRESH SATELLITE DATA
# =========================================================

def load_satellite_data():

    print(
        "\nLoading fresh satellite features..."
    )

    if not os.path.exists(SATELLITE_FILE):

        raise FileNotFoundError(
            f"\nSatellite feature file not found:\n"
            f"{SATELLITE_FILE}"
        )

    df = pd.read_csv(
        SATELLITE_FILE
    )

    print(
        "Satellite rows:",
        len(df)
    )

    if "Satellite_Valid" not in df.columns:

        raise ValueError(
            "Satellite_Valid column is missing."
        )

    valid_count = int(
        df["Satellite_Valid"].sum()
    )

    invalid_count = int(
        (~df["Satellite_Valid"]).sum()
    )

    print(
        "Valid satellite rows:",
        valid_count
    )

    print(
        "Invalid satellite rows:",
        invalid_count
    )

    return df


# =========================================================
# LOAD TRAINING / LAND-USE DATA
# =========================================================

def load_training_data():

    print(
        "\nLoading land-use/training dataset..."
    )

    if not os.path.exists(TRAINING_DATASET):

        raise FileNotFoundError(
            f"\nTraining dataset not found:\n"
            f"{TRAINING_DATASET}"
        )

    df = pd.read_csv(
        TRAINING_DATASET
    )

    print(
        "Training rows:",
        len(df)
    )

    return df


# =========================================================
# MERGE SATELLITE + LAND USE
# =========================================================

def build_production_dataset(
    satellite_df,
    training_df
):

    print(
        "\nMerging fresh satellite data "
        "with land-use data..."
    )

    # -----------------------------------------------------
    # Check Grid_ID
    # -----------------------------------------------------

    if "Grid_ID" not in satellite_df.columns:

        raise ValueError(
            "Grid_ID missing from satellite dataset."
        )

    if "Grid_ID" not in training_df.columns:

        raise ValueError(
            "Grid_ID missing from training dataset."
        )


    # -----------------------------------------------------
    # Land-use columns
    # -----------------------------------------------------

    landuse_columns = [
        "Grid_ID",
        "Latitude",
        "Longitude"
    ] + LANDUSE_FEATURES


    missing_landuse = [
        column
        for column in landuse_columns
        if column not in training_df.columns
    ]


    if missing_landuse:

        print(
            "\nMissing land-use columns:"
        )

        for column in missing_landuse:

            print(
                " -",
                column
            )

        raise ValueError(
            "Required land-use columns are missing."
        )


    landuse = training_df[
        landuse_columns
    ].copy()


    # -----------------------------------------------------
    # Fresh satellite columns
    # -----------------------------------------------------

    satellite_columns = [
        "Grid_ID"
    ] + SATELLITE_FEATURES + [
        "valid_pixel_count",
        "Satellite_Valid"
    ]


    missing_satellite = [
        column
        for column in satellite_columns
        if column not in satellite_df.columns
    ]


    if missing_satellite:

        print(
            "\nMissing satellite columns:"
        )

        for column in missing_satellite:

            print(
                " -",
                column
            )

        raise ValueError(
            "Required satellite columns are missing."
        )


    satellite = satellite_df[
        satellite_columns
    ].copy()


    # -----------------------------------------------------
    # Merge
    # -----------------------------------------------------

    production = landuse.merge(
        satellite,
        on="Grid_ID",
        how="left",
        validate="one_to_one"
    )


    print(
        "Production rows after merge:",
        len(production)
    )


    # -----------------------------------------------------
    # Satellite matching
    # -----------------------------------------------------

    unmatched = production[
        "Satellite_Valid"
    ].isna().sum()


    print(
        "Satellite rows without match:",
        unmatched
    )


    # -----------------------------------------------------
    # Clean satellite validity
    # -----------------------------------------------------

    production["Satellite_Valid"] = (
        production["Satellite_Valid"]
        .fillna(False)
        .astype(bool)
    )


    production["valid_pixel_count"] = (
        pd.to_numeric(
            production["valid_pixel_count"],
            errors="coerce"
        )
        .fillna(0)
    )


    return production


# =========================================================
# LOAD MAIN SATELLITE + LAND-USE MODEL
# =========================================================

def load_main_model():

    print(
        "\nLoading trained satellite + land-use "
        "Random Forest model..."
    )

    if not os.path.exists(MODEL_FILE):

        raise FileNotFoundError(
            f"\nModel not found:\n{MODEL_FILE}"
        )


    model = joblib.load(
        MODEL_FILE
    )


    print(
        "Main model loaded successfully."
    )


    return model


# =========================================================
# TRAIN LAND-USE FALLBACK MODEL
# =========================================================

def train_landuse_fallback_model(
    training_df
):

    print(
        "\nTraining land-use fallback model..."
    )

    target_column = "estimated_daily_waste_kg"


    if target_column not in training_df.columns:

        raise ValueError(
            f"Fallback target '{target_column}' "
            "is missing from training dataset."
        )


    missing_features = [
        feature
        for feature in LANDUSE_FEATURES
        if feature not in training_df.columns
    ]


    if missing_features:

        print(
            "\nMissing fallback features:"
        )

        for feature in missing_features:

            print(
                " -",
                feature
            )

        raise ValueError(
            "Required land-use features are missing."
        )


    X = training_df[
        LANDUSE_FEATURES
    ].copy()


    y = pd.to_numeric(
        training_df[
            target_column
        ],
        errors="coerce"
    )


    # -----------------------------------------------------
    # Numeric conversion
    # -----------------------------------------------------

    X = X.apply(
        pd.to_numeric,
        errors="coerce"
    )


    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    )


    # -----------------------------------------------------
    # Median imputation
    # -----------------------------------------------------

    X = X.fillna(
        X.median()
    )


    # -----------------------------------------------------
    # Remove rows without target
    # -----------------------------------------------------

    valid_target = y.notna()


    X = X.loc[
        valid_target
    ]

    y = y.loc[
        valid_target
    ]


    print(
        "Fallback training rows:",
        len(X)
    )


    # -----------------------------------------------------
    # Land-use Random Forest
    # -----------------------------------------------------

    fallback_model = RandomForestRegressor(
        n_estimators=200,
        random_state=42,
        n_jobs=-1
    )


    fallback_model.fit(
        X,
        y
    )


    print(
        "Land-use fallback model trained successfully."
    )


    return fallback_model


# =========================================================
# PREPARE SATELLITE + LAND-USE FEATURES
# =========================================================

def prepare_main_features(
    production_df
):

    print(
        "\nPreparing main model features..."
    )


    missing = [
        feature
        for feature in FEATURES
        if feature not in production_df.columns
    ]


    if missing:

        print(
            "\nMissing model features:"
        )

        for feature in missing:

            print(
                " -",
                feature
            )

        raise ValueError(
            "Required prediction features are missing."
        )


    X = production_df[
        FEATURES
    ].copy()


    # -----------------------------------------------------
    # Numeric conversion
    # -----------------------------------------------------

    X = X.apply(
        pd.to_numeric,
        errors="coerce"
    )


    # -----------------------------------------------------
    # Replace infinities
    # -----------------------------------------------------

    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    )


    # -----------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT use median satellite values for invalid
    # satellite grids.
    #
    # We only prepare the values here.
    # Valid satellite rows will be selected later.
    # -----------------------------------------------------

    return X


# =========================================================
# PREPARE LAND-USE FEATURES
# =========================================================

def prepare_landuse_features(
    production_df
):

    print(
        "\nPreparing land-use fallback features..."
    )


    X = production_df[
        LANDUSE_FEATURES
    ].copy()


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
# GENERATE PRODUCTION PREDICTIONS
# =========================================================

def generate_production_predictions(
    production_df,
    main_model,
    fallback_model
):

    print(
        "\nGenerating production waste predictions..."
    )


    total_rows = len(
        production_df
    )


    # -----------------------------------------------------
    # Create output array
    # -----------------------------------------------------

    predictions = np.zeros(
        total_rows,
        dtype=float
    )


    # -----------------------------------------------------
    # Identify satellite validity
    # -----------------------------------------------------

    satellite_valid_mask = (
        production_df[
            "Satellite_Valid"
        ]
        .astype(bool)
        .values
    )


    satellite_invalid_mask = (
        ~satellite_valid_mask
    )


    valid_count = int(
        satellite_valid_mask.sum()
    )

    invalid_count = int(
        satellite_invalid_mask.sum()
    )


    print(
        "Satellite-based predictions:",
        valid_count
    )

    print(
        "Land-use fallback predictions:",
        invalid_count
    )


    # =====================================================
    # 1. SATELLITE-VALID GRIDS
    # =====================================================

    if valid_count > 0:

        print(
            "\nPredicting valid satellite grids..."
        )


        X_main = prepare_main_features(
            production_df
        )


        valid_indices = np.where(
            satellite_valid_mask
        )[0]


        X_valid = X_main.iloc[
            valid_indices
        ].copy()


        # -------------------------------------------------
        # Handle missing values ONLY within valid rows.
        #
        # These are genuine satellite observations but
        # individual bands may still contain NaN.
        # -------------------------------------------------

        X_valid = X_valid.fillna(
            X_valid.median()
        )


        # -------------------------------------------------
        # Predict
        # -------------------------------------------------

        satellite_predictions = (
            main_model.predict(
                X_valid
            )
        )


        satellite_predictions = np.maximum(
            satellite_predictions,
            0
        )


        predictions[
            valid_indices
        ] = satellite_predictions


    # =====================================================
    # 2. SATELLITE-INVALID GRIDS
    # =====================================================

    if invalid_count > 0:

        print(
            "\nPredicting satellite-invalid grids "
            "using land-use fallback model..."
        )


        X_landuse = prepare_landuse_features(
            production_df
        )


        invalid_indices = np.where(
            satellite_invalid_mask
        )[0]


        X_invalid = X_landuse.iloc[
            invalid_indices
        ].copy()


        fallback_predictions = (
            fallback_model.predict(
                X_invalid
            )
        )


        fallback_predictions = np.maximum(
            fallback_predictions,
            0
        )


        predictions[
            invalid_indices
        ] = fallback_predictions


    print(
        "\nAll production predictions generated:",
        len(predictions)
    )


    return (
        predictions,
        satellite_valid_mask
    )


# =========================================================
# CLASSIFY WASTE RISK
# =========================================================

def classify_risk(
    predictions
):

    print(
        "\nClassifying waste risk..."
    )


    q50 = np.percentile(
        predictions,
        50
    )


    q75 = np.percentile(
        predictions,
        75
    )


    q90 = np.percentile(
        predictions,
        90
    )


    def classify(value):

        if value >= q90:

            return "CRITICAL"

        elif value >= q75:

            return "HIGH"

        elif value >= q50:

            return "MEDIUM"

        else:

            return "LOW"


    risk = [
        classify(value)
        for value in predictions
    ]


    return (
        risk,
        q50,
        q75,
        q90
    )


# =========================================================
# COLLECTION PRIORITY
# =========================================================

def calculate_priority(
    risk
):

    print(
        "\nCalculating collection priority..."
    )


    priority_map = {
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4
    }


    return [
        priority_map[level]
        for level in risk
    ]


# =========================================================
# SAVE PRODUCTION RESULTS
# =========================================================

def save_results(
    production_df,
    predictions,
    risk,
    priority,
    satellite_valid_mask
):

    print(
        "\nCreating production prediction dataset..."
    )


    result = pd.DataFrame()


    # -----------------------------------------------------
    # Grid identification
    # -----------------------------------------------------

    result["Grid_ID"] = (
        production_df[
            "Grid_ID"
        ].values
    )


    # -----------------------------------------------------
    # Coordinates
    # -----------------------------------------------------

    result["Latitude"] = (
        production_df[
            "Latitude"
        ].values
    )


    result["Longitude"] = (
        production_df[
            "Longitude"
        ].values
    )


    # -----------------------------------------------------
    # Satellite coverage information
    # -----------------------------------------------------

    result[
        "valid_pixel_count"
    ] = (
        production_df[
            "valid_pixel_count"
        ].values
    )


    result[
        "Satellite_Valid"
    ] = satellite_valid_mask


    # -----------------------------------------------------
    # Prediction source
    # -----------------------------------------------------

    result[
        "prediction_source"
    ] = np.where(
        satellite_valid_mask,
        "Sentinel-2 + Land-use",
        "Land-use fallback"
    )


    # -----------------------------------------------------
    # Satellite indices
    # -----------------------------------------------------

    for column in [
        "NDVI",
        "NDBI",
        "NDWI"
    ]:

        result[column] = (
            production_df[
                column
            ].values
        )


    # -----------------------------------------------------
    # Prediction
    # -----------------------------------------------------

    result[
        "predicted_daily_waste_kg"
    ] = predictions


    # -----------------------------------------------------
    # Risk
    # -----------------------------------------------------

    result[
        "waste_risk"
    ] = risk


    # -----------------------------------------------------
    # Collection priority
    # -----------------------------------------------------

    result[
        "collection_priority"
    ] = priority


    # -----------------------------------------------------
    # Sort
    # -----------------------------------------------------

    result = result.sort_values(
        by=[
            "collection_priority",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False
        ]
    )


    result = result.reset_index(
        drop=True
    )


    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    result.to_csv(
        OUTPUT_FILE,
        index=False
    )


    print(
        "\nProduction prediction dataset saved:"
    )


    print(
        OUTPUT_FILE
    )


    return result


# =========================================================
# DISPLAY SUMMARY
# =========================================================

def display_summary(
    result,
    q50,
    q75,
    q90
):

    print(
        "\n"
        + "=" * 70
    )


    print(
        "FRESH SATELLITE PRODUCTION "
        "WASTE PREDICTION SUMMARY"
    )


    print(
        "=" * 70
    )


    # -----------------------------------------------------
    # Overall
    # -----------------------------------------------------

    print(
        "\nTotal grids:",
        len(result)
    )


    print(
        "Valid satellite grids:",
        int(
            result[
                "Satellite_Valid"
            ].sum()
        )
    )


    print(
        "Invalid satellite grids:",
        int(
            (
                ~result[
                    "Satellite_Valid"
                ]
            ).sum()
        )
    )


    # -----------------------------------------------------
    # Prediction sources
    # -----------------------------------------------------

    print(
        "\nPrediction sources:"
    )


    print(
        result[
            "prediction_source"
        ]
        .value_counts()
        .to_string()
    )


    # -----------------------------------------------------
    # Prediction statistics
    # -----------------------------------------------------

    print(
        "\nPrediction statistics:"
    )


    print(
        result[
            "predicted_daily_waste_kg"
        ]
        .describe()
        .to_string()
    )


    # -----------------------------------------------------
    # Risk thresholds
    # -----------------------------------------------------

    print(
        "\nRisk thresholds:"
    )


    print(
        f"MEDIUM   : {q50:.2f} kg"
    )


    print(
        f"HIGH     : {q75:.2f} kg"
    )


    print(
        f"CRITICAL : {q90:.2f} kg"
    )


    # -----------------------------------------------------
    # Risk distribution
    # -----------------------------------------------------

    print(
        "\nRisk distribution:"
    )


    print(
        result[
            "waste_risk"
        ]
        .value_counts()
        .to_string()
    )


    # -----------------------------------------------------
    # Priority distribution
    # -----------------------------------------------------

    print(
        "\nCollection priority:"
    )


    print(
        result[
            "collection_priority"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )


    # -----------------------------------------------------
    # Risk by prediction source
    # -----------------------------------------------------

    print(
        "\nRisk by prediction source:"
    )


    print(
        pd.crosstab(
            result[
                "prediction_source"
            ],
            result[
                "waste_risk"
            ]
        ).to_string()
    )


    # -----------------------------------------------------
    # Top 20 grids
    # -----------------------------------------------------

    print(
        "\nTop 20 priority grids:"
    )


    print(
        result[
            [
                "Grid_ID",
                "predicted_daily_waste_kg",
                "waste_risk",
                "collection_priority",
                "Satellite_Valid",
                "valid_pixel_count",
                "prediction_source"
            ]
        ]
        .head(20)
        .to_string(
            index=False
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=" * 70
    )


    print(
        "BENGALURU FRESH SATELLITE "
        "PRODUCTION WASTE PREDICTION"
    )


    print(
        "=" * 70
    )


    # -----------------------------------------------------
    # 1. Load fresh satellite observations
    # -----------------------------------------------------

    satellite_df = load_satellite_data()


    # -----------------------------------------------------
    # 2. Load training / land-use dataset
    # -----------------------------------------------------

    training_df = load_training_data()


    # -----------------------------------------------------
    # 3. Merge fresh satellite + land use
    # -----------------------------------------------------

    production_df = build_production_dataset(
        satellite_df,
        training_df
    )


    # -----------------------------------------------------
    # 4. Load main trained model
    # -----------------------------------------------------

    main_model = load_main_model()


    # -----------------------------------------------------
    # 5. Train land-use fallback model
    # -----------------------------------------------------

    fallback_model = train_landuse_fallback_model(
        training_df
    )


    # -----------------------------------------------------
    # 6. Generate predictions
    # -----------------------------------------------------

    (
        predictions,
        satellite_valid_mask
    ) = generate_production_predictions(
        production_df,
        main_model,
        fallback_model
    )


    # -----------------------------------------------------
    # 7. Risk classification
    # -----------------------------------------------------

    (
        risk,
        q50,
        q75,
        q90
    ) = classify_risk(
        predictions
    )


    # -----------------------------------------------------
    # 8. Collection priority
    # -----------------------------------------------------

    priority = calculate_priority(
        risk
    )


    # -----------------------------------------------------
    # 9. Save
    # -----------------------------------------------------

    result = save_results(
        production_df,
        predictions,
        risk,
        priority,
        satellite_valid_mask
    )


    # -----------------------------------------------------
    # 10. Display summary
    # -----------------------------------------------------

    display_summary(
        result,
        q50,
        q75,
        q90
    )


    print(
        "\n"
        + "=" * 70
    )


    print(
        "FRESH SATELLITE PRODUCTION "
        "PREDICTION COMPLETED"
    )


    print(
        "=" * 70
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()