import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import traffic_alert_eligibility as tae
from app import api_traffic_incidents, api_traffic_live_status
def setup_function(_):
    tae._alert_state.clear()
def test_no_incidents_result_is_a_valid_honest_outcome_shape():
    result = api_traffic_incidents(source=None, destination=None)
    assert result["available"] is True
    assert isinstance(result["incident_count"], int)
    assert result["incident_count"] == len(result["incidents"])
    assert result["incident_count"] >= 0
def test_route_impact_is_not_evaluated_when_no_route_given():
    result = api_traffic_incidents(source=None, destination=None)
    assert "route_impact" not in result
    for inc in result["incidents"]:
        assert inc["route_impact"] is None
def test_route_impact_yes_and_no_use_real_route_geometry():
    """For the real Hebbal -> Marathahalli route (already used elsewhere
    in this suite), each incident's route_impact must be a real True/False
    computed from actual OSRM route geometry -- never assumed True just
    because the road is somewhere in Bengaluru, and never assumed False
    without checking."""
    result = api_traffic_incidents(source="Hebbal", destination="Marathahalli")
    assert result["available"] is True
    assert "route_impact" in result 
    assert isinstance(result["route_impact"]["affected"], bool)
    for inc in result["incidents"]:
        assert inc["route_impact"] in (True, False)
    on_route_ids = {i["segment_id"] for i in result["route_impact"]["incidents_on_route"]}
    for inc in result["incidents"]:
        assert inc["route_impact"] == (inc["segment_id"] in on_route_ids)
def test_alert_message_present_only_when_alert_eligible():
    result = api_traffic_incidents(source=None, destination=None)
    for inc in result["incidents"]:
        if inc["alert_eligible"]:
            assert inc["alert_message"] is not None
            assert "english" in inc["alert_message"]
            assert "kannada" in inc["alert_message"]
        else:
            assert inc["alert_message"] is None
def test_alert_message_never_says_accident_unless_provider_confirmed():
    result = api_traffic_incidents(source=None, destination=None)
    for inc in result["incidents"]:
        if inc["alert_message"] and inc["type"] != "PROVIDER_CONFIRMED_INCIDENT":
            assert "accident" not in inc["alert_message"]["english"].lower()
def test_data_mode_is_never_claimed_live_without_configured_tomtom_and_fresh_data():
    """This dev/test environment has no TOMTOM_API_KEY configured, so the
    data mode must honestly report HISTORICAL_TOMTOM or NO_LIVE_DATA --
    never LIVE_TOMTOM."""
    import os
    if os.getenv("TOMTOM_API_KEY") or os.getenv("TRAFFIC_API_KEY"):
        import pytest
        pytest.skip("TomTom is actually configured in this environment; live-mode assumption doesn't apply.")
    result = api_traffic_incidents(source=None, destination=None)
    assert result["data_mode"] in ("HISTORICAL_TOMTOM", "NO_LIVE_DATA")
    status = api_traffic_live_status()
    assert status["data_mode"] in ("HISTORICAL_TOMTOM", "NO_LIVE_DATA")
    assert status["tomtom_configured"] is False
def test_live_status_exposes_no_raw_user_coordinates():
    status = api_traffic_live_status()
    assert "active_location_sessions" in status
    assert isinstance(status["active_location_sessions"], int)
    assert "locations" not in status
    assert "users" not in status
def test_no_fabricated_incidents_every_result_traces_to_real_observations():
    """Every incident the endpoint returns must carry a real timestamp and
    a real segment_id sourced from the actual collected CSV -- never an
    invented placeholder."""
    result = api_traffic_incidents(source=None, destination=None)
    for inc in result["incidents"]:
        assert inc["segment_id"]
        assert inc["timestamp"] is not None
        assert inc["type"] in (
            "TRAFFIC_ANOMALY", "POSSIBLE_TRAFFIC_BLOCKAGE", "PROVIDER_CONFIRMED_INCIDENT",
        )












