"""
2-Hour Traffic Forecast Engine.

WHAT THIS IS: a transparent hybrid extrapolation combining two genuinely
real signals — (1) the existing real GNN's/heuristic's CURRENT predicted
state for a route (real_gnn_service.py, unchanged, not retrained), and
(2) a real historical hour-of-day speed-ratio pattern derived from actual
TomTom observations (forecasting/historical_pattern.py) — to project the
current state forward by FORECAST_HORIZON_MINUTES.

WHAT THIS IS NOT: a trained supervised T+120 model. Direct T -> T+120
training pairs do not exist in the currently-collected data (see
forecasting/README.md — 0 pairs, median per-edge revisit interval
~354 minutes). No such model is claimed here, and none was fabricated.

Every response explicitly states which method tier produced it:
  - "historical_temporal_extrapolation": current state x a real
    hour-over-hour ratio derived from actual observations at both the
    current and forecast hour (>=10 real samples each, see
    historical_pattern.MIN_SAMPLES_FOR_PATTERN).
  - "persistence_estimate": historical coverage for the forecast hour is
    insufficient, so the current state is carried forward UNCHANGED and
    explicitly labeled as not a temporal forecast — this is the honest
    fallback, never disguised as the first tier.

The spatial component (which real GNN-covered edges are on this route)
always comes from real_gnn_service.py, completely unmodified. The
temporal component is citywide-aggregated (not per-segment — per-segment
history is too sparse), and that is disclosed in every response's
"limitations" list.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routing_service import get_routing_service
from real_gnn_service import get_route_traffic_signal
from weather_logic import get_live_weather, get_weather_impact, classify_weather_impact
from forecasting.historical_pattern import get_temporal_ratio, MIN_SAMPLES_FOR_PATTERN

FORECAST_HORIZON_MINUTES = 120

TRAFFIC_HISTORY_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bengaluru_traffic_history.csv")

# Same band thresholds already used by /api/predict-enhanced (traffic_level
# from slowdown_ratio) — reused for consistency, not reinvented.
_BAND_THRESHOLDS = [(0.85, "LOW"), (0.65, "MODERATE"), (0.45, "HIGH")]


def _band_from_slowdown_ratio(ratio: float) -> str:
    for threshold, label in _BAND_THRESHOLDS:
        if ratio >= threshold:
            return label
    return "SEVERE"


def _current_route_state(source: str, destination: str, now: datetime) -> dict:
    """Duplicates only the minimal real-data calls /api/predict-enhanced
    already makes (routing + real GNN + weather) — does not reimplement
    or alter any of their internal logic, and does not touch app.py."""

    routing_service = get_routing_service()
    try:
        route_data = routing_service.get_route(source, destination)
    except Exception as e:
        # get_route() raises (e.g. ValueError on an ungeocodable place)
        # rather than returning a falsy dict — caught here so an invalid
        # route honestly reports unavailable instead of crashing.
        return {"available": False, "reason": f"could not resolve route '{source}' -> '{destination}': {e}"}

    if not route_data or not route_data.get("primary_route"):
        return {"available": False, "reason": f"no route found between '{source}' and '{destination}'"}

    primary_route = route_data["primary_route"]
    distance_km = primary_route["distance_km"]
    base_time_min = primary_route.get("base_duration_min", primary_route["duration_min"])

    weather_data = get_live_weather()
    weather_multiplier = get_weather_impact()["multiplier"]
    current_time_min = primary_route["duration_min"] * weather_multiplier

    hour = now.hour
    is_weekend = now.weekday() >= 5

    try:
        signal = get_route_traffic_signal(primary_route["geometry"], hour, is_weekend)
    except Exception as e:
        signal = {"covered": False, "reason": f"real GNN lookup failed: {e}"}

    free_flow_speed_est = (distance_km / base_time_min) * 60 if base_time_min > 0 else 0.0

    if signal.get("covered"):
        is_extrapolated = signal.get("source") == "REAL_GNN_V1_EXTRAPOLATED"
        traffic_source = "REAL_GNN_EXTRAPOLATED" if is_extrapolated else "REAL_GNN"
        real_avg_speed = signal["avg_predicted_speed_kmh"]
        slowdown_ratio = max(0.2, min(1.3, real_avg_speed / free_flow_speed_est)) if free_flow_speed_est > 0 else 1.0
        current_speed_kmh = real_avg_speed
        current_predicted_time_min = current_time_min / slowdown_ratio
    else:
        traffic_source = "HEURISTIC_FALLBACK"
        slowdown_ratio = 1.0 if base_time_min <= 0 else min(1.0, base_time_min / current_time_min) if current_time_min > 0 else 1.0
        current_predicted_time_min = current_time_min
        current_speed_kmh = (distance_km / current_predicted_time_min) * 60 if current_predicted_time_min > 0 else 0.0

    return {
        "available": True,
        "distance_km": round(distance_km, 2),
        "traffic_source": traffic_source,
        "current_speed_kmh": round(current_speed_kmh, 1),
        "current_predicted_time_min": round(current_predicted_time_min, 1),
        "slowdown_ratio": round(slowdown_ratio, 3),
        "traffic_condition": _band_from_slowdown_ratio(slowdown_ratio),
        "weather": {
            "condition": weather_data.get("condition", "unknown"),
            "impact": classify_weather_impact(weather_multiplier),
        },
        "route_geometry": primary_route["geometry"],
        "gnn_signal": signal,
    }


def get_route_forecast_2h(source: str, destination: str) -> dict:

    now = datetime.now()
    forecast_time = now + timedelta(minutes=FORECAST_HORIZON_MINUTES)

    current = _current_route_state(source, destination, now)

    base_response = {
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "current_timestamp": now.isoformat(),
        "forecast_timestamp": forecast_time.isoformat(),
        "route": {"source": source, "destination": destination},
    }

    if not current["available"]:
        return {
            **base_response,
            "available": False,
            "reason": current["reason"],
            "current": None,
            "forecast": None,
            "method": None,
            "confidence": None,
            "data_quality": None,
            "limitations": [],
        }

    temporal = get_temporal_ratio(TRAFFIC_HISTORY_CSV, now.hour, forecast_time.hour)

    limitations = [
        "Temporal signal is citywide-aggregated (all monitored real segments), not specific to this route's own segments — "
        "per-segment repeat observations are too sparse (median ~2.5 per edge) to derive a per-segment hourly pattern.",
        "Assumes current weather persists for the forecast window — no weather forecast is integrated.",
        "Cannot anticipate an unforeseen incident (accident, closure) occurring within the forecast window — "
        "see the separate live incident-detection system (/api/traffic/incidents) for that, which only detects an anomaly once it has already begun.",
        "Historical pattern currently spans a single ~24h collection window (2026-09-08/09) and cannot yet distinguish "
        "a true day-of-week effect from a one-off day.",
    ]

    if temporal["available"]:
        # Clamp the applied ratio to a sane range — a real ratio derived
        # from real data, but still bounded so a thin-sample hour can't
        # swing the forecast to an absurd extreme.
        applied_ratio = max(0.5, min(1.8, temporal["ratio"]))
        forecast_speed = round(current["current_speed_kmh"] * applied_ratio, 1)
        forecast_slowdown_ratio = max(0.15, min(1.3, current["slowdown_ratio"] * (1 / applied_ratio) if applied_ratio else current["slowdown_ratio"]))
        forecast_time_min = round(current["distance_km"] / forecast_speed * 60, 1) if forecast_speed > 0 else None
        forecast_delay_percent = round(max(0.0, (1 - forecast_slowdown_ratio)) * 100, 1)

        method = "historical_temporal_extrapolation"
        basis = (
            f"Current {current['traffic_source']} state ({current['current_speed_kmh']} km/h) adjusted by the real "
            f"historical hour-of-day speed pattern: hour {now.hour}:00 averaged speed_ratio "
            f"{temporal['current_hour_avg_speed_ratio']} (n={temporal['current_hour_samples']} real TomTom observations) "
            f"vs. hour {forecast_time.hour}:00 averaged {temporal['forecast_hour_avg_speed_ratio']} "
            f"(n={temporal['forecast_hour_samples']})."
        )

        if current["traffic_source"] == "REAL_GNN" and temporal["current_hour_samples"] >= 30 and temporal["forecast_hour_samples"] >= 30:
            data_quality = "HIGH DATA SUPPORT"
        elif current["traffic_source"] in ("REAL_GNN", "REAL_GNN_EXTRAPOLATED"):
            data_quality = "MODERATE DATA SUPPORT"
        else:
            data_quality = "LIMITED DATA SUPPORT"

    else:
        forecast_speed = current["current_speed_kmh"]
        forecast_time_min = current["current_predicted_time_min"]
        forecast_slowdown_ratio = current["slowdown_ratio"]
        forecast_delay_percent = round(max(0.0, (1 - forecast_slowdown_ratio)) * 100, 1)

        method = "persistence_estimate"
        basis = (
            f"Historical hour-of-day coverage is insufficient for this forecast window "
            f"({temporal['reason']}) — showing the current {current['traffic_source']} state carried forward "
            f"unchanged. This is NOT a temporal forecast; treat it as today's condition, not a genuine +120min projection."
        )
        data_quality = "LIMITED DATA SUPPORT"
        limitations.insert(0, "No historical temporal adjustment could be applied — see 'basis' for why.")

    return {
        **base_response,
        "available": True,
        "method": method,
        "current": {
            "traffic_condition": current["traffic_condition"],
            "speed_kmh": current["current_speed_kmh"],
            "predicted_time_min": current["current_predicted_time_min"],
            "data_source": current["traffic_source"],
        },
        "forecast": {
            "traffic_condition": _band_from_slowdown_ratio(forecast_slowdown_ratio),
            "predicted_speed_kmh": forecast_speed,
            "predicted_time_min": forecast_time_min,
            "predicted_delay_percent": forecast_delay_percent,
        },
        "basis": basis,
        "data_quality": data_quality,
        "weather": current["weather"],
        "distance_km": current["distance_km"],
        "route_geometry": current["route_geometry"],
        "limitations": limitations,
    }
