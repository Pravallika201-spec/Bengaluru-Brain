import os
import numpy as np
import pandas as pd


# =========================================================
# PATHS
# =========================================================

INPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_production_waste_predictions.csv"
)

OUTPUT_DIR = (
    "waste_module/satellite/outputs"
)

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_overflow_risk_predictions.csv"
)


# =========================================================
# CONFIGURATION
# =========================================================

# Minimum valid satellite pixels considered useful.
SATELLITE_PIXEL_THRESHOLD = 5


# =========================================================
# LOAD PRODUCTION PREDICTIONS
# =========================================================

def load_production_predictions():

    print("\nLoading production waste predictions...")

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"\nProduction prediction file not found:\n"
            f"{INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    print(
        "Production rows:",
        len(df)
    )

    required_columns = [
        "Grid_ID",
        "Latitude",
        "Longitude",
        "valid_pixel_count",
        "Satellite_Valid",
        "prediction_source",
        "predicted_daily_waste_kg",
        "waste_risk",
        "collection_priority"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        print("\nMissing columns:")

        for column in missing:
            print(" -", column)

        raise ValueError(
            "Required production prediction columns are missing."
        )

    return df


# =========================================================
# CLEAN DATA
# =========================================================

def clean_data(df):

    print("\nCleaning production data...")

    numeric_columns = [
        "valid_pixel_count",
        "predicted_daily_waste_kg",
        "collection_priority"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["predicted_daily_waste_kg"] = (
        df["predicted_daily_waste_kg"]
        .fillna(0)
        .clip(lower=0)
    )

    df["valid_pixel_count"] = (
        df["valid_pixel_count"]
        .fillna(0)
        .clip(lower=0)
    )

    df["Satellite_Valid"] = (
        df["Satellite_Valid"]
        .fillna(False)
        .astype(bool)
    )

    return df


# =========================================================
# CALCULATE WASTE PRESSURE
# =========================================================

def calculate_waste_pressure(df):

    print("\nCalculating waste pressure...")

    waste = df[
        "predicted_daily_waste_kg"
    ].values

    # Percentile-based normalization.
    #
    # This does NOT claim that a specific kg value
    # physically causes overflow.
    #
    # It measures how high the predicted waste is
    # compared with the other Bengaluru grids.

    q25 = np.percentile(
        waste,
        25
    )

    q50 = np.percentile(
        waste,
        50
    )

    q75 = np.percentile(
        waste,
        75
    )

    q90 = np.percentile(
        waste,
        90
    )

    q95 = np.percentile(
        waste,
        95
    )

    print(
        f"25th percentile : {q25:.2f} kg"
    )

    print(
        f"50th percentile : {q50:.2f} kg"
    )

    print(
        f"75th percentile : {q75:.2f} kg"
    )

    print(
        f"90th percentile : {q90:.2f} kg"
    )

    print(
        f"95th percentile : {q95:.2f} kg"
    )

    # Percentile rank for every grid.

    ranks = pd.Series(
        waste
    ).rank(
        pct=True
    ).values

    df["waste_pressure_score"] = (
        ranks * 100
    )

    return (
        df,
        q25,
        q50,
        q75,
        q90,
        q95
    )


# =========================================================
# SATELLITE CONFIDENCE
# =========================================================

def calculate_satellite_confidence(df):

    print(
        "\nCalculating satellite observation confidence..."
    )

    confidence = []

    for _, row in df.iterrows():

        valid_pixels = (
            row["valid_pixel_count"]
        )

        satellite_valid = (
            row["Satellite_Valid"]
        )

        if (
            satellite_valid
            and valid_pixels >= 500
        ):

            level = "HIGH"

        elif (
            satellite_valid
            and valid_pixels >= 50
        ):

            level = "MEDIUM"

        elif (
            satellite_valid
            and valid_pixels >= SATELLITE_PIXEL_THRESHOLD
        ):

            level = "LOW"

        else:

            level = "NONE"

        confidence.append(
            level
        )

    df["satellite_confidence"] = confidence

    return df


# =========================================================
# CALCULATE OVERFLOW RISK SCORE
# =========================================================

def calculate_overflow_score(df):

    print(
        "\nCalculating overflow risk proxy..."
    )

    scores = []

    for _, row in df.iterrows():

        # -------------------------------------------------
        # 1. Waste pressure
        # -------------------------------------------------

        waste_score = (
            float(
                row["waste_pressure_score"]
            )
        )

        # -------------------------------------------------
        # 2. Existing production waste risk
        # -------------------------------------------------

        risk = str(
            row["waste_risk"]
        ).upper()

        risk_score_map = {

            "LOW": 10,

            "MEDIUM": 35,

            "HIGH": 70,

            "CRITICAL": 95

        }

        risk_score = risk_score_map.get(
            risk,
            10
        )

        # -------------------------------------------------
        # 3. Collection urgency
        # -------------------------------------------------

        priority = int(
            row["collection_priority"]
        )

        priority_score_map = {

            1: 100,

            2: 75,

            3: 45,

            4: 15

        }

        priority_score = priority_score_map.get(
            priority,
            15
        )

        # -------------------------------------------------
        # 4. Combine signals
        # -------------------------------------------------

        overflow_score = (

            0.50 * waste_score

            + 0.30 * risk_score

            + 0.20 * priority_score

        )

        scores.append(
            min(
                max(
                    overflow_score,
                    0
                ),
                100
            )
        )

    df["overflow_risk_score"] = scores

    return df


# =========================================================
# CLASSIFY OVERFLOW RISK
# =========================================================

def classify_overflow_risk(df):

    print(
        "\nClassifying overflow risk..."
    )

    def classify(score):

        if score >= 80:

            return "CRITICAL"

        elif score >= 60:

            return "HIGH"

        elif score >= 35:

            return "MEDIUM"

        else:

            return "LOW"

    df["overflow_risk"] = (
        df[
            "overflow_risk_score"
        ]
        .apply(classify)
    )

    return df


# =========================================================
# CALCULATE FINAL COLLECTION PRIORITY
# =========================================================

def calculate_final_priority(df):

    print(
        "\nCalculating final collection priority..."
    )

    priority_map = {

        "CRITICAL": 1,

        "HIGH": 2,

        "MEDIUM": 3,

        "LOW": 4

    }

    df["overflow_collection_priority"] = (
        df[
            "overflow_risk"
        ]
        .map(
            priority_map
        )
    )

    return df


# =========================================================
# ADD CONFIDENCE FLAG
# =========================================================

def calculate_prediction_confidence(df):

    print(
        "\nCalculating prediction confidence..."
    )

    confidence = []

    for _, row in df.iterrows():

        source = str(
            row["prediction_source"]
        )

        satellite_confidence = str(
            row["satellite_confidence"]
        )

        if (
            source
            == "Sentinel-2 + Land-use"
            and satellite_confidence == "HIGH"
        ):

            level = "HIGH"

        elif (
            source
            == "Sentinel-2 + Land-use"
            and satellite_confidence
            in ["MEDIUM", "LOW"]
        ):

            level = "MEDIUM"

        else:

            level = "LOW"

        confidence.append(
            level
        )

    df["prediction_confidence"] = (
        confidence
    )

    return df


# =========================================================
# SAVE RESULTS
# =========================================================

def save_results(df):

    print(
        "\nCreating overflow risk dataset..."
    )

    columns = [

        "Grid_ID",

        "Latitude",

        "Longitude",

        "valid_pixel_count",

        "Satellite_Valid",

        "prediction_source",

        "prediction_confidence",

        "satellite_confidence",

        "predicted_daily_waste_kg",

        "waste_risk",

        "collection_priority",

        "waste_pressure_score",

        "overflow_risk_score",

        "overflow_risk",

        "overflow_collection_priority"

    ]

    result = df[
        columns
    ].copy()

    # Highest overflow risk first.

    result = result.sort_values(

        by=[
            "overflow_collection_priority",
            "overflow_risk_score",
            "predicted_daily_waste_kg"
        ],

        ascending=[
            True,
            False,
            False
        ]

    )

    result = result.reset_index(
        drop=True
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nOverflow risk dataset saved:"
    )

    print(
        OUTPUT_FILE
    )

    return result


# =========================================================
# DISPLAY SUMMARY
# =========================================================

def display_summary(df):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BENGALURU OVERFLOW RISK ENGINE SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        "\nTotal grids:",
        len(df)
    )

    print(
        "\nOverflow risk distribution:"
    )

    print(
        df[
            "overflow_risk"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nOverflow collection priority:"
    )

    print(
        df[
            "overflow_collection_priority"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print(
        "\nPrediction confidence:"
    )

    print(
        df[
            "prediction_confidence"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nPrediction source:"
    )

    print(
        df[
            "prediction_source"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nOverflow risk score statistics:"
    )

    print(
        df[
            "overflow_risk_score"
        ]
        .describe()
        .to_string()
    )

    print(
        "\nTop 20 overflow-risk grids:"
    )

    print(
        df[
            [
                "Grid_ID",
                "predicted_daily_waste_kg",
                "waste_pressure_score",
                "overflow_risk_score",
                "overflow_risk",
                "overflow_collection_priority",
                "prediction_source",
                "prediction_confidence"
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

    print("=" * 70)

    print(
        "BENGALURU OVERFLOW RISK ENGINE"
    )

    print("=" * 70)

    # -----------------------------------------------------
    # 1. Load production predictions
    # -----------------------------------------------------

    df = (
        load_production_predictions()
    )

    # -----------------------------------------------------
    # 2. Clean
    # -----------------------------------------------------

    df = clean_data(
        df
    )

    # -----------------------------------------------------
    # 3. Waste pressure
    # -----------------------------------------------------

    (
        df,
        q25,
        q50,
        q75,
        q90,
        q95
    ) = calculate_waste_pressure(
        df
    )

    # -----------------------------------------------------
    # 4. Satellite confidence
    # -----------------------------------------------------

    df = calculate_satellite_confidence(
        df
    )

    # -----------------------------------------------------
    # 5. Overflow score
    # -----------------------------------------------------

    df = calculate_overflow_score(
        df
    )

    # -----------------------------------------------------
    # 6. Overflow classification
    # -----------------------------------------------------

    df = classify_overflow_risk(
        df
    )

    # -----------------------------------------------------
    # 7. Collection priority
    # -----------------------------------------------------

    df = calculate_final_priority(
        df
    )

    # -----------------------------------------------------
    # 8. Prediction confidence
    # -----------------------------------------------------

    df = calculate_prediction_confidence(
        df
    )

    # -----------------------------------------------------
    # 9. Save
    # -----------------------------------------------------

    result = save_results(
        df
    )

    # -----------------------------------------------------
    # 10. Summary
    # -----------------------------------------------------

    display_summary(
        result
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "OVERFLOW RISK ANALYSIS COMPLETED"
    )

    print(
        "=" * 70
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()