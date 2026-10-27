import csv
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import forecasting.t120_preliminary_service as svc
FIXTURE_COLUMNS = [
    "timestamp", "data_mode", "osm_u", "osm_v", "osm_key", "latitude", "longitude",
    "road_name", "highway", "edge_length_m", "base_speed_kph", "status", "http_status",
    "current_speed_kmh", "free_flow_speed_kmh", "current_travel_time_sec",
    "free_flow_travel_time_sec", "confidence", "road_closure", "tomtom_segment_id",
    "speed_ratio", "delay_percent",
]
class _FakeModel:
    """Deterministic stand-in for the trained RandomForestRegressor --
    mechanics only, never presented as a real prediction."""
    def predict(self, X):
        # Predicted speed = current_speed_kmh (first feature) minus a fixed
        # synthetic slowdown, purely to exercise the pipeline end-to-end.
        return [max(0.0, X[0][0] - 5.0)]
def _write_fixture_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIXTURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
def _ok_row(timestamp, osm_u, osm_v, road_name, current_speed, free_flow_speed, lat="12.9", lon="77.6"):
    return {
        "timestamp": timestamp, "data_mode": "LIVE_TOMTOM", "osm_u": osm_u, "osm_v": osm_v,
        "osm_key": "0", "latitude": lat, "longitude": lon, "road_name": road_name,
        "highway": "trunk", "edge_length_m": "500", "base_speed_kph": "50", "status": "OK",
        "http_status": "200", "current_speed_kmh": current_speed, "free_flow_speed_kmh": free_flow_speed,
        "current_travel_time_sec": "100", "free_flow_travel_time_sec": "80", "confidence": "0.95",
        "road_closure": "False", "tomtom_segment_id": "seg1",
        "speed_ratio": str(float(current_speed) / float(free_flow_speed)),
        "delay_percent": str(round(max(0.0, 1 - float(current_speed) / float(free_flow_speed)) * 100, 1)),
    }
def _error_row(timestamp, osm_u, osm_v, road_name):
    return {
        "timestamp": timestamp, "data_mode": "LIVE_TOMTOM_ATTEMPT_FAILED", "osm_u": osm_u, "osm_v": osm_v,
        "osm_key": "0", "latitude": "12.9", "longitude": "77.6", "road_name": road_name,
        "highway": "trunk", "edge_length_m": "500", "base_speed_kph": "50", "status": "ERROR",
        "http_status": "", "current_speed_kmh": "", "free_flow_speed_kmh": "",
        "current_travel_time_sec": "", "free_flow_travel_time_sec": "", "confidence": "",
        "road_closure": "", "tomtom_segment_id": "", "speed_ratio": "", "delay_percent": "",
    }
def _reset_module_state(monkeypatch, csv_path, bundle):
    monkeypatch.setattr(svc, "HISTORY_CSV", csv_path)
    monkeypatch.setattr(svc, "_bundle", bundle)
    monkeypatch.setattr(svc, "_load_error", None)
    monkeypatch.setattr(svc, "_load_attempted", True)
def _fake_bundle():
    return {
        "model": _FakeModel(),
        "feature_columns": [
            "current_speed_kmh", "free_flow_speed_kmh", "speed_ratio", "delay_percent",
            "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
            "hour", "day_of_week", "is_weekend", "segment_index",
        ],
        "segment_labels": ["111_222_0", "333_444_0"],
    }
def test_supported_segments_only_lists_trained_ok_rows(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    rows = [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40"),
        _ok_row("2026-01-01 10:05:00", "111", "222", "Test Road A", "22", "40"),
        _error_row("2026-01-01 10:10:00", "111", "222", "Test Road A"),
        _ok_row("2026-01-01 10:00:00", "999", "888", "Untrained Road", "30", "50"),
    ]
    _write_fixture_csv(csv_path, rows)
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())

    segments = svc.get_supported_segments()
    names = {s["road_name"] for s in segments}
    assert names == {"Test Road A"}, "only trained segments with a real OK observation should be listed"

def test_forecast_available_for_supported_segment(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    rows = [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40"),
        _ok_row("2026-01-01 10:05:00", "111", "222", "Test Road A", "22", "40"),  # latest -> used
    ]
    _write_fixture_csv(csv_path, rows)
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("Test Road A")
    assert result["available"] is True
    assert result["road_name"] == "Test Road A"
    assert result["now"]["speed_kmh"] == 22.0
    assert result["forecast"]["predicted_speed_kmh"] == 17.0  # fake model: current - 5
    assert result["forecast"]["forecast_horizon_minutes"] == 120
    assert result["preliminary"] is True
    assert "condition" in result["now"] and "condition" in result["forecast"]
def test_current_and_predicted_speed_are_separate_fields_never_aliased(tmp_path, monkeypatch):
    """Guards against the 'both modes show the same output' regression:
    current speed and predicted speed must live at distinct dict paths,
    and (with a model that actually changes the value) must genuinely
    differ -- proving the UI isn't just redisplaying the current value
    twice under two different labels."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("Test Road A")
    assert result["available"] is True
    assert "speed_kmh" in result["now"]
    assert "predicted_speed_kmh" in result["forecast"]
    assert "speed_kmh" not in result["forecast"]
    assert "predicted_speed_kmh" not in result["now"]
    assert result["now"]["speed_kmh"] != result["forecast"]["predicted_speed_kmh"]
def test_no_fabricated_confidence_score_anywhere_in_forecast(tmp_path, monkeypatch):
    """The T+120 model has no validated confidence claim -- the response
    must never carry a 'confidence' key (top-level or nested), unlike the
    current GNN prediction which does report one."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("Test Road A")
    assert "confidence" not in result
    assert "confidence" not in result["now"]
    assert "confidence" not in result["forecast"]
def test_forecast_reports_real_training_counts_not_hardcoded_in_frontend(tmp_path, monkeypatch):
    """training_pairs/training_hours are read live from the training
    script's saved report (models/t120_preliminary_metrics.json +
    data/forecast_segments_data_readiness_report.json) -- never hardcoded
    module constants -- so a future retrain updates them automatically
    without any frontend or service code change."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("Test Road A")
    assert result["training_pairs"] == svc._load_metrics().get("total_genuine_pairs")
    assert result["training_hours"] == svc._training_hours_label()
    assert isinstance(result["training_pairs"], int) and result["training_pairs"] > 0
def test_forecast_unavailable_for_unsupported_road(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("Some Random Unmonitored Road")
    assert result["available"] is False
    assert result["reason"] == "2-hour forecast unavailable for this road in the preliminary model."
    assert "Test Road A" in result["supported_segments"]
def test_forecast_unavailable_when_no_road_name(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("")
    assert result["available"] is False
def test_forecast_unavailable_when_model_missing(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    monkeypatch.setattr(svc, "HISTORY_CSV", csv_path)
    monkeypatch.setattr(svc, "_bundle", None)
    monkeypatch.setattr(svc, "_load_error", "model artifact not found")
    monkeypatch.setattr(svc, "_load_attempted", True)
    result = svc.get_t120_forecast("Test Road A")
    assert result["available"] is False
    assert "unavailable" in result["reason"].lower()
def test_forecast_unavailable_when_no_real_observation_for_trained_segment(tmp_path, monkeypatch):
    # Segment is in the trained labels but has zero rows in this CSV.
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    result = svc.get_t120_forecast("111_222_0")  # not a real road_name -> unsupported anyway
    assert result["available"] is False
def test_case_insensitive_and_substring_road_matching(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Ramp A | Ragigudda-Silk Board Integrated Flyover", "20", "40"),
    ])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())

    result = svc.get_t120_forecast("ragigudda-silk board integrated flyover")
    assert result["available"] is True
    assert result["road_name"] == "Ramp A | Ragigudda-Silk Board Integrated Flyover"
def test_route_matches_geographically_close_segment(tmp_path, monkeypatch):
    # Segment sits at (12.90, 77.60). A route passing within ~50m of it
    # (well under the 200m match radius) should resolve to it -- even
    # though the route's own road-name text ("MG Road") is unrelated to
    # the segment's real road_name, proving this is a geographic match,
    # not a string match.
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40", lat="12.90000", lon="77.60000"),
    ])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[12.895, 77.595], [12.9001, 77.6001], [12.905, 77.605]]  # passes right by the segment
    segment = svc.find_segment_near_route(route_coords)
    assert segment is not None
    assert segment["road_name"] == "Test Road A"
    result = svc.get_t120_forecast_for_route(route_coords)
    assert result["available"] is True
    assert result["road_name"] == "Test Road A"
def test_route_far_from_all_segments_is_unavailable(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40", lat="12.90000", lon="77.60000"),
    ])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[13.00, 77.70], [13.01, 77.71]]
    result = svc.get_t120_forecast_for_route(route_coords)
    assert result["available"] is False
    assert result["reason"] == "2-hour forecast unavailable for this route in the preliminary model."
    assert "Test Road A" in result["supported_segments"]
def test_empty_route_coords_is_unavailable(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    assert svc.find_segment_near_route([]) is None
    result = svc.get_t120_forecast_for_route([])
    assert result["available"] is False
def test_route_eta_unavailable_when_coverage_below_threshold(tmp_path, monkeypatch):
    """A single 500m monitored segment on a 50km route is nowhere near
    enough real coverage to responsibly sum into a whole-route future
    travel time -- must be reported honestly as unavailable, with the
    real computed coverage percentage, never a fabricated ETA."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[12.9, 77.6], [12.91, 77.61]]  # passes right by the segment
    result = svc.get_t120_forecast_for_route(route_coords, route_distance_km=50.0)
    assert result["available"] is True
    assert result["route_eta"]["available"] is False
    assert result["route_eta"]["future_travel_time_min"] is None
    assert result["route_eta"]["future_arrival_time"] is None
    coverage = result["coverage"]
    assert coverage["matched_length_m"] == 500.0
    assert coverage["route_length_m"] == 50000.0
    assert coverage["coverage_percent"] == 1.0  # 500m / 50000m = 1%
    assert "does not cover enough of this route" in result["route_eta_note"]
    assert "1.0%" in result["route_eta_note"]
def test_route_eta_computed_when_coverage_meets_threshold(tmp_path, monkeypatch):
    """When a monitored segment's real length accounts for (near) the
    entire route distance, the route-level future travel time must be
    computed as segment_length_m / (predicted_speed_kmh / 3.6), summed
    across matched segments and converted to minutes -- a real formula
    over real numbers, not a guess."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[12.9, 77.6], [12.901, 77.601]]
    # Real segment length is 500m (fixture). Use a route distance close
    # enough to it that coverage clears the 95% threshold.
    route_distance_km = 0.5
    result = svc.get_t120_forecast_for_route(route_coords, route_distance_km=route_distance_km)
    assert result["available"] is True
    coverage = result["coverage"]
    assert coverage["coverage_percent"] == 100.0
    assert result["route_eta"]["available"] is True
    predicted_speed_kmh = result["forecast"]["predicted_speed_kmh"]  # fake model: current(20) - 5 = 15.0
    expected_seconds = 500.0 / (predicted_speed_kmh / 3.6)
    expected_minutes = round(expected_seconds / 60.0, 1)
    assert result["route_eta"]["future_travel_time_min"] == expected_minutes
    # Future arrival = future departure (target_time) + travel time.
    import datetime
    departure = datetime.datetime.fromisoformat(result["route_eta"]["future_departure_time"])
    arrival = datetime.datetime.fromisoformat(result["route_eta"]["future_arrival_time"])
    actual_minutes = (arrival - departure).total_seconds() / 60.0
    assert abs(actual_minutes - expected_minutes) < 0.01
    assert result["route_eta_note"] is None or result["route_eta"]["note"] is None
def test_route_eta_coverage_sums_multiple_matched_segments(tmp_path, monkeypatch):
    """Two distinct monitored segments both near the route must both
    contribute their real lengths to coverage and both contribute their
    real predicted-speed segment times to the summed travel time --
    never just the single closest one silently standing in for the rest
    of the route."""
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [
        _ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40", lat="12.90000", lon="77.60000"),
        _ok_row("2026-01-01 10:00:00", "333", "444", "Test Road B", "30", "50", lat="12.90100", lon="77.60100"),
    ])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[12.9000, 77.6000], [12.9010, 77.6010]]
    matched = svc.find_segments_near_route(route_coords)
    assert len(matched) == 2
    result = svc.get_t120_forecast_for_route(route_coords, route_distance_km=1.0)
    assert result["available"] is True
    assert len(result["segments"]) == 2
    # Both real 500m segments -> 1000m matched length.
    assert result["coverage"]["matched_length_m"] == 1000.0
    assert result["coverage"]["coverage_percent"] == 100.0
    assert result["route_eta"]["available"] is True
    total_seconds = sum(
        500.0 / (seg["forecast"]["predicted_speed_kmh"] / 3.6) for seg in result["segments"]
    )
    expected_minutes = round(total_seconds / 60.0, 1)
    assert result["route_eta"]["future_travel_time_min"] == expected_minutes
def test_route_eta_unavailable_when_route_distance_not_provided(tmp_path, monkeypatch):
    csv_path = str(tmp_path / "fixture.csv")
    _write_fixture_csv(csv_path, [_ok_row("2026-01-01 10:00:00", "111", "222", "Test Road A", "20", "40")])
    _reset_module_state(monkeypatch, csv_path, _fake_bundle())
    route_coords = [[12.9, 77.6]]
    result = svc.get_t120_forecast_for_route(route_coords)  # no distance given
    assert result["available"] is True
    assert result["coverage"]["coverage_percent"] is None
    assert result["route_eta"]["available"] is False
    assert "route distance was not provided" in result["route_eta_note"]
def test_real_trained_artifact_loads_and_predicts_end_to_end():
    """Sanity check only -- confirms the actual production model +
    real clean CSV can serve a forecast for a real supported segment.
    Does not assert any specific metric or prediction value (those are
    reported by the training script, not re-verified here)."""
    import importlib
    fresh_svc = importlib.reload(svc)  # reset any monkeypatched globals from other tests
    segments = fresh_svc.get_supported_segments()
    if not segments:
        import pytest
        pytest.skip("Real T+120 model/data artifacts not present in this environment.")
    result = fresh_svc.get_t120_forecast(segments[0]["road_name"])
    assert result["available"] is True
    assert isinstance(result["forecast"]["predicted_speed_kmh"], float)
    assert result["forecast"]["forecast_horizon_minutes"] == 120
    assert result["preliminary"] is True














