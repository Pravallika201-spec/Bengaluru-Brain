"""
Tests for the generic T+120 model-metadata interface
(get_model_metadata() / GET /api/traffic/forecast-t120/model-info),
introduced so the pipeline can be retrained on more collected real data
without any frontend or hardcoded-constant change.

Also covers the honest, computed-not-asserted comparison against the
persistence baseline (train_t120_preliminary_model.py's
baseline_comparison block), and that unsupported/insufficient-data cases
never fabricate a value.
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import forecasting.t120_preliminary_service as svc


def test_model_metadata_reads_the_real_saved_training_report():
    meta = svc.get_model_metadata()
    assert meta["available"] is True
    # Every field must come straight from the real, saved report -- cross
    # check against a fresh read of the same file.
    with open(svc.METRICS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    assert meta["total_genuine_pairs"] == raw["total_genuine_pairs"]
    assert meta["unique_segments"] == raw["unique_segments"]
    assert meta["split"] == raw["split"]
    assert meta["leakage_check"] == raw["leakage_check"]
    assert meta["test_metrics"] == raw["metrics"]["test"]
    assert meta["persistence_baseline_test_metrics"] == raw["persistence_baseline_metrics"]["test"]


def test_model_metadata_reports_leakage_check_result_honestly():
    meta = svc.get_model_metadata()
    assert meta["available"] is True
    assert meta["leakage_check"]["leakage_detected"] is False
    assert meta["leakage_check"]["train_before_val"] is True
    assert meta["leakage_check"]["val_before_test"] is True


def test_model_metadata_includes_honest_baseline_comparison_not_fabricated():
    meta = svc.get_model_metadata()
    assert meta["available"] is True
    comparison = meta["baseline_comparison"]
    assert comparison is not None
    # Recompute the comparison independently from the same real numbers
    # and confirm it matches -- this is a pure, honest computation, not
    # an assertion of a specific favorable outcome.
    test_m = meta["test_metrics"]
    base_m = meta["persistence_baseline_test_metrics"]
    expected_mae = test_m["mae"] < base_m["mae"]
    expected_rmse = test_m["rmse"] < base_m["rmse"]
    expected_r2 = test_m["r2"] > base_m["r2"]
    assert comparison["beats_baseline_mae"] == expected_mae
    assert comparison["beats_baseline_rmse"] == expected_rmse
    assert comparison["beats_baseline_r2"] == expected_r2
    assert comparison["beats_baseline_overall"] == (expected_mae and expected_rmse and expected_r2)


def test_model_metadata_unavailable_when_report_missing(monkeypatch):
    monkeypatch.setattr(svc, "_metrics_cache", {})
    monkeypatch.setattr(svc, "_metrics_load_attempted", True)
    monkeypatch.setattr(svc, "_bundle", None)
    monkeypatch.setattr(svc, "_load_error", None)
    monkeypatch.setattr(svc, "_load_attempted", True)

    meta = svc.get_model_metadata()
    assert meta["available"] is False
    assert "reason" in meta


def test_training_hours_label_reads_real_readiness_report():
    label = svc._training_hours_label()
    assert label != "unknown"
    assert label.startswith("~")
    with open(svc.READINESS_REPORT_PATH, encoding="utf-8") as f:
        readiness = json.load(f)
    assert readiness["time_span_start"] and readiness["time_span_end"]


def test_training_hours_label_honest_fallback_when_readiness_report_missing(monkeypatch):
    monkeypatch.setattr(svc, "_readiness_cache", {})
    monkeypatch.setattr(svc, "_readiness_load_attempted", True)
    assert svc._training_hours_label() == "unknown"
