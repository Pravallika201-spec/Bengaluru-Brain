import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import predict_traffic


def test_predict_traffic_returns_enhanced_metrics():
    result = predict_traffic("electronic city", "whitefield")

    assert "weather" in result
    assert "event" in result
    assert "traffic" in result
    assert "confidence" in result
    assert "route_type" in result
    assert "factors" in result
    assert 0 <= result["confidence"] <= 1
    assert result["distance_km"] >= 0
    assert result["travel_time"] >= result["base_duration_mins"]
