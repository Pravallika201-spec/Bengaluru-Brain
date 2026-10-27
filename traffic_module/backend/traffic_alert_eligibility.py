"""
Alert eligibility layer for unexpected-traffic incidents — sits ON TOP OF
traffic_incident_service.py's detector output, deciding (a) whether an
already-detected incident is even worth alerting about again right now
(cooldown/dedup, mirroring the style of integration/alert_state.py — a
separate file, that existing module is untouched), and (b) which
currently-active, consenting users (user_location_service.py) are close
enough to the REAL affected road segment(s) to plausibly care.

Kept deliberately separate from:
  - the detector itself (traffic_incident_service.py) — this module only
    consumes its output, never re-implements detection logic.
  - route-based matching (traffic_incident_service.check_route_impact) —
    an on-demand check only; checking a route never auto-subscribes a
    user to alerts (see PART 7 of the task).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from traffic_incident_service import (
    haversine_km,
    NORMAL_CONGESTION,
    HEAVY_CONGESTION,
    TRAFFIC_ANOMALY,
    POSSIBLE_TRAFFIC_BLOCKAGE,
    PROVIDER_CONFIRMED_INCIDENT,
)
from user_location_service import UserLocation

logger = logging.getLogger("traffic_alert_eligibility")

# Ordinal severity rank — used only to detect "severity increased since
# last alert", never surfaced as a fabricated numeric confidence.
_SEVERITY_RANK = {
    NORMAL_CONGESTION: 0,
    HEAVY_CONGESTION: 1,
    TRAFFIC_ANOMALY: 2,
    POSSIBLE_TRAFFIC_BLOCKAGE: 3,
    PROVIDER_CONFIRMED_INCIDENT: 4,
}

COOLDOWN_SECONDS = 1800  # 30 minutes — matches this project's existing USI alert cooldown convention
LOCATION_CHANGE_KM = 1.0  # a re-detected incident whose location moved this far counts as a new alert
DEFAULT_MATCH_RADIUS_KM = 2.0

_lock = threading.Lock()
_alert_state: dict[str, "_AlertRecord"] = {}


@dataclass
class _AlertRecord:
    last_alert_time: datetime
    last_severity_rank: int
    last_latitude: Optional[float]
    last_longitude: Optional[float]


def is_alert_eligible(
    segment_id: str,
    incident_state: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    cooldown_seconds: int = COOLDOWN_SECONDS,
    location_change_km: float = LOCATION_CHANGE_KM,
) -> tuple[bool, str]:
    """Returns (eligible, reason). NORMAL_CONGESTION/HEAVY_CONGESTION are
    never alert-eligible — only TRAFFIC_ANOMALY and above reach here in
    practice, but this is defensive regardless of caller."""

    rank = _SEVERITY_RANK.get(incident_state, 0)
    if rank < _SEVERITY_RANK[TRAFFIC_ANOMALY]:
        return False, "not severe enough to alert (NORMAL_CONGESTION/HEAVY_CONGESTION never alert)"

    now = datetime.now()
    with _lock:
        prev = _alert_state.get(segment_id)

        if prev is None:
            _alert_state[segment_id] = _AlertRecord(now, rank, latitude, longitude)
            logger.info("ALERT_ELIGIBLE segment=%s reason=first_detection state=%s", segment_id, incident_state)
            return True, "first detection of this incident"

        if rank > prev.last_severity_rank:
            _alert_state[segment_id] = _AlertRecord(now, rank, latitude, longitude)
            logger.info("ALERT_ELIGIBLE segment=%s reason=severity_increased state=%s", segment_id, incident_state)
            return True, f"severity increased since last alert"

        moved = False
        if latitude is not None and longitude is not None and prev.last_latitude is not None and prev.last_longitude is not None:
            moved = haversine_km(latitude, longitude, prev.last_latitude, prev.last_longitude) >= location_change_km

        if moved:
            _alert_state[segment_id] = _AlertRecord(now, rank, latitude, longitude)
            logger.info("ALERT_ELIGIBLE segment=%s reason=location_changed", segment_id)
            return True, "incident location changed significantly"

        if (now - prev.last_alert_time) >= timedelta(seconds=cooldown_seconds):
            _alert_state[segment_id] = _AlertRecord(now, rank, latitude, longitude)
            logger.info("ALERT_ELIGIBLE segment=%s reason=cooldown_expired", segment_id)
            return True, "cooldown expired"

        logger.info("ALERT_SUPPRESSED_COOLDOWN segment=%s", segment_id)
        return False, "suppressed: within cooldown window, no severity increase or location change"


def match_users_to_incident(
    affected_locations: list[dict],
    active_users: list[UserLocation],
    max_radius_km: float = DEFAULT_MATCH_RADIUS_KM,
) -> list[dict]:
    """affected_locations: real (segment_id, latitude, longitude) dicts —
    typically the primary incident segment plus any real corroborating
    nearby segments, so a user is matched against the NEAREST actually-
    affected road segment, not an arbitrary single center point.
    Returns only users within max_radius_km — never all active users,
    never another user's raw location (only distance + which segment)."""

    valid_locations = [
        loc for loc in affected_locations
        if loc.get("latitude") is not None and loc.get("longitude") is not None
    ]
    if not valid_locations:
        return []

    eligible = []
    for user in active_users:
        best_distance = None
        best_segment = None
        for loc in valid_locations:
            d = haversine_km(user.latitude, user.longitude, loc["latitude"], loc["longitude"])
            if best_distance is None or d < best_distance:
                best_distance = d
                best_segment = loc.get("segment_id")

        if best_distance is not None and best_distance <= max_radius_km:
            eligible.append({
                "session_id": user.session_id,
                "distance_km": round(best_distance, 2),
                "matched_segment_id": best_segment,
                "reason_for_match": f"within {max_radius_km}km of the nearest affected road segment",
            })
            logger.info(
                "USER_MATCHED_TO_INCIDENT session=%s segment=%s distance_km=%.2f",
                user.session_id, best_segment, best_distance,
            )

    return eligible


def build_alert_message(incident: dict) -> Optional[str]:
    """Factual, never overclaiming — mirrors the detector's own
    user_alert_message() wording exactly, kept here too since this is
    where the final alert-worthy message is assembled with location
    context for the notification layer."""

    state = incident.get("type")
    road = incident.get("road_name") or f"segment {incident.get('segment_id')}"

    if state == PROVIDER_CONFIRMED_INCIDENT:
        return f"Traffic incident confirmed on {road}. Expect delays in this area."
    if state == POSSIBLE_TRAFFIC_BLOCKAGE:
        return f"Possible traffic blockage detected on {road}. Expect delays in this area."
    if state == TRAFFIC_ANOMALY:
        return f"A traffic anomaly was detected on {road}."
    return None


def build_bilingual_alert_message(incident: dict) -> Optional[dict]:
    """English + Kannada alert text for one detected incident, using the
    project's existing bilingual message architecture
    (kannada_messages.py) -- state-specific wording only (never a generic
    'incident'/'accident' string), returns None for NORMAL_CONGESTION/
    HEAVY_CONGESTION (mirrors build_alert_message's own rule)."""
    from kannada_messages import get_kannada_service
    return get_kannada_service().generate_incident_alert(
        incident.get("type"), incident.get("road_name")
    )


def get_active_traffic_incident_alerts() -> list[dict]:
    """Read-only view, for the EXISTING Alerts module, of traffic
    incidents the Traffic module has ALREADY determined eligible for an
    alert (via is_alert_eligible(), called from /api/traffic/incidents).

    Deliberately never calls is_alert_eligible() itself -- that function
    is stateful (cooldown/escalation tracking) and must only ever be
    driven by the Traffic module's own detection flow, exactly matching
    the required architecture:

        Traffic module:  detect -> determine eligibility -> record
        Alerts module:   read what's already been recorded -> display

    An incident only appears here once /api/traffic/incidents has
    actually run at least once since backend startup and flagged it
    eligible (get_all_alert_state() is real bookkeeping, not a fresh
    computation) -- never fabricated, never a second detector."""
    from traffic_incident_service import (
        analyze_all_segments, load_recent_observations_from_csv, _ESCALATED_STATES,
    )
    import os

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bengaluru_traffic_history.csv")
    if not os.path.exists(csv_path):
        return []

    by_segment = load_recent_observations_from_csv(csv_path)
    results = analyze_all_segments(by_segment)
    already_eligible = get_all_alert_state()  # pure read, no side effects

    alerts = []
    for r in results:
        if r["type"] not in _ESCALATED_STATES:
            continue
        record = already_eligible.get(r["segment_id"])
        if not record:
            continue  # Traffic module hasn't recorded this as alert-eligible
        message = build_bilingual_alert_message(r)
        if not message:
            continue
        alerts.append({
            "segment_id": r["segment_id"],
            "road_name": r.get("road_name") or r["segment_id"],
            "type": r["type"],
            "english": message["english"],
            "kannada": message["kannada"],
            "last_alert_time": record.get("last_alert_time"),
        })
    return alerts


def get_all_alert_state() -> dict:
    """Read-only introspection, e.g. for a debug endpoint — never returns
    user locations, only per-segment alert bookkeeping."""
    with _lock:
        return {
            seg: {
                "last_alert_time": rec.last_alert_time.isoformat(),
                "last_severity_rank": rec.last_severity_rank,
            }
            for seg, rec in _alert_state.items()
        }
