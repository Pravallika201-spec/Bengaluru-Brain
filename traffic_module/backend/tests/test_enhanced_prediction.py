import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import predict_traffic, classify_status_from_delay_percentage, validate_prediction


def test_predict_traffic_returns_enhanced_metrics():
    result = predict_traffic("electronic city", "whitefield")

    assert "weather" in result
    assert "event" in result
    assert "traffic" in result
    assert "confidence" in result
    assert "route_type" in result
    assert "factors" in result
    assert "traffic_source" in result
    assert "route_coords" in result
    assert result["traffic_source"] in {"LIVE", "MODEL/HISTORICAL", "OSM/HEURISTIC"}
    assert 0 <= result["confidence"] <= 1
    assert result["distance_km"] >= 0
    assert result["travel_time"] >= result["base_duration_mins"]
    if result["traffic_points"]:
        assert len(result["traffic_points"]) >= 1
        speeds = [p.get("current_speed_kmh", 0) for p in result["traffic_points"]]
        assert any(speed != speeds[0] for speed in speeds[1:]) or speeds[0] != 40


def test_status_is_derived_from_delay_percentage():
    assert classify_status_from_delay_percentage(5) == "NORMAL"
    assert classify_status_from_delay_percentage(20) == "MODERATE"
    assert classify_status_from_delay_percentage(30) == "HIGH"
    assert classify_status_from_delay_percentage(45) == "CRITICAL"


def test_validation_rejects_inconsistent_predictions():
    invalid = {
        "predicted_speed_kmh": 120,
        "base_duration_mins": 20,
        "predicted_duration_mins": 15,
        "delay_percentage": 5,
    }
    assert validate_prediction(invalid) is False
