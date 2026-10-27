"""
Preliminary T+120 (2-hour-ahead) traffic forecast service.

Serves predictions from the ALREADY-TRAINED preliminary RandomForest
model (see train_t120_preliminary_model.py, models/t120_preliminary_rf_model.joblib,
models/t120_preliminary_metrics.json). This module:

  - Never retrains or modifies the model.
  - Never forecasts for any road other than the exact 8 real OSM
    segments the model was trained on.
  - Never fabricates, interpolates, or substitutes stale/other-segment
    data when a real observation isn't available.
  - Reuses the project's EXISTING traffic-condition thresholds
    (see app.py: classify_status_from_delay_percentage) for both the
    "now" and "after 2 hours" condition labels -- no new thresholds are
    invented for the forecast.

This is completely separate from, and does not modify, the existing
current-state GNN prediction (real_gnn_service.py) or the existing
hybrid 2-hour route forecast (traffic_forecast_service.py /
/api/traffic/forecast-2h), which stay untouched.
"""
from __future__ import annotations

import csv
import json
import math
import os
import threading
from datetime import datetime, timedelta

import joblib

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "t120_preliminary_rf_model.joblib")
METRICS_PATH = os.path.join(HERE, "models", "t120_preliminary_metrics.json")
HISTORY_CSV = os.path.join(HERE, "data", "forecast_segments_history_clean.csv")

# Same match radius the existing real GNN route-matching already uses
# (real_gnn_service.py: MATCH_RADIUS_M) -- reused for consistency rather
# than inventing a new distance threshold for this second matcher.
MATCH_RADIUS_M = 200.0

_metrics_lock = threading.Lock()
_metrics_cache = None  # the parsed models/t120_preliminary_metrics.json, or {} if missing
_metrics_load_attempted = False


def _load_metrics() -> dict:
    """Reads the training script's real, saved evaluation report -- never
    recomputed, adjusted, or fabricated here. This is the ONE place model
    metadata (pair counts, segment counts, test metrics, baseline
    comparison) is read from, so retraining the pipeline and overwriting
    this JSON is enough to update everything the API/UI show -- no
    frontend or hardcoded-constant changes needed."""
    global _metrics_cache, _metrics_load_attempted
    if _metrics_load_attempted:
        return _metrics_cache
    with _metrics_lock:
        if _metrics_load_attempted:
            return _metrics_cache
        _metrics_load_attempted = True
        try:
            with open(METRICS_PATH, encoding="utf-8") as f:
                _metrics_cache = json.load(f)
        except Exception:
            _metrics_cache = {}
    return _metrics_cache


READINESS_REPORT_PATH = os.path.join(HERE, "data", "forecast_segments_data_readiness_report.json")
_readiness_cache = None
_readiness_load_attempted = False


def _load_readiness_report() -> dict:
    """The dataset builder's own real readiness report -- the authoritative
    record of the real observation window the training data actually
    spans (time_span_start/time_span_end), never recomputed here."""
    global _readiness_cache, _readiness_load_attempted
    if _readiness_load_attempted:
        return _readiness_cache
    _readiness_load_attempted = True
    try:
        with open(READINESS_REPORT_PATH, encoding="utf-8") as f:
            _readiness_cache = json.load(f)
    except Exception:
        _readiness_cache = {}
    return _readiness_cache


def _training_pairs_count() -> int | None:
    return _load_metrics().get("total_genuine_pairs")


def _training_hours_label() -> str:
    """Real training-data time span, read from the dataset builder's own
    readiness report (time_span_start -> time_span_end) -- not a
    hardcoded constant, so retraining on a longer collection window
    updates this automatically. Falls back to 'unknown' rather than
    guessing if the report is missing."""
    report = _load_readiness_report()
    start, end = report.get("time_span_start"), report.get("time_span_end")
    if not start or not end:
        return "unknown"
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
        hours = (end_dt - start_dt).total_seconds() / 3600.0
        return f"~{hours:.1f}"
    except Exception:
        return "unknown"


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))

_lock = threading.Lock()
_bundle = None  # {"model", "feature_columns", "segment_labels"} once loaded
_load_error = None
_load_attempted = False


def _load_bundle():
    global _bundle, _load_error, _load_attempted
    if _load_attempted:
        return
    with _lock:
        if _load_attempted:
            return
        _load_attempted = True
        try:
            _bundle = joblib.load(MODEL_PATH)
        except Exception as exc:  # model missing/corrupt -- honest failure, no fallback
            _load_error = str(exc)


def _segment_key(osm_u, osm_v, osm_key) -> str:
    return f"{osm_u}_{osm_v}_{osm_key}"


def _read_history_rows():
    if not os.path.exists(HISTORY_CSV):
        return []
    with open(HISTORY_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_supported_segments() -> list[dict]:
    """Real metadata (road name + OSM identity) for exactly the 8
    segments the preliminary model was trained on, resolved from the
    latest real OK-status observation of each in the clean CSV. Returns
    an empty list if the model or CSV isn't available -- never invented."""
    _load_bundle()
    if _bundle is None:
        return []

    trained_keys = set(_bundle["segment_labels"])
    latest_by_segment: dict[str, dict] = {}
    for row in _read_history_rows():
        if row.get("status") != "OK":
            continue
        key = _segment_key(row["osm_u"], row["osm_v"], row["osm_key"])
        if key not in trained_keys:
            continue
        existing = latest_by_segment.get(key)
        if existing is None or row["timestamp"] > existing["timestamp"]:
            latest_by_segment[key] = row

    segments = []
    for key in _bundle["segment_labels"]:
        row = latest_by_segment.get(key)
        if row is None:
            continue
        segments.append({
            "segment_key": key,
            "road_name": row["road_name"],
            "osm_u": row["osm_u"],
            "osm_v": row["osm_v"],
            "osm_key": row["osm_key"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            # Real OSM edge length for this monitored segment -- the ONLY
            # real basis for judging how much of a route's physical
            # distance a matched segment's predicted speed actually
            # represents. Never estimated/guessed.
            "edge_length_m": float(row["edge_length_m"]) if row.get("edge_length_m") not in (None, "") else 0.0,
        })
    return segments


def find_segments_near_route(route_coords: list) -> list[dict]:
    """Geographic match (same 200m radius the existing real GNN uses to
    match a route against its own monitored edges) between a route's real
    geometry and ALL of the 8 segments this preliminary model was trained
    on that the route passes near (not just the single closest one) --
    needed to honestly assess how much of the route's physical distance
    is actually covered by real monitored segments.

    This is deliberately geography-based rather than road-name-string
    matching: OSM edges often have no usable `name` tag (falling back to
    a highway class like "trunk"), which would silently under-match a
    route that genuinely passes through a monitored segment. Distance is
    computed from the segments' own real sampled coordinates -- nothing
    here is fabricated or guessed.

    route_coords: list of [lat, lon] pairs (the exact geometry already
    shown on the map for this route). Returns matched segment dicts
    (each with its own closest approach distance_m), sorted nearest
    first; empty list if none are within the match radius."""
    if not route_coords:
        return []
    segments = get_supported_segments()
    if not segments:
        return []

    # Unlike the existing real-GNN route matcher (which downsamples
    # because it checks against thousands of edges), there are only 8
    # segments here -- checking every real route point against all 8 is
    # cheap and avoids missing a genuine close pass that a downsampled
    # stride could skip over.
    best_by_key: dict[str, tuple[float, dict]] = {}
    for point in route_coords:
        lat, lon = point[0], point[1]
        for seg in segments:
            d = _haversine_m(lat, lon, seg["latitude"], seg["longitude"])
            if d <= MATCH_RADIUS_M:
                key = seg["segment_key"]
                if key not in best_by_key or d < best_by_key[key][0]:
                    best_by_key[key] = (d, seg)

    matches = sorted(best_by_key.values(), key=lambda t: t[0])
    return [{**seg, "distance_from_route_m": round(dist, 1)} for dist, seg in matches]


def find_segment_near_route(route_coords: list) -> dict | None:
    """Backward-compatible single-nearest-match wrapper around
    find_segments_near_route() -- kept for direct/manual lookups that
    only need the closest match, not the full coverage picture."""
    matches = find_segments_near_route(route_coords)
    return matches[0] if matches else None


def _find_supported_segment(road_name: str) -> dict | None:
    """Case-insensitive match of `road_name` against a supported
    segment's real road_name (exact first, then substring, to tolerate
    real names like 'Ramp A | Ragigudda-Silk Board Integrated Flyover').
    Returns None if `road_name` isn't one of the 8 trained segments."""
    if not road_name:
        return None
    segments = get_supported_segments()
    query = road_name.strip().lower()

    for seg in segments:
        if seg["road_name"].strip().lower() == query:
            return seg
    for seg in segments:
        seg_name = seg["road_name"].strip().lower()
        if query in seg_name or seg_name in query:
            return seg
    return None


def _latest_ok_observation(segment_key: str) -> dict | None:
    latest = None
    for row in _read_history_rows():
        if row.get("status") != "OK":
            continue
        if _segment_key(row["osm_u"], row["osm_v"], row["osm_key"]) != segment_key:
            continue
        if latest is None or row["timestamp"] > latest["timestamp"]:
            latest = row
    return latest


def _classify_condition(delay_percent: float) -> str:
    """Identical thresholds to the existing current-prediction condition
    label (app.py: classify_status_from_delay_percentage) -- reused
    verbatim, not reinvented, so NOW and AFTER-2-HOURS labels are
    directly comparable."""
    if delay_percent < 10:
        return "NORMAL"
    if delay_percent < 25:
        return "MODERATE"
    if delay_percent < 40:
        return "HIGH"
    return "CRITICAL"


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.fromisoformat(s)


def get_t120_forecast(road_name: str) -> dict:
    """Returns the preliminary T+120 forecast for `road_name` if, and
    only if, it resolves (by name) to one of the 8 real segments the
    model was trained on AND a real OK-status observation exists for it.
    Kept for direct/manual lookups; the route-level UI uses
    get_t120_forecast_for_route() below (geographic matching), which
    doesn't depend on OSM `name` tags being present."""
    _load_bundle()
    if _load_error is not None:
        return {"available": False, "reason": f"T+120 model unavailable: {_load_error}"}
    if _bundle is None:
        return {"available": False, "reason": "T+120 model artifact not found."}

    segment = _find_supported_segment(road_name)
    if segment is None:
        return {
            "available": False,
            "reason": "2-hour forecast unavailable for this road in the preliminary model.",
            "supported_segments": [s["road_name"] for s in get_supported_segments()],
        }
    return _forecast_for_segment(segment)


# A whole-route future ETA is only trustworthy if real monitored
# segments' predicted speeds account for essentially the entire physical
# route -- otherwise summing them would silently claim to have predicted
# travel time over distance the model has no real speed for. With only 8
# short, single-point monitored segments citywide, a typical multi-km
# route will cover a tiny fraction of its length this way; this
# threshold is deliberately high (not tuned to make the current data
# "pass") so the honest answer -- "unavailable" -- is what's shown until
# genuinely dense coverage exists.
ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT = 95.0


def get_t120_forecast_for_route(route_coords: list, route_distance_km: float | None = None) -> dict:
    """Returns the preliminary T+120 forecast for whichever of the 8
    trained segments (if any) this route's real geometry actually passes
    within MATCH_RADIUS_M of, PLUS an honest assessment of whether enough
    of the route's real physical distance is covered by those segments
    to responsibly sum into a whole-route future travel time.

    Never substitutes a different segment's data, never fabricates a
    route ETA, and never changes the route's distance -- `route_distance_km`
    is used ONLY to compute what fraction of it real segments cover, not
    to derive or adjust the distance itself (that stays the caller's own
    real OSRM value, unchanged)."""
    # The displayed "Future Departure" is always the actual moment of this
    # request + 120 minutes -- a real wall-clock value, never the
    # (possibly stale) TomTom observation timestamp, and never hardcoded.
    # Every return path below carries this same value so the frontend has
    # one consistent departure/arrival basis regardless of which
    # prediction tier (or the GNN baseline fallback it computes from this
    # same field) ends up being used.
    request_time = datetime.now()
    future_departure_time = (request_time + timedelta(minutes=120)).isoformat()

    _load_bundle()
    if _load_error is not None:
        return {"available": False, "reason": f"T+120 model unavailable: {_load_error}", "future_departure_time": future_departure_time}
    if _bundle is None:
        return {"available": False, "reason": "T+120 model artifact not found.", "future_departure_time": future_departure_time}

    matched = find_segments_near_route(route_coords)
    if not matched:
        return {
            "available": False,
            "reason": "2-hour forecast unavailable for this route in the preliminary model.",
            "supported_segments": [s["road_name"] for s in get_supported_segments()],
            "future_departure_time": future_departure_time,
            "coverage": {
                "matched_length_m": 0.0,
                "route_length_m": round(route_distance_km * 1000.0, 1) if route_distance_km else None,
                "coverage_percent": 0.0 if route_distance_km else None,
                "threshold_percent": ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT,
            },
        }

    # Real per-segment model predictions for every geographically matched
    # segment that also has a real recent observation. A segment matched
    # geographically but with no observation yet is dropped, not guessed.
    valid = []
    for seg in matched:
        result = _forecast_for_segment(seg)
        if result.get("available"):
            valid.append((seg, result))

    if not valid:
        return {
            "available": False,
            "reason": "No real recent observation available yet for this segment.",
            "road_name": matched[0]["road_name"],
            "future_departure_time": future_departure_time,
            "coverage": {
                "matched_length_m": 0.0,
                "route_length_m": round(route_distance_km * 1000.0, 1) if route_distance_km else None,
                "coverage_percent": 0.0 if route_distance_km else None,
                "threshold_percent": ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT,
            },
        }

    # The segment with the most recent real observation anchors the
    # displayed "now"/"forecast" fields -- the freshest real data
    # available for this route (but NOT the displayed future departure
    # time -- see future_departure_time above).
    valid.sort(key=lambda pair: pair[1]["now"]["observation_time"], reverse=True)
    primary_segment, primary = valid[0]

    matched_length_m = sum(seg["edge_length_m"] for seg, _ in valid)
    route_length_m = route_distance_km * 1000.0 if route_distance_km else None
    coverage_percent = round(100.0 * matched_length_m / route_length_m, 1) if route_length_m else None
    route_eta_available = coverage_percent is not None and coverage_percent >= ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT

    route_eta = {
        "available": route_eta_available,
        "future_departure_time": future_departure_time,
        "forecast_horizon_minutes": 120,
        "future_travel_time_min": None,
        "future_arrival_time": None,
        "note": None,
    }
    if route_eta_available:
        # future_route_travel_time = sum(segment_length_m / (predicted_speed_kmh / 3.6))
        # -- real segment lengths and real model-predicted speeds only.
        total_seconds = 0.0
        for seg, result in valid:
            speed_kmh = result["forecast"]["predicted_speed_kmh"]
            if speed_kmh > 0:
                total_seconds += seg["edge_length_m"] / (speed_kmh / 3.6)
        future_travel_time_min = round(total_seconds / 60.0, 1)
        future_arrival_dt = request_time + timedelta(minutes=120 + future_travel_time_min)
        route_eta["future_travel_time_min"] = future_travel_time_min
        route_eta["future_arrival_time"] = future_arrival_dt.isoformat()
    else:
        if coverage_percent is None:
            route_eta["note"] = (
                "Whole-route 2-hour ETA unavailable: route distance was not provided, "
                "so real monitored-segment coverage of this route cannot be assessed."
            )
        else:
            route_eta["note"] = (
                f"Whole-route 2-hour ETA unavailable: the preliminary T+120 model does not "
                f"cover enough of this route ({coverage_percent}% of "
                f"{round(route_length_m / 1000.0, 2)} km covered by real monitored segments; "
                f"≥{ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT:.0f}% required for a whole-route estimate)."
            )

    response = dict(primary)  # road_name, segment_key, now, forecast, model, data_coverage, ...
    response["segments"] = [
        {
            "road_name": seg["road_name"],
            "segment_key": seg["segment_key"],
            "edge_length_m": seg["edge_length_m"],
            "distance_from_route_m": seg.get("distance_from_route_m"),
            "now": result["now"],
            "forecast": result["forecast"],
        }
        for seg, result in valid
    ]
    response["coverage"] = {
        "matched_length_m": round(matched_length_m, 1),
        "route_length_m": round(route_length_m, 1) if route_length_m else None,
        "coverage_percent": coverage_percent,
        "threshold_percent": ROUTE_ETA_COVERAGE_THRESHOLD_PERCENT,
    }
    response["route_eta"] = route_eta
    response["future_departure_time"] = future_departure_time
    # Backward-compatible top-level mirrors of route_eta's honesty fields.
    response["route_eta_available"] = route_eta["available"]
    response["route_eta_note"] = route_eta["note"] or "Future route ETA unavailable in the preliminary model."
    return response


def _forecast_for_segment(segment: dict) -> dict:
    obs = _latest_ok_observation(segment["segment_key"])
    if obs is None:
        return {
            "available": False,
            "reason": "No real recent observation available yet for this segment.",
            "road_name": segment["road_name"],
        }

    ts = _parse_ts(obs["timestamp"])
    feature_columns = _bundle["feature_columns"]
    segment_index = _bundle["segment_labels"].index(segment["segment_key"])

    feats = {
        "current_speed_kmh": float(obs["current_speed_kmh"]),
        "free_flow_speed_kmh": float(obs["free_flow_speed_kmh"]),
        "speed_ratio": float(obs["speed_ratio"]),
        "delay_percent": float(obs["delay_percent"]),
        "current_travel_time_sec": float(obs["current_travel_time_sec"]),
        "free_flow_travel_time_sec": float(obs["free_flow_travel_time_sec"]),
        "confidence": float(obs["confidence"]),
        "hour": ts.hour,
        "day_of_week": ts.weekday(),
        "is_weekend": 1 if ts.weekday() >= 5 else 0,
        "segment_index": segment_index,
    }
    row_vector = [[feats[c] for c in feature_columns]]

    predicted_speed = float(_bundle["model"].predict(row_vector)[0])
    free_flow = feats["free_flow_speed_kmh"]
    predicted_delay_percent = round(max(0.0, (1 - predicted_speed / free_flow)) * 100, 1) if free_flow else None

    now_condition = _classify_condition(feats["delay_percent"])
    forecast_condition = _classify_condition(predicted_delay_percent) if predicted_delay_percent is not None else None
    target_time = ts + timedelta(minutes=120)

    return {
        "available": True,
        "road_name": segment["road_name"],
        "segment_key": segment["segment_key"],
        "now": {
            "speed_kmh": feats["current_speed_kmh"],
            "condition": now_condition,
            "delay_percent": feats["delay_percent"],
            "observation_time": ts.isoformat(),
        },
        "forecast": {
            "predicted_speed_kmh": round(predicted_speed, 1),
            "condition": forecast_condition,
            "predicted_delay_percent": predicted_delay_percent,
            "forecast_horizon_minutes": 120,
            "target_time": target_time.isoformat(),
        },
        "model": _load_metrics().get("model_type", "Preliminary T+120 model (see /api/traffic/forecast-t120/model-info)"),
        "data_coverage": f"{_load_metrics().get('unique_segments', len(_bundle['segment_labels']))} monitored Bengaluru road segments",
        "training_pairs": _training_pairs_count(),
        "training_hours": _training_hours_label(),
        "disclosure": (
            f"Preliminary forecast — trained on {_training_hours_label()} hours of real data "
            f"({_training_pairs_count()} genuine T+120 pairs)"
        ),
        "preliminary": True,
        # Explicit, undeniable honesty statement (never silently omitted):
        # this model predicts a per-segment speed, not a validated
        # whole-route future travel time. A single matched segment's
        # predicted speed is NEVER extrapolated into a route ETA here.
        "route_eta_available": False,
        "route_eta_note": "Future route ETA unavailable in the preliminary model.",
    }


def get_model_metadata() -> dict:
    """Full, generic model/training metadata for the technical-details
    area of the UI -- read entirely from the training script's saved
    report (models/t120_preliminary_metrics.json), never recomputed or
    invented here. This is the ONE place the frontend needs to query to
    stay correct across a retrain: run train_t120_preliminary_model.py
    again on more collected data, overwrite the two model artifacts, and
    every number this function returns updates automatically -- no
    frontend or backend code change required.

    Returns {"available": False, "reason": ...} if the model/report isn't
    present, rather than a partially-fabricated metadata object."""
    _load_bundle()
    metrics = _load_metrics()
    if _load_error is not None:
        return {"available": False, "reason": f"T+120 model unavailable: {_load_error}"}
    if _bundle is None or not metrics:
        return {"available": False, "reason": "T+120 model artifact or metrics report not found."}

    return {
        "available": True,
        "model_type": metrics.get("model_type"),
        "trained_at": metrics.get("trained_at"),
        "data_source": metrics.get("data_source"),
        "total_genuine_pairs": metrics.get("total_genuine_pairs"),
        "unique_segments": metrics.get("unique_segments"),
        "training_data_span_hours": _training_hours_label(),
        "split": metrics.get("split"),
        "leakage_check": metrics.get("leakage_check"),
        "input_features": metrics.get("input_features"),
        "model_params": metrics.get("model_params"),
        "test_metrics": (metrics.get("metrics") or {}).get("test"),
        "validation_metrics": (metrics.get("metrics") or {}).get("validation"),
        "train_metrics": (metrics.get("metrics") or {}).get("train"),
        "persistence_baseline_test_metrics": (metrics.get("persistence_baseline_metrics") or {}).get("test"),
        "baseline_comparison": metrics.get("baseline_comparison"),
        "limitations": metrics.get("limitations"),
    }
