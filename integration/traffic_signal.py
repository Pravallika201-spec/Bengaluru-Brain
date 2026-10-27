"""
Traffic severity (0-100) for a NAMED AREA, for USI fusion.

Two possible sources, always labeled in the result — never silently
presented as more certain than it is:
  - REAL_GNN: the area's known coordinates (from traffic_module's curated
    location table) fall within range of one of the ~750 real
    TomTom-monitored edges the retrained GNN (real_gnn_service.py) has
    ground truth for. Severity is derived from predicted speed vs. the
    road's own free-flow/base speed.
  - SIMULATED_WARD_STRESS: no real coverage for this area; falls back to
    traffic_module/backend/ward_stress.py, which generates its numbers with
    random.* (see that file's own docstring) — not a live feed.
  - None severity + source="NO_DATA" if the area isn't in the traffic
    module's location table at all.
"""
import os
import sys
from datetime import datetime

TRAFFIC_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "traffic_module", "backend")
if TRAFFIC_BACKEND not in sys.path:
    sys.path.insert(0, TRAFFIC_BACKEND)

from location_data import BENGALURU_LOCATIONS, get_location_info  # noqa: E402
from ward_stress import get_ward_stress_by_id  # noqa: E402
import real_gnn_service  # noqa: E402


def _find_location(area_name):
    """Case-insensitive lookup into the traffic module's curated location table."""
    norm = area_name.strip().lower()
    for name, info in BENGALURU_LOCATIONS.items():
        if name.lower() == norm:
            return name, info
    return None, None


def get_traffic_severity(area_name):
    matched_name, info = _find_location(area_name)
    if info is None:
        return {
            "area_name": area_name,
            "severity": None,
            "source": "NO_DATA",
            "detail": f"'{area_name}' is not in the traffic module's known location table.",
        }

    lat, lon = info["lat"], info["lon"]
    now = datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5

    try:
        signal = real_gnn_service.get_route_traffic_signal([[lat, lon]], hour, is_weekend)
    except Exception as e:
        signal = {"covered": False, "reason": f"real GNN lookup failed: {e}"}

    if signal.get("covered"):
        segment = signal["matched_segments"][0]
        base_speed = info.get("base_speed_kph") or 40.0
        predicted_speed = segment["predicted_speed_kmh"]
        severity = max(0.0, min(100.0, 100.0 * (1.0 - predicted_speed / max(base_speed, 1.0))))
        return {
            "area_name": matched_name,
            "severity": round(severity, 1),
            "source": "REAL_GNN",
            "detail": f"Real GNN prediction near '{segment['road_name']}' "
                      f"({segment['distance_from_route_m']}m away): "
                      f"{predicted_speed} km/h predicted.",
            "model_metrics": signal.get("model_metrics"),
        }

    # Fallback: simulated ward stress, clearly labeled.
    ward_id = info.get("ward")
    ward_data = get_ward_stress_by_id(ward_id) if ward_id else None
    if ward_data:
        return {
            "area_name": matched_name,
            "severity": float(ward_data["traffic_score"]),
            "source": "SIMULATED_WARD_STRESS",
            "detail": f"No real-GNN coverage near {matched_name}; using simulated "
                      f"ward-{ward_id} stress score (ward_stress.py, random-based, not a live feed).",
        }

    return {
        "area_name": matched_name,
        "severity": None,
        "source": "NO_DATA",
        "detail": f"No real GNN coverage and no ward mapping for '{matched_name}'.",
    }
