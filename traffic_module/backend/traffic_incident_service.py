"""
Traffic Incident Service — real-time UNEXPECTED traffic / blockage
detection, separate from:
  - incident_service.py (the EXISTING manually-added/simulated incident
    tracker behind /api/incident/add|list|remove|clear — untouched)
  - the T+120 forecasting pipeline (forecasting/ package) — this module
    reads one read-only utility from it (the real historical hour-of-day
    pattern) purely as an input to the BASELINE below; nothing about the
    forecast feature itself is touched or extended here.

CORE PRINCIPLE: "low speed" alone never means "incident". Bengaluru has
real, expected peak-hour congestion — Outer Ring Road at 15 km/h at 6pm
is NORMAL_CONGESTION, not an anomaly. What matters is a road's speed
relative to what is EXPECTED for that specific road at that specific
time — see _baseline_speed() below.

CLASSIFICATION HIERARCHY (never "accident" anywhere in this vocabulary):

    NORMAL_CONGESTION     — slow, but consistent with the road/hour baseline
      -> HEAVY_CONGESTION  — worse than expected, not yet anomaly-level evidence
      -> TRAFFIC_ANOMALY   — a real, significant deviation from baseline
      -> POSSIBLE_TRAFFIC_BLOCKAGE
                            — severe deviation that PERSISTS across multiple
                              real observations, optionally strengthened by
                              real nearby-segment corroboration
      -> PROVIDER_CONFIRMED_INCIDENT
                            — only ever set when an external incident-feed
                              explicitly confirms it. This project's TomTom
                              integration (tomtom_traffic_service.py) has no
                              incidents endpoint wired up, so this tier is
                              dormant by construction — disclosed in every
                              response, never hidden.

BASELINE (road-specific, time-aware, never a single global number) —
see _baseline_speed():
  1. Real recent same-segment observation history (best — most specific)
     when >=2 prior real readings exist for this exact segment.
  2. Otherwise: this exact segment's own real TomTom free-flow speed x
     the REAL citywide hour-of-day speed_ratio pattern for the CURRENT
     observation's hour (forecasting/historical_pattern.py — derived
     from actual collected TomTom observations, >=10 real samples
     required for that hour or this tier is skipped). This is what makes
     "15 km/h at peak on ORR = normal" vs "40 -> 8 km/h at 11am =
     anomaly" possible: free-flow speed is real and road-specific; the
     ratio is real and time-aware.
  3. Otherwise: the segment's free-flow speed alone (no time adjustment
     possible) — a weaker baseline, and reported as such.
  4. If none of the above exist: baseline is None — the detector reports
     NORMAL_CONGESTION (the safe, non-alarming default) with an explicit
     "baseline unavailable" note. It never guesses an incident from
     nothing to compare against.

NEARBY-ROAD CHECK (Step 5) — see find_nearby_segments(): real road-graph
adjacency (shares an OSM node with the target segment) first; real
geographic proximity (haversine distance between the segments' own real
sampled coordinates, within NEARBY_DISTANCE_KM) as a fallback. Never an
invented coordinate or a fabricated "nearby" relationship.

EVIDENCE / CONFIDENCE (Step 8): no numeric confidence is fabricated or
derived by a direct percent-to-confidence conversion. Every result
carries a qualitative `evidence_level` (LOW/MEDIUM/HIGH) computed from a
transparent, documented point count of the actual evidence present
(severity, persistence, corroboration) — see _evidence_level().
"""
from __future__ import annotations

import logging
import math
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("traffic_incident_service")

# Data-mode labels for Part 11 — never presented as more "live" than it
# genuinely is.
LIVE_TOMTOM = "LIVE_TOMTOM"
HISTORICAL_TOMTOM = "HISTORICAL_TOMTOM"
NO_LIVE_DATA = "NO_LIVE_DATA"

LIVE_FRESHNESS_SECONDS = 900  # a real observation this recent counts as "live", not just historical


def get_data_mode(tomtom_configured: bool, latest_observation_age_seconds: Optional[float]) -> str:
    """Honest classification of what the detector is actually running on
    right now — never LIVE_TOMTOM unless TOMTOM_API_KEY is configured AND
    the newest real observation is genuinely recent."""
    if not tomtom_configured:
        return NO_LIVE_DATA if latest_observation_age_seconds is None else HISTORICAL_TOMTOM
    if latest_observation_age_seconds is not None and latest_observation_age_seconds <= LIVE_FRESHNESS_SECONDS:
        return LIVE_TOMTOM
    return HISTORICAL_TOMTOM if latest_observation_age_seconds is not None else NO_LIVE_DATA


# ---------------------------------------------------------------------
# States
# ---------------------------------------------------------------------

NORMAL_CONGESTION = "NORMAL_CONGESTION"
HEAVY_CONGESTION = "HEAVY_CONGESTION"
TRAFFIC_ANOMALY = "TRAFFIC_ANOMALY"
POSSIBLE_TRAFFIC_BLOCKAGE = "POSSIBLE_TRAFFIC_BLOCKAGE"
PROVIDER_CONFIRMED_INCIDENT = "PROVIDER_CONFIRMED_INCIDENT"

_ESCALATED_STATES = (TRAFFIC_ANOMALY, POSSIBLE_TRAFFIC_BLOCKAGE, PROVIDER_CONFIRMED_INCIDENT)


# ---------------------------------------------------------------------
# Configuration — every threshold lives here, nothing scattered in logic
# ---------------------------------------------------------------------

@dataclass
class IncidentThresholds:
    # Below this % deviation from baseline: NORMAL_CONGESTION.
    heavy_congestion_deviation_pct: float = 35.0
    # At/above this %: enough of a deviation to be "anomaly-level" evidence.
    anomaly_deviation_pct: float = 55.0
    # At/above this %: severe enough, on its own, to matter for escalation.
    severe_deviation_pct: float = 70.0
    # A real delay (current vs free-flow travel time) above this % also
    # counts as anomaly-level evidence, independent of the speed check.
    anomaly_delay_pct: float = 50.0
    # How many of the most recent consecutive observations must ALL be at
    # anomaly-level before calling it "persistent" rather than a single
    # noisy reading. The example in the spec (40->10->8->7, 3 bad
    # readings) is exactly this window size.
    min_persistent_observations: int = 3
    # Minimum number of corroborating nearby segments (also anomalous)
    # to count as real supporting evidence.
    min_corroborating_neighbors: int = 1
    # Real geographic proximity radius used as the nearby-road fallback
    # when no direct OSM node adjacency exists between two monitored
    # segments (see find_nearby_segments()).
    nearby_distance_km: float = 3.0


DEFAULT_THRESHOLDS = IncidentThresholds()


# ---------------------------------------------------------------------
# Observation — one real reading of one real segment
# ---------------------------------------------------------------------

@dataclass
class Observation:
    timestamp: datetime
    current_speed_kmh: Optional[float]
    free_flow_speed_kmh: Optional[float] = None
    current_travel_time_sec: Optional[float] = None
    free_flow_travel_time_sec: Optional[float] = None
    road_closure: Optional[bool] = None
    # Real, optional metadata carried straight from the CSV/live response
    # — used for the API shape, map exposure, and nearby-road lookup.
    # Never invented when absent.
    road_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    osm_u: Optional[int] = None
    osm_v: Optional[int] = None
    osm_key: Optional[int] = None


def _pct_drop(current: float, baseline: float) -> Optional[float]:
    if baseline is None or baseline <= 0 or current is None:
        return None
    return round(max(0.0, (baseline - current) / baseline * 100.0), 1)


def _pct_increase(current: float, baseline: float) -> Optional[float]:
    if baseline is None or baseline <= 0 or current is None:
        return None
    return round(max(0.0, (current - baseline) / baseline * 100.0), 1)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------
# Nearby-road adjacency — real graph nodes first, real distance fallback
# ---------------------------------------------------------------------

def find_nearby_segments(
    target_key: str,
    all_observations: dict[str, list[Observation]],
    thresholds: IncidentThresholds = DEFAULT_THRESHOLDS,
) -> list[str]:
    """Returns the segment_ids of OTHER monitored segments considered
    "nearby" to target_key — first by sharing a real OSM node (genuine
    road-network adjacency), then, if none share a node, by real
    haversine distance between their own sampled coordinates (both
    already-real values from the CSV, never invented)."""

    target_obs = all_observations.get(target_key)
    if not target_obs:
        return []
    target = target_obs[-1]

    shared_node: list[str] = []
    nearby_by_distance: list[str] = []

    target_nodes = {target.osm_u, target.osm_v} - {None}

    for key, obs_list in all_observations.items():
        if key == target_key or not obs_list:
            continue
        other = obs_list[-1]

        other_nodes = {other.osm_u, other.osm_v} - {None}
        if target_nodes and other_nodes and (target_nodes & other_nodes):
            shared_node.append(key)
            continue

        if (
            target.latitude is not None and target.longitude is not None
            and other.latitude is not None and other.longitude is not None
        ):
            d = haversine_km(target.latitude, target.longitude, other.latitude, other.longitude)
            if d <= thresholds.nearby_distance_km:
                nearby_by_distance.append(key)

    return shared_node + nearby_by_distance


# ---------------------------------------------------------------------
# Evidence level — transparent point count, never a fabricated float
# ---------------------------------------------------------------------

def _evidence_level(severe: bool, anomaly: bool, persistent: bool, corroborating: int, thresholds: IncidentThresholds) -> str:
    points = 0
    if severe:
        points += 2
    elif anomaly:
        points += 1
    if persistent:
        points += 1
    points += min(corroborating, 2)

    if points <= 1:
        return "LOW"
    if points <= 3:
        return "MEDIUM"
    return "HIGH"


class TrafficIncidentDetector:

    def __init__(self, thresholds: IncidentThresholds = DEFAULT_THRESHOLDS):
        self.thresholds = thresholds

    def _baseline_speed(
        self,
        recent: list[Observation],
        latest: Observation,
        hourly_pattern: Optional[dict] = None,
    ) -> tuple[Optional[float], str]:

        # Exclude the persistence-check window (the most recent
        # min_persistent_observations readings) from the "recent history"
        # baseline — otherwise an ongoing incident contaminates its own
        # baseline (a real bug found while testing: 40->8->7->6 averaged
        # together makes 8/7/6 look almost normal against a diluted
        # ~18 km/h "baseline" instead of the real pre-incident ~40 km/h).
        pre_window = (
            recent[:-self.thresholds.min_persistent_observations]
            if len(recent) > self.thresholds.min_persistent_observations
            else recent[:-1]
        )
        history = [o.current_speed_kmh for o in pre_window if o.current_speed_kmh is not None]
        if len(history) >= 2:
            return round(sum(history) / len(history), 1), "recent_history_average"

        hour = latest.timestamp.hour if latest.timestamp else None
        if latest.free_flow_speed_kmh and hour is not None and hourly_pattern:
            bucket = hourly_pattern.get(hour % 24)
            if bucket is not None and bucket.sufficient:
                baseline = latest.free_flow_speed_kmh * bucket.avg_speed_ratio
                return round(baseline, 1), f"free_flow_x_historical_hour_pattern(hour={hour}, n={bucket.n})"

        if latest.free_flow_speed_kmh:
            return latest.free_flow_speed_kmh, "free_flow_speed_only_no_hour_pattern"

        return None, "unavailable"

    def analyze_segment(
        self,
        segment_id: str,
        recent_observations: list[Observation],
        nearby_segment_results: Optional[list[dict]] = None,
        provider_confirmed: bool = False,
        hourly_pattern: Optional[dict] = None,
    ) -> dict:

        t = self.thresholds

        def _road_name(obs_list):
            for o in reversed(obs_list):
                if o.road_name:
                    return o.road_name
            return None

        if not recent_observations:
            return {
                "type": NORMAL_CONGESTION,
                "segment_id": segment_id,
                "road_name": None,
                "evidence_level": "LOW",
                "evidence": ["no observations available"],
                "current_speed_kmh": None,
                "expected_speed_kmh": None,
                "baseline_source": None,
                "speed_drop_percent": None,
                "delay_percent": None,
                "duration_minutes": 0,
                "nearby_roads_affected": 0,
                "provider_confirmed": False,
                "timestamp": None,
                "latitude": None,
                "longitude": None,
            }

        latest = recent_observations[-1]
        baseline_speed, baseline_source = self._baseline_speed(recent_observations, latest, hourly_pattern)

        speed_drop = _pct_drop(latest.current_speed_kmh, baseline_speed) if baseline_speed is not None else None
        delay_pct = _pct_increase(latest.current_travel_time_sec, latest.free_flow_travel_time_sec)

        common = {
            "segment_id": segment_id,
            "road_name": _road_name(recent_observations),
            "current_speed_kmh": latest.current_speed_kmh,
            "expected_speed_kmh": baseline_speed,
            "baseline_source": baseline_source,
            "speed_drop_percent": speed_drop,
            "delay_percent": delay_pct,
            "provider_confirmed": False,
            "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
            "latitude": latest.latitude,
            "longitude": latest.longitude,
        }

        if baseline_speed is None:
            return {
                **common,
                "type": NORMAL_CONGESTION,
                "evidence_level": "LOW",
                "evidence": ["no baseline available for this segment/hour — cannot assess deviation, defaulting to non-alarming classification"],
                "duration_minutes": 0,
                "nearby_roads_affected": 0,
            }

        road_closed = bool(latest.road_closure)
        anomaly_level = (
            (speed_drop is not None and speed_drop >= t.anomaly_deviation_pct)
            or (delay_pct is not None and delay_pct >= t.anomaly_delay_pct)
            or road_closed
        )
        heavy_level = speed_drop is not None and speed_drop >= t.heavy_congestion_deviation_pct
        severe = speed_drop is not None and speed_drop >= t.severe_deviation_pct

        evidence: list[str] = []
        if road_closed:
            evidence.append("provider-reported road closure flag is set")
        if speed_drop is not None and speed_drop >= t.heavy_congestion_deviation_pct:
            evidence.append(f"current speed is {speed_drop}% below the expected speed ({baseline_speed} km/h, {baseline_source})")
        if delay_pct is not None and delay_pct >= t.anomaly_delay_pct:
            evidence.append(f"travel time is {delay_pct}% above free-flow travel time")

        if not anomaly_level:
            result_type = HEAVY_CONGESTION if heavy_level else NORMAL_CONGESTION
            if result_type == NORMAL_CONGESTION:
                evidence = ["current speed is consistent with the expected baseline for this road/time"]
            return {
                **common,
                "type": result_type,
                "evidence_level": "LOW",
                "evidence": evidence,
                "duration_minutes": 0,
                "nearby_roads_affected": 0,
            }

        # ---- persistence: do the last N observations ALL show anomaly-level deviation? ----
        window = recent_observations[-t.min_persistent_observations:]
        window_drops = [_pct_drop(o.current_speed_kmh, baseline_speed) for o in window]
        persistent = len(window) >= t.min_persistent_observations and all(
            d is not None and d >= t.anomaly_deviation_pct for d in window_drops
        )
        duration_minutes = 0
        if persistent and len(window) >= 2 and window[0].timestamp and window[-1].timestamp:
            duration_minutes = round((window[-1].timestamp - window[0].timestamp).total_seconds() / 60.0, 1)
        if persistent:
            evidence.append(f"abnormal slowdown has persisted across the last {t.min_persistent_observations} observations (~{duration_minutes} min)")

        # ---- nearby-road corroboration (real, caller-supplied results) ----
        corroborating = 0
        if nearby_segment_results:
            for nr in nearby_segment_results:
                if nr.get("type") in _ESCALATED_STATES:
                    corroborating += 1
        if corroborating > 0:
            evidence.append(f"{corroborating} nearby real segment(s) also show an anomaly")

        result_type = TRAFFIC_ANOMALY

        if severe and (persistent or corroborating >= t.min_corroborating_neighbors):
            result_type = POSSIBLE_TRAFFIC_BLOCKAGE
        elif persistent and corroborating >= t.min_corroborating_neighbors:
            result_type = POSSIBLE_TRAFFIC_BLOCKAGE
        elif severe:
            evidence.append(f"single reading is severe ({speed_drop}% drop) but not yet persistent or corroborated — not confirmed as a blockage")

        if corroborating == 0 and result_type == POSSIBLE_TRAFFIC_BLOCKAGE:
            evidence.append("no corroborating nearby-road evidence — reported with weaker supporting evidence")

        if provider_confirmed:
            result_type = PROVIDER_CONFIRMED_INCIDENT
            evidence.append("confirmed by an external TomTom incident feed")
        else:
            evidence.append(
                "no incident-provider feed is configured in this project — "
                "classification is based on speed/delay anomaly detection only, not a confirmed cause"
            )

        evidence_level = _evidence_level(severe, anomaly_level, persistent, corroborating, t) if not provider_confirmed else "HIGH"

        return {
            **common,
            "type": result_type,
            "evidence_level": evidence_level,
            "evidence": evidence,
            "duration_minutes": duration_minutes,
            "nearby_roads_affected": corroborating,
            "provider_confirmed": provider_confirmed,
        }

    def user_alert_message(self, result: dict) -> Optional[str]:
        """A plain-language message ONLY for the states that warrant one —
        never says 'accident' unless provider_confirmed."""
        if result["type"] == POSSIBLE_TRAFFIC_BLOCKAGE:
            road = result.get("road_name") or f"segment {result['segment_id']}"
            return f"⚠️ Possible traffic blockage detected on {road}."
        if result["type"] == PROVIDER_CONFIRMED_INCIDENT:
            road = result.get("road_name") or f"segment {result['segment_id']}"
            return f"🚨 Confirmed traffic incident on {road}."
        return None


_detector: Optional[TrafficIncidentDetector] = None


def get_incident_detector() -> TrafficIncidentDetector:
    global _detector
    if _detector is None:
        _detector = TrafficIncidentDetector()
    return _detector


def load_recent_observations_from_csv(csv_path: str, max_per_segment: int = 5) -> dict[str, list[Observation]]:
    """Reads the validated/repaired real observation log and returns the
    most recent `max_per_segment` OK observations per real OSM edge, ready
    to feed into TrafficIncidentDetector.analyze_segment(). This does NOT
    make any TomTom API call — it only reads what has already been
    collected and written to disk (respects the "no auto-polling" rule)."""

    from forecasting.csv_validator import validate_and_repair

    clean_rows, _report = validate_and_repair(csv_path)

    by_edge: dict[str, list[Observation]] = {}
    for r in clean_rows:
        if r.get("status") != "OK":
            continue
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, KeyError):
            continue

        def _f(key):
            v = r.get(key)
            try:
                return float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None

        obs = Observation(
            timestamp=ts,
            current_speed_kmh=_f("current_speed_kmh"),
            free_flow_speed_kmh=_f("free_flow_speed_kmh"),
            current_travel_time_sec=_f("current_travel_time_sec"),
            free_flow_travel_time_sec=_f("free_flow_travel_time_sec"),
            road_closure=(str(r.get("road_closure")).strip().lower() == "true"),
            road_name=r.get("osm_road_name") or None,
            latitude=_f("sample_latitude"),
            longitude=_f("sample_longitude"),
            osm_u=r.get("osm_u"),
            osm_v=r.get("osm_v"),
            osm_key=r.get("osm_key"),
        )
        segment_key = f"{r['osm_u']}_{r['osm_v']}_{r['osm_key']}"
        by_edge.setdefault(segment_key, []).append(obs)

    for key in by_edge:
        by_edge[key].sort(key=lambda o: o.timestamp)
        by_edge[key] = by_edge[key][-max_per_segment:]

    return by_edge


def latest_observation_timestamp(observations_by_segment: dict[str, list[Observation]]) -> Optional[datetime]:
    latest = None
    for obs_list in observations_by_segment.values():
        if obs_list and (latest is None or obs_list[-1].timestamp > latest):
            latest = obs_list[-1].timestamp
    return latest


_segment_state_lock = threading.Lock()
_last_segment_state: dict[str, str] = {}

_ALARM_STATES = (TRAFFIC_ANOMALY, POSSIBLE_TRAFFIC_BLOCKAGE, PROVIDER_CONFIRMED_INCIDENT)


def _log_state_transition(segment_id: str, new_state: str) -> None:
    """INCIDENT_DETECTED / INCIDENT_UPDATED / INCIDENT_RECOVERED — logged
    with segment id and states only, never a raw coordinate."""
    with _segment_state_lock:
        prev_state = _last_segment_state.get(segment_id)
        _last_segment_state[segment_id] = new_state

    was_alarm = prev_state in _ALARM_STATES
    is_alarm = new_state in _ALARM_STATES

    if is_alarm and not was_alarm:
        logger.info("INCIDENT_DETECTED segment=%s state=%s", segment_id, new_state)
    elif is_alarm and was_alarm and new_state != prev_state:
        logger.info("INCIDENT_UPDATED segment=%s from=%s to=%s", segment_id, prev_state, new_state)
    elif was_alarm and not is_alarm:
        logger.info("INCIDENT_RECOVERED segment=%s to=%s", segment_id, new_state)


def analyze_all_segments(
    observations_by_segment: dict[str, list[Observation]],
    thresholds: IncidentThresholds = DEFAULT_THRESHOLDS,
) -> list[dict]:
    """Runs the detector over every monitored segment, wiring REAL
    nearby-road corroboration (Step 5) between them via
    find_nearby_segments() — a two-pass process: first pass gets each
    segment's own reading, second pass re-checks anomalous segments with
    their real neighbors' first-pass results as corroboration."""

    from forecasting.historical_pattern import get_hourly_pattern

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bengaluru_traffic_history.csv")
    hourly_pattern = get_hourly_pattern(csv_path) if os.path.exists(csv_path) else None

    detector = TrafficIncidentDetector(thresholds)

    first_pass: dict[str, dict] = {
        key: detector.analyze_segment(key, obs, hourly_pattern=hourly_pattern)
        for key, obs in observations_by_segment.items()
    }

    final: list[dict] = []
    for key, obs in observations_by_segment.items():
        if first_pass[key]["type"] == NORMAL_CONGESTION:
            _log_state_transition(key, NORMAL_CONGESTION)
            final.append(first_pass[key])
            continue

        neighbor_keys = find_nearby_segments(key, observations_by_segment, thresholds)
        neighbor_results = [first_pass[k] for k in neighbor_keys if k in first_pass]

        result = detector.analyze_segment(key, obs, nearby_segment_results=neighbor_results, hourly_pattern=hourly_pattern)
        result["user_alert"] = detector.user_alert_message(result)
        _log_state_transition(key, result["type"])
        final.append(result)

    return final


def check_route_impact(source: str, destination: str, incidents: list[dict], proximity_km: float = 1.0) -> dict:
    """Real route geometry (existing routing_service, unmodified) checked
    against each detected incident's real coordinates — never an
    invented alternate route, never a fabricated location."""

    from routing_service import get_routing_service

    try:
        route_data = get_routing_service().get_route(source, destination)
    except Exception as e:
        return {"available": False, "reason": str(e), "affected": False, "incidents_on_route": []}

    if not route_data or not route_data.get("primary_route"):
        return {"available": False, "reason": "no route found", "affected": False, "incidents_on_route": []}

    geometry = route_data["primary_route"]["geometry"]
    affected = []

    for inc in incidents:
        if inc["type"] not in _ESCALATED_STATES:
            continue
        if inc.get("latitude") is None or inc.get("longitude") is None:
            continue
        for lat, lon in geometry:
            if haversine_km(inc["latitude"], inc["longitude"], lat, lon) <= proximity_km:
                affected.append(inc)
                break

    message = None
    if affected:
        worst = max(affected, key=lambda i: _ESCALATED_STATES.index(i["type"]) if i["type"] in _ESCALATED_STATES else 0)
        if worst["type"] == PROVIDER_CONFIRMED_INCIDENT:
            message = f"🚨 Confirmed traffic incident detected on your route ({worst.get('road_name') or worst['segment_id']})."
        elif worst["type"] == POSSIBLE_TRAFFIC_BLOCKAGE:
            message = "⚠️ Possible traffic blockage detected on your route."
        else:
            message = "⚠️ A traffic anomaly was detected on your route."

    # ---- Alternate-route RECOMMENDATION only (never auto-applied) ----
    # Real OSRM alternative routes (routing_service already requests
    # alternatives=true) checked against the SAME real incident
    # coordinates. Recommends the first alternative whose own geometry
    # doesn't pass near any affected incident, with a real time-saving
    # figure (both durations are real routing-engine estimates -- never
    # invented). This module never changes the active route itself; that
    # remains a separate, not-yet-implemented rerouting feature.
    recommendation = None
    if affected:
        primary_duration = route_data["primary_route"].get("duration_min")
        for alt in route_data.get("alternative_routes", []):
            alt_geometry = alt.get("geometry") or []
            alt_affected = any(
                haversine_km(inc["latitude"], inc["longitude"], lat, lon) <= proximity_km
                for inc in affected
                for lat, lon in alt_geometry
            )
            if not alt_affected:
                alt_duration = alt.get("duration_min")
                time_saving_min = (
                    round(primary_duration - alt_duration, 1)
                    if primary_duration is not None and alt_duration is not None
                    else None
                )
                recommendation = {
                    "available": True,
                    "distance_km": round(alt["distance_km"], 2) if alt.get("distance_km") is not None else None,
                    "duration_min": round(alt_duration, 1) if alt_duration is not None else None,
                    "time_saving_min": time_saving_min,
                }
                break
        if recommendation is None:
            recommendation = {
                "available": False,
                "reason": "No alternate route avoiding the detected incident(s) is currently available.",
            }

    return {
        "available": True,
        "affected": bool(affected),
        "message": message,
        "incidents_on_route": affected,
        "alternate_route_recommendation": recommendation,
    }
