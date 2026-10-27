import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "realtime_prediction_dataset.csv"
MODEL_FILE = "realtime_traffic_baseline.pkl"


print("=" * 60)
print("REAL-TIME TRAFFIC BASELINE MODEL")
print("=" * 60)


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_FILE)

df["timestamp"] = pd.to_datetime(
    df["timestamp"]
)

print("Rows:", len(df))
print(
    "Locations:",
    df["traffic_location"].nunique()
)


# ============================================================
# SORT CHRONOLOGICALLY
# ============================================================

df = df.sort_values(
    "timestamp"
).reset_index(drop=True)


# ============================================================
# ENCODE LOCATION
# ============================================================

location_codes = {
    location: index
    for index, location
    in enumerate(
        sorted(
            df["traffic_location"].unique()
        )
    )
}

df["location_code"] = (
    df["traffic_location"]
    .map(location_codes)
)


# ============================================================
# FEATURES
# ============================================================

feature_columns = [

    "current_speed_kmh",

    "free_flow_speed_kmh",

    "current_travel_time_sec",

    "free_flow_travel_time_sec",

    "delay_sec",

    "delay_percent",

    "confidence",

    "hour",

    "minute",

    "day_of_week",

    "is_weekend",

    "minutes_since_midnight",

    "location_code"
]


target_column = "target_speed_next"


# ============================================================
# CHECK FEATURES
# ============================================================

missing_features = [
    column
    for column in feature_columns
    if column not in df.columns
]

if missing_features:

    print(
        "Missing features:",
        missing_features
    )

    raise SystemExit(1)


# ============================================================
# CHRONOLOGICAL SPLIT
# ============================================================

print()
print("=" * 60)
print("CHRONOLOGICAL SPLIT")
print("=" * 60)


unique_times = sorted(
    df["timestamp"].unique()
)


n_times = len(unique_times)

train_end = int(
    n_times * 0.70
)

validation_end = int(
    n_times * 0.85
)


train_times = set(
    unique_times[:train_end]
)

validation_times = set(
    unique_times[
        train_end:validation_end
    ]
)

test_times = set(
    unique_times[
        validation_end:
    ]
)


train_df = df[
    df["timestamp"].isin(
        train_times
    )
].copy()


validation_df = df[
    df["timestamp"].isin(
        validation_times
    )
].copy()


test_df = df[
    df["timestamp"].isin(
        test_times
    )
].copy()


print(
    "Training rows:",
    len(train_df)
)

print(
    "Validation rows:",
    len(validation_df)
)

print(
    "Testing rows:",
    len(test_df)
)


# ============================================================
# FEATURES / TARGET
# ============================================================

X_train = train_df[
    feature_columns
]

y_train = train_df[
    target_column
]


X_validation = validation_df[
    feature_columns
]

y_validation = validation_df[
    target_column
]


X_test = test_df[
    feature_columns
]

y_test = test_df[
    target_column
]


# ============================================================
# RANDOM FOREST
# ============================================================

print()
print("=" * 60)
print("TRAINING RANDOM FOREST")
print("=" * 60)


model = RandomForestRegressor(

    n_estimators=200,

    max_depth=8,

    min_samples_leaf=3,

    random_state=42,

    n_jobs=-1
)


model.fit(
    X_train,
    y_train
)


print(
    "Training completed."
)


# ============================================================
# EVALUATION FUNCTION
# ============================================================

def evaluate(
    name,
    y_true,
    predictions
):

    mae = mean_absolute_error(
        y_true,
        predictions
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            predictions
        )
    )

    r2 = r2_score(
        y_true,
        predictions
    )

    print()
    print(name)

    print(
        "MAE  :",
        round(mae, 3),
        "km/h"
    )

    print(
        "RMSE :",
        round(rmse, 3),
        "km/h"
    )

    print(
        "R²   :",
        round(r2, 3)
    )

    return {
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2
    }


# ============================================================
# VALIDATION
# ============================================================

validation_predictions = (
    model.predict(
        X_validation
    )
)


validation_metrics = evaluate(
    "VALIDATION",
    y_validation,
    validation_predictions
)


# ============================================================
# FINAL TEST
# ============================================================

test_predictions = (
    model.predict(
        X_test
    )
)


test_metrics = evaluate(
    "TEST",
    y_test,
    test_predictions
)


# ============================================================
# PERSISTENCE BASELINE
# ============================================================

print()
print("=" * 60)
print("PERSISTENCE BASELINE")
print("=" * 60)


persistence_predictions = (
    test_df[
        "current_speed_kmh"
    ].values
)


persistence_metrics = evaluate(
    "CURRENT SPEED → NEXT SPEED",
    y_test,
    persistence_predictions
)


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

print()
print("=" * 60)
print("FEATURE IMPORTANCE")
print("=" * 60)


importance = pd.DataFrame({

    "feature":
        feature_columns,

    "importance":
        model.feature_importances_

}).sort_values(
    "importance",
    ascending=False
)


print(
    importance.to_string(
        index=False
    )
)


# ============================================================
# SAMPLE PREDICTIONS
# ============================================================

results = test_df[
    [
        "timestamp",
        "target_timestamp",
        "traffic_location",
        "current_speed_kmh",
        "target_speed_next"
    ]
].copy()


results[
    "predicted_speed"
] = test_predictions


results[
    "absolute_error"
] = (

    abs(
        results[
            "target_speed_next"
        ]

        -

        results[
            "predicted_speed"
        ]
    )
)


print()
print("=" * 60)
print("SAMPLE TEST PREDICTIONS")
print("=" * 60)


print(
    results
    .head(30)
    .to_string(index=False)
)


# ============================================================
# SAVE MODEL
# ============================================================

import pickle


model_package = {

    "model": model,

    "feature_columns":
        feature_columns,

    "location_codes":
        location_codes,

    "test_metrics":
        test_metrics,

    "persistence_metrics":
        persistence_metrics
}


with open(
    MODEL_FILE,
    "wb"
) as file:

    pickle.dump(
        model_package,
        file
    )


# ============================================================
# SAVE PREDICTIONS
# ============================================================

results.to_csv(
    "realtime_model_predictions.csv",
    index=False
)


print()
print("=" * 60)
print("REAL-TIME BASELINE MODEL COMPLETE")
print("=" * 60)

print(
    "Model saved:",
    MODEL_FILE
)

print(
    "Predictions saved:",
    "realtime_model_predictions.csv"
)