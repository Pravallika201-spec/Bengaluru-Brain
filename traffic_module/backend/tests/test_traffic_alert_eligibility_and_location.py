"""
Tests for user_location_service.py and traffic_alert_eligibility.py —
location-based alert eligibility, incident-to-user matching, and
cooldown/duplicate-alert prevention. No fake users/GPS presented as
real — these are synthetic test coordinates exercising real logic.
"""
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_location_service as uls
import traffic_alert_eligibility as tae
from traffic_incident_service import TRAFFIC_ANOMALY, POSSIBLE_TRAFFIC_BLOCKAGE, NORMAL_CONGESTION


def setup_function(_):
    # Each test gets a clean in-memory registry/state — these modules are
    # process-global singletons by design (ephemeral, no persistence).
    uls._locations.clear()
    tae._alert_state.clear()


# ---------------------------------------------------------------------
# User location registration (Part 5)
# ---------------------------------------------------------------------

def test_update_location_stores_and_returns_it():
    loc = uls.update_location("session-1", 12.97, 77.59)
    assert loc.session_id == "session-1"
    assert loc.latitude == 12.97


def test_update_location_rejects_implausible_coordinates():
    try:
        uls.update_location("session-1", 999.0, 77.59)
        assert False, "should have raised"
    except ValueError:
        pass


def test_get_active_users_excludes_stale_sessions():
    uls.update_location("fresh", 12.97, 77.59)
    stale = uls.UserLocation("stale", 12.90, 77.50, datetime.now() - timedelta(seconds=uls.LOCATION_TTL_SECONDS + 60))
    uls._locations["stale"] = stale

    active = uls.get_active_users()
    ids = {u.session_id for u in active}
    assert "fresh" in ids
    assert "stale" not in ids


def test_remove_location_immediately_deregisters():
    uls.update_location("session-1", 12.97, 77.59)
    uls.remove_location("session-1")
    assert uls.get_user_location("session-1") is None


def test_no_permanent_tracking_in_memory_only():
    """This is a design assertion, not a behavior test: confirms the
    module has no disk-persistence function to accidentally call."""
    assert not hasattr(uls, "save_to_disk")
    assert not hasattr(uls, "_persist")


# ---------------------------------------------------------------------
# Incident -> user matching (Part 6) — nearest AFFECTED SEGMENT, not
# an arbitrary incident center
# ---------------------------------------------------------------------

def test_user_within_radius_of_affected_segment_is_matched():
    user = uls.update_location("near-user", 12.9716, 77.5946)
    affected = [{"segment_id": "seg1", "latitude": 12.9720, "longitude": 77.5950}]  # ~50m away
    matches = tae.match_users_to_incident(affected, [user], max_radius_km=2.0)
    assert len(matches) == 1
    assert matches[0]["session_id"] == "near-user"
    assert matches[0]["matched_segment_id"] == "seg1"


def test_user_outside_radius_is_not_matched():
    user = uls.update_location("far-user", 13.5000, 78.5000)  # far from Bengaluru center
    affected = [{"segment_id": "seg1", "latitude": 12.9716, "longitude": 77.5946}]
    matches = tae.match_users_to_incident(affected, [user], max_radius_km=2.0)
    assert matches == []


def test_matches_nearest_of_multiple_affected_segments_not_arbitrary_center():
    user = uls.update_location("u1", 12.90, 77.60)
    affected = [
        {"segment_id": "far_seg", "latitude": 13.50, "longitude": 78.50},
        {"segment_id": "near_seg", "latitude": 12.901, "longitude": 77.601},
    ]
    matches = tae.match_users_to_incident(affected, [user], max_radius_km=5.0)
    assert len(matches) == 1
    assert matches[0]["matched_segment_id"] == "near_seg"


def test_no_affected_locations_never_invents_a_match():
    user = uls.update_location("u1", 12.90, 77.60)
    matches = tae.match_users_to_incident([{"segment_id": "seg1", "latitude": None, "longitude": None}], [user])
    assert matches == []


def test_matching_never_returns_other_users_raw_coordinates():
    user = uls.update_location("u1", 12.9716, 77.5946)
    affected = [{"segment_id": "seg1", "latitude": 12.9720, "longitude": 77.5950}]
    matches = tae.match_users_to_incident(affected, [user])
    assert "latitude" not in matches[0]
    assert "longitude" not in matches[0]


# ---------------------------------------------------------------------
# Alert eligibility / cooldown / duplicate prevention (Part 8/9)
# ---------------------------------------------------------------------

def test_first_detection_is_eligible():
    eligible, reason = tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6)
    assert eligible is True
    assert "first detection" in reason


def test_repeat_same_severity_within_cooldown_is_suppressed():
    tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6)
    eligible, reason = tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6, cooldown_seconds=3600)
    assert eligible is False
    assert "cooldown" in reason.lower()


def test_severity_increase_bypasses_cooldown():
    tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6)
    eligible, reason = tae.is_alert_eligible("seg1", POSSIBLE_TRAFFIC_BLOCKAGE, 12.9, 77.6, cooldown_seconds=3600)
    assert eligible is True
    assert "severity" in reason.lower()


def test_significant_location_change_bypasses_cooldown():
    tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.90, 77.60)
    eligible, reason = tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 13.50, 78.50, cooldown_seconds=3600, location_change_km=1.0)
    assert eligible is True
    assert "location" in reason.lower()


def test_cooldown_expiry_allows_realert():
    tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6, cooldown_seconds=0)
    time.sleep(0.01)
    eligible, reason = tae.is_alert_eligible("seg1", TRAFFIC_ANOMALY, 12.9, 77.6, cooldown_seconds=0)
    assert eligible is True
    assert "cooldown expired" in reason


def test_normal_congestion_never_eligible_for_alert():
    eligible, reason = tae.is_alert_eligible("seg1", NORMAL_CONGESTION, 12.9, 77.6)
    assert eligible is False


def test_build_alert_message_never_says_accident_unless_confirmed():
    from traffic_incident_service import PROVIDER_CONFIRMED_INCIDENT
    blockage_msg = tae.build_alert_message({"type": POSSIBLE_TRAFFIC_BLOCKAGE, "road_name": "Outer Ring Road", "segment_id": "s1"})
    assert "blockage" in blockage_msg.lower()
    assert "accident" not in blockage_msg.lower()

    confirmed_msg = tae.build_alert_message({"type": PROVIDER_CONFIRMED_INCIDENT, "road_name": "Outer Ring Road", "segment_id": "s1"})
    assert "confirmed" in confirmed_msg.lower()


# ---------------------------------------------------------------------
# Bilingual (English + Kannada) alert messages -- state-specific wording,
# never a generic/overclaiming string, using the project's existing
# kannada_messages.py architecture.
# ---------------------------------------------------------------------

def test_bilingual_message_matches_detector_state_for_anomaly():
    msg = tae.build_bilingual_alert_message({"type": TRAFFIC_ANOMALY, "road_name": "Outer Ring Road", "segment_id": "s1"})
    assert msg is not None
    assert "Outer Ring Road" in msg["english"]
    assert "unexpected" in msg["english"].lower()
    assert "accident" not in msg["english"].lower()
    assert "blockage" not in msg["english"].lower()
    # Real Kannada text, not an empty/placeholder string.
    assert len(msg["kannada"]) > 10
    assert msg["incident_type"] == TRAFFIC_ANOMALY


def test_bilingual_message_for_possible_blockage_says_possible_not_confirmed():
    msg = tae.build_bilingual_alert_message({"type": POSSIBLE_TRAFFIC_BLOCKAGE, "road_name": "Hosur Road", "segment_id": "s2"})
    assert msg is not None
    assert "possible" in msg["english"].lower()
    assert "blockage" in msg["english"].lower()
    assert "confirmed" not in msg["english"].lower()
    assert "accident" not in msg["english"].lower()


def test_bilingual_message_for_provider_confirmed_says_confirmed():
    from traffic_incident_service import PROVIDER_CONFIRMED_INCIDENT
    msg = tae.build_bilingual_alert_message({"type": PROVIDER_CONFIRMED_INCIDENT, "road_name": "Bellary Road", "segment_id": "s3"})
    assert msg is not None
    assert "confirmed" in msg["english"].lower()


def test_bilingual_message_none_for_normal_and_heavy_congestion():
    from traffic_incident_service import HEAVY_CONGESTION
    assert tae.build_bilingual_alert_message({"type": NORMAL_CONGESTION, "road_name": "X", "segment_id": "s"}) is None
    assert tae.build_bilingual_alert_message({"type": HEAVY_CONGESTION, "road_name": "X", "segment_id": "s"}) is None


def test_bilingual_message_falls_back_when_road_name_missing():
    msg = tae.build_bilingual_alert_message({"type": TRAFFIC_ANOMALY, "road_name": None, "segment_id": "s1"})
    assert msg is not None
    assert "this road" in msg["english"].lower()
