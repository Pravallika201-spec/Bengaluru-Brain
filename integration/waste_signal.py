"""
Waste overflow severity (0-100) for a NAMED AREA, for USI fusion.

Reads directly from the waste module's real, populated processed data
(bengaluru_area_overflow_predictions.csv — 2,562 rows across 366 areas and
7 prediction dates). The MOST RECENT prediction_date row for the area is
used. No fabrication: if the area isn't in this file, severity is None and
the source says so plainly.

IMPORTANT PROVENANCE NOTE (found during the Sept 2026 waste-pipeline audit):
Overflow_Risk_Score is NOT output from the trained satellite RandomForest
model that also exists in this codebase (ml/satellite_waste_model.py,
ml/satellite_waste_random_forest.joblib) — that model is real but is not
in this live data path. The number actually feeding this file comes from
prediction/waste_estimator.py: a heuristic weighted sum of real OSM
land-use area ratios (WASTE_INTENSITY constants, not empirically fit) times
a fixed day-of-week/seasonal multiplier table
(prediction/temporal_predictor.py's DAY_MULTIPLIERS). Verified directly:
the same grid cell's underlying estimated_daily_waste_kg is byte-identical
across all 7 stored dates — only the multiplier changes. So this is a real,
deterministic, land-use-based estimate, not a validated ML prediction and
not a live day-to-day forecast. Labeled "WASTE_HEURISTIC_MODEL" below, not
"WASTE_MODEL_REAL", to avoid overstating it as AI/ML output.

CITIZEN-REPORT ESCALATION: if real citizen reports have been submitted for
this area in the last 7 days (via the waste dashboard's Citizen Reports
page -> waste_module/waste_module/backend/citizen_reports_store.py), a
small bounded bonus is added on top of the model's score: +5 per report,
capped at +15 total. This is a real, documented, transparent adjustment
driven by actual submitted reports — never a fabricated bump — and is
reported separately in the result so a caller can see exactly how much of
the score came from the model vs. from citizen reports.
"""
import os
import sys
import pandas as pd

WASTE_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "waste_module", "waste_module", "data", "processed",
    "bengaluru_area_overflow_predictions.csv",
)
WASTE_MODULE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "waste_module", "waste_module",
)
if WASTE_MODULE_DIR not in sys.path:
    sys.path.insert(0, WASTE_MODULE_DIR)

CITIZEN_BONUS_PER_REPORT = 5.0
CITIZEN_BONUS_CAP = 15.0

_cache = {"df": None}


def _citizen_escalation(area_name):
    try:
        from backend import citizen_reports_store
        counts = citizen_reports_store.get_report_counts_by_area(within_days=7)
    except Exception:
        return 0.0, 0
    n = counts.get(area_name, 0)
    bonus = min(CITIZEN_BONUS_CAP, n * CITIZEN_BONUS_PER_REPORT)
    return bonus, n


def _load():
    if _cache["df"] is None:
        if not os.path.exists(WASTE_DATA_PATH):
            raise FileNotFoundError(WASTE_DATA_PATH)
        df = pd.read_csv(WASTE_DATA_PATH)
        df["prediction_date"] = pd.to_datetime(df["prediction_date"])
        _cache["df"] = df
    return _cache["df"]


def get_waste_severity(area_name):
    try:
        df = _load()
    except FileNotFoundError as e:
        return {"area_name": area_name, "severity": None, "source": "NO_DATA",
                "detail": f"Waste data file missing: {e}"}

    norm = area_name.strip().lower()
    matches = df[df["area_name"].str.lower().str.strip() == norm]
    if matches.empty:
        return {
            "area_name": area_name,
            "severity": None,
            "source": "NO_DATA",
            "detail": f"'{area_name}' is not one of the 366 areas in the waste module's processed data.",
        }

    latest = matches.sort_values("prediction_date").iloc[-1]
    model_score = float(latest["Overflow_Risk_Score"])
    bonus, n_reports = _citizen_escalation(str(latest["area_name"]))
    final_score = min(100.0, model_score + bonus)

    detail = (f"{latest['Area_Overflow_Risk']} overflow risk "
              f"(collection priority: {latest['Collection_Priority']}) — "
              f"MODEL PREDICTION USING LAST AVAILABLE DATA ({latest['prediction_date'].date()}), "
              f"heuristic land-use estimate, not a live ML forecast.")
    if n_reports:
        detail += f" +{bonus:.0f} from {n_reports} citizen report(s) in the last 7 days."

    return {
        "area_name": latest["area_name"],
        "severity": final_score,
        "source": "WASTE_HEURISTIC_MODEL",
        "detail": detail,
        "prediction_date": str(latest["prediction_date"].date()),
        "total_predicted_waste_kg": float(latest["Total_Predicted_Waste_kg"]),
        "model_score": model_score,
        "citizen_report_bonus": bonus,
        "citizen_report_count_7d": n_reports,
    }
