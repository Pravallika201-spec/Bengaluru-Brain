"""
Tests for the corrected Traffic/Alerts architecture:

  Traffic module   -> detect incident, determine route impact,
                       recommend an alternate route (never auto-applied)
  Alerts module    -> receives an already-eligible incident and displays
                       a simple citizen-facing message (existing Alerts
                       UI/flow untouched)

These tests use deterministic fixtures only -- no real network calls, no
fabricated production data.
"""
import sys
import types
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from traffic_incident_service import (
    Observation, TrafficIncidentDetector, TRAFFIC_ANOMALY, NORMAL_CONGESTION,
)
from traffic_alert_eligibility import (
    is_alert_eligible, get_all_alert_state, build_bilingual_alert_message,
    get_active_traffic_incident_alerts, _alert_state, _lock,
)
from kannada_messages import get_kannada_service


def _reset_alert_state():
    with _lock:
        _alert_state.clear()


def test_bilingual_message_matches_incident_type_never_says_accident_for_anomaly():
    msg = get_kannada_service().generate_incident_alert("TRAFFIC_ANOMALY", "Outer Ring Road")
    assert msg is not None
    assert "accident" not in msg["english"].lower()
    assert "unexpected" in msg["english"].lower()
    assert "Outer Ring Road" in msg["english"]
    assert msg["kannada"]  # real Kannada text present, not empty


def test_bilingual_message_for_possible_blockage_says_possible_not_confirmed():
    msg = get_kannada_service().generate_incident_alert("POSSIBLE_TRAFFIC_BLOCKAGE", "Hosur Road")
    assert msg is not None
    assert "possible" in msg["english"].lower()
    assert "confirmed" not in msg["english"].lower()
    assert "accident" not in msg["english"].lower()


def test_bilingual_message_for_provider_confirmed_never_fabricates_accident_word():
    """PROVIDER_CONFIRMED_INCIDENT is real confirmation of *an incident*,
    not necessarily an accident -- this project's TomTom integration has
    no live incident-type feed, so the message must stay factual
    ('confirmed traffic incident'), never invent 'accident'."""
    msg = get_kannada_service().generate_incident_alert("PROVIDER_CONFIRMED_INCIDENT", "Silk Board")
    assert msg is not None
    assert "confirmed" in msg["english"].lower()
    assert "accident" not in msg["english"].lower()


def test_bilingual_message_none_for_normal_and_heavy_congestion():
    assert get_kannada_service().generate_incident_alert("NORMAL_CONGESTION", "Any Road") is None
    assert get_kannada_service().generate_incident_alert("HEAVY_CONGESTION", "Any Road") is None
    assert build_bilingual_alert_message({"type": "NORMAL_CONGESTION", "road_name": "Any Road"}) is None


def test_build_bilingual_alert_message_uses_real_incident_fields():
    incident = {"type": "TRAFFIC_ANOMALY", "road_name": "Bellary Road", "segment_id": "1_2_0"}
    msg = build_bilingual_alert_message(incident)
    assert msg["road_name"] == "Bellary Road"
    assert msg["incident_type"] == "TRAFFIC_ANOMALY"


def test_get_active_traffic_incident_alerts_is_read_only_never_mutates_eligibility():
    """The Alerts module's read must never itself flip an incident's
    eligibility/cooldown state -- only /api/traffic/incidents (via
    is_alert_eligible) does that. Calling the read-only function twice in
    a row must not change get_all_alert_state()'s content."""
    _reset_alert_state()
    is_alert_eligible("seg_test_1", TRAFFIC_ANOMALY, 12.9, 77.6)
    state_before = get_all_alert_state()

    get_active_traffic_incident_alerts()
    get_active_traffic_incident_alerts()
    state_after = get_all_alert_state()

    assert state_before.keys() == state_after.keys()
    for key in state_before:
        assert state_before[key]["last_alert_time"] == state_after[key]["last_alert_time"]
    _reset_alert_state()


def test_get_active_traffic_incident_alerts_excludes_not_yet_eligible_segments(monkeypatch):
    """A real detector result for a segment with NO existing eligibility
    record (i.e. /api/traffic/incidents was never called for it) must not
    appear in the Alerts feed -- the Alerts module never runs detection
    or eligibility itself."""
    _reset_alert_state()

    def fake_analyze_all_segments(by_segment, thresholds=None):
        return [{
            "segment_id": "never_flagged_eligible",
            "road_name": "Untouched Road",
            "type": TRAFFIC_ANOMALY,
            "evidence_level": "HIGH",
        }]

    import traffic_alert_eligibility as tae
    monkeypatch.setattr("traffic_incident_service.analyze_all_segments", fake_analyze_all_segments)
    monkeypatch.setattr("traffic_incident_service.load_recent_observations_from_csv", lambda path: {"x": []})
    monkeypatch.setattr("os.path.exists", lambda path: True)

    alerts = tae.get_active_traffic_incident_alerts()
    assert alerts == []
    _reset_alert_state()


def test_no_fake_incidents_ever_when_history_file_missing(monkeypatch):
    import traffic_alert_eligibility as tae
    monkeypatch.setattr("os.path.exists", lambda path: False)
    assert tae.get_active_traffic_incident_alerts() == []


def test_alternate_route_recommendation_uses_real_alternative_and_computes_time_saving(monkeypatch):
    """When an incident sits on the primary route but NOT on a real OSRM
    alternative, the recommendation must use that alternative's own real
    distance/duration and a time-saving figure computed only from those
    two real numbers -- never invented."""
    from traffic_incident_service import check_route_impact

    incident_lat, incident_lon = 12.90, 77.60
    primary_geometry = [[12.90, 77.60], [12.91, 77.61]]  # passes through the incident
    alt_geometry = [[13.00, 77.70], [13.01, 77.71]]       # far from the incident

    class _FakeRoutingService:
        def get_route(self, source, destination):
            return {
                "provider": "OSRM",
                "primary_route": {"distance_km": 20.0, "duration_min": 40.0, "geometry": primary_geometry},
                "alternative_routes": [
                    {"distance_km": 22.0, "duration_min": 30.0, "geometry": alt_geometry},
                ],
            }

    fake_module = types.ModuleType("routing_service")
    fake_module.get_routing_service = lambda: _FakeRoutingService()
    monkeypatch.setitem(sys.modules, "routing_service", fake_module)

    incidents = [{
        "type": TRAFFIC_ANOMALY, "segment_id": "seg1", "road_name": "Test Road",
        "latitude": incident_lat, "longitude": incident_lon,
    }]
    result = check_route_impact("Source", "Destination", incidents)

    assert result["affected"] is True
    rec = result["alternate_route_recommendation"]
    assert rec["available"] is True
    assert rec["distance_km"] == 22.0
    assert rec["duration_min"] == 30.0
    assert rec["time_saving_min"] == 10.0  # 40 - 30, both real numbers


def test_alternate_route_recommendation_honest_when_all_alternatives_also_affected(monkeypatch):
    """If every real alternative also passes near the incident, the
    recommendation must say so honestly -- never fabricate a route that
    avoids it."""
    from traffic_incident_service import check_route_impact

    incident_lat, incident_lon = 12.90, 77.60
    shared_geometry = [[12.90, 77.60], [12.91, 77.61]]

    class _FakeRoutingService:
        def get_route(self, source, destination):
            return {
                "provider": "OSRM",
                "primary_route": {"distance_km": 20.0, "duration_min": 40.0, "geometry": shared_geometry},
                "alternative_routes": [
                    {"distance_km": 21.0, "duration_min": 38.0, "geometry": shared_geometry},
                ],
            }

    fake_module = types.ModuleType("routing_service")
    fake_module.get_routing_service = lambda: _FakeRoutingService()
    monkeypatch.setitem(sys.modules, "routing_service", fake_module)

    incidents = [{
        "type": TRAFFIC_ANOMALY, "segment_id": "seg1", "road_name": "Test Road",
        "latitude": incident_lat, "longitude": incident_lon,
    }]
    result = check_route_impact("Source", "Destination", incidents)

    assert result["affected"] is True
    rec = result["alternate_route_recommendation"]
    assert rec["available"] is False
    assert "no alternate route" in rec["reason"].lower()


def test_no_recommendation_field_populated_when_route_not_affected(monkeypatch):
    from traffic_incident_service import check_route_impact

    far_geometry = [[13.00, 77.70], [13.01, 77.71]]

    class _FakeRoutingService:
        def get_route(self, source, destination):
            return {
                "provider": "OSRM",
                "primary_route": {"distance_km": 20.0, "duration_min": 40.0, "geometry": far_geometry},
                "alternative_routes": [],
            }

    fake_module = types.ModuleType("routing_service")
    fake_module.get_routing_service = lambda: _FakeRoutingService()
    monkeypatch.setitem(sys.modules, "routing_service", fake_module)

    incidents = [{
        "type": TRAFFIC_ANOMALY, "segment_id": "seg1", "road_name": "Test Road",
        "latitude": 12.90, "longitude": 77.60,
    }]
    result = check_route_impact("Source", "Destination", incidents)
    assert result["affected"] is False
    assert result["alternate_route_recommendation"] is None


def test_detector_still_classifies_normal_congestion_correctly():
    """Sanity check that the existing detector itself was not touched by
    this integration work."""
    from datetime import datetime, timedelta
    detector = TrafficIncidentDetector()
    now = datetime.now()
    obs = [
        Observation(timestamp=now - timedelta(minutes=i * 5), current_speed_kmh=38.0, free_flow_speed_kmh=40.0)
        for i in range(5, 0, -1)
    ]
    result = detector.analyze_segment("seg_normal", obs)
    assert result["type"] == NORMAL_CONGESTION
