"""
Ward Stress Generator for Bengaluru Traffic Prediction
Generates SIMULATED (random.*, not a live feed) stress scores across the
REAL 369-ward registry (integration/geo/ward_registry.json — real OSM
admin_level=10 relations). Ward identity here is the canonical
BBMP/OSM ward_id, the same one used by /api/wards/*, the waste module's
area_osm_id join, and location_data.py's canonical_ward_id — this was
previously an arbitrary, unrelated sequential 1-369 numbering (see Priority
2 ward-identity audit); fixed 2026-09-03 so there is exactly one ward
identity system, not two silently-coexisting ones.
"""
import json
import os
import random
from datetime import datetime
from typing import List, Dict
from location_data import BENGALURU_LOCATIONS

_HERE = os.path.dirname(os.path.abspath(__file__))
_WARD_REGISTRY_PATH = os.path.join(_HERE, "..", "..", "integration", "geo", "ward_registry.json")


def _load_real_wards():
    """Real 369 wards: ward_id (real OSM relation id, the SAME id used by
    /api/wards/*, the waste module's area_osm_id join, and
    location_data.py's canonical_ward_id), ward_name, centroid — all read
    directly from the one real registry (integration/geo/ward_registry.json,
    built by integration/geo/build_ward_registry.py from a live Overpass
    query). Falls back to an empty list (never fabricated placeholder
    wards) if the registry isn't present on this machine."""
    wards = []
    try:
        with open(_WARD_REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
        entries = registry.get("wards", {})
        # "wards" is a dict keyed by ward_id (string or int) -> ward record
        for w in (entries.values() if isinstance(entries, dict) else entries):
            wards.append({
                "ward_id": w.get("ward_id"),
                "ward_name": w.get("ward_name"),
                "lat": w.get("centroid_lat"),
                "lon": w.get("centroid_lon"),
            })
    except (OSError, json.JSONDecodeError):
        pass
    return wards


_REAL_WARDS = _load_real_wards()

# Ward stress levels and status mapping
STRESS_LEVELS = {
    "LOW": (0, 40),
    "MEDIUM": (40, 70),
    "HIGH": (70, 90),
    "CRITICAL": (90, 100)
}

STATUS_COLORS = {
    "LOW": "GREEN",
    "MEDIUM": "YELLOW",
    "HIGH": "ORANGE",
    "CRITICAL": "RED"
}

# IT zones and major corridors, now keyed by the REAL canonical_ward_id
# (resolved via point-in-polygon against the real ward boundaries — see
# location_data.py) instead of an arbitrary hand-picked integer list.
IT_ZONE_WARDS = {info["canonical_ward_id"] for info in BENGALURU_LOCATIONS.values()
                  if info["it_zone"] and info.get("canonical_ward_id")}

_CORRIDOR_LOCATION_NAMES = [
    "Hebbal", "Manyata Tech Park", "KR Puram", "Koramangala", "Shivajinagar",
    "MG Road", "Indiranagar", "Whitefield", "Marathahalli", "Silk Board",
    "Sarjapur Road", "Electronic City",
]
MAJOR_CORRIDORS = {BENGALURU_LOCATIONS[name]["canonical_ward_id"]
                    for name in _CORRIDOR_LOCATION_NAMES
                    if name in BENGALURU_LOCATIONS and BENGALURU_LOCATIONS[name].get("canonical_ward_id")}


def get_base_stress_score(ward_id, current_hour: int) -> int:
    """
    Get base stress score for a ward based on time and ward characteristics
    """
    # Time-based baseline
    if 8 <= current_hour <= 10:  # Morning peak
        time_baseline = random.randint(60, 85)
    elif 17 <= current_hour <= 19:  # Evening peak
        time_baseline = random.randint(65, 90)
    elif 11 <= current_hour <= 16:  # Daytime
        time_baseline = random.randint(40, 65)
    elif 20 <= current_hour <= 22:  # Evening
        time_baseline = random.randint(30, 55)
    else:  # Night/early morning
        time_baseline = random.randint(10, 30)

    # Ward-specific adjustments
    ward_multiplier = 1.0

    # IT zones have higher stress during peak hours
    if ward_id in IT_ZONE_WARDS and (8 <= current_hour <= 10 or 17 <= current_hour <= 19):
        ward_multiplier *= 1.3

    # Major corridors have higher baseline stress
    if ward_id in MAJOR_CORRIDORS:
        ward_multiplier *= 1.2

    # Add some randomness
    random_factor = random.uniform(0.9, 1.1)

    base_score = int(time_baseline * ward_multiplier * random_factor)
    return min(100, max(0, base_score))

def get_ward_status(stress_score: int) -> str:
    """
    Get ward status based on stress score
    """
    if stress_score < 40:
        return "LOW"
    elif stress_score < 70:
        return "MEDIUM"
    elif stress_score < 90:
        return "HIGH"
    else:
        return "CRITICAL"

def get_status_color(status: str) -> str:
    """
    Get color code for ward status
    """
    return STATUS_COLORS.get(status, "GREEN")

def generate_ward_stress_data() -> List[Dict]:
    """
    Generate SIMULATED stress data for all real 369 wards. Ward identity
    (ward_id, ward_name) is real; only the traffic_score is simulated.
    """
    current_hour = datetime.now().hour
    ward_data = []

    for ward in _REAL_WARDS:
        ward_id = ward["ward_id"]
        stress_score = get_base_stress_score(ward_id, current_hour)
        status = get_ward_status(stress_score)
        color = get_status_color(status)

        ward_info = {
            "ward_id": ward_id,
            "ward_name": ward["ward_name"],
            "latitude": ward.get("lat"),
            "longitude": ward.get("lon"),
            "traffic_score": stress_score,
            "status": status,
            "color": color,
            "is_it_zone": ward_id in IT_ZONE_WARDS,
            "is_major_corridor": ward_id in MAJOR_CORRIDORS,
            "last_updated": datetime.now().isoformat()
        }

        ward_data.append(ward_info)

    return ward_data

def get_ward_stress_by_id(ward_id) -> Dict:
    """
    Get stress data for a specific REAL ward_id (canonical OSM id).
    """
    all_wards = generate_ward_stress_data()
    for ward in all_wards:
        if ward["ward_id"] == ward_id:
            return ward
    return None

def get_high_stress_wards(threshold: int = 70) -> List[Dict]:
    """
    Get wards with stress score above threshold
    """
    all_wards = generate_ward_stress_data()
    return [ward for ward in all_wards if ward["traffic_score"] >= threshold]

def get_it_zone_stress() -> List[Dict]:
    """
    Get stress data for all IT zones
    """
    all_wards = generate_ward_stress_data()
    return [ward for ward in all_wards if ward["is_it_zone"]]

def get_major_corridor_stress() -> List[Dict]:
    """
    Get stress data for major traffic corridors
    """
    all_wards = generate_ward_stress_data()
    return [ward for ward in all_wards if ward["is_major_corridor"]]

def get_stress_trend(ward_id, hours_back: int = 12) -> List[Dict]:
    """
    Generate mock stress trend data for a ward (real canonical ward_id)
    """
    current_hour = datetime.now().hour
    trend_data = []

    for i in range(hours_back):
        hour = (current_hour - hours_back + i + 24) % 24
        stress_score = get_base_stress_score(ward_id, hour)
        status = get_ward_status(stress_score)

        trend_data.append({
            "hour": hour,
            "stress_score": stress_score,
            "status": status,
            "timestamp": datetime.now().replace(hour=hour, minute=0, second=0).isoformat()
        })

    return trend_data

def get_citywide_stress_summary() -> Dict:
    """
    Get citywide stress summary across the real 369-ward registry
    """
    all_wards = generate_ward_stress_data()

    total_wards = len(all_wards)
    if total_wards == 0:
        return {"total_wards": 0, "average_stress": None, "citywide_status": "UNKNOWN",
                 "status_distribution": {}, "critical_wards_count": 0, "critical_wards": [],
                 "it_zone_average": 0, "last_updated": datetime.now().isoformat()}
    avg_stress = sum(ward["traffic_score"] for ward in all_wards) / total_wards

    status_counts = {}
    for status in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        status_counts[status] = len([w for w in all_wards if w["status"] == status])

    critical_wards = [w for w in all_wards if w["status"] == "CRITICAL"]
    it_zone_wards = [w for w in all_wards if w["is_it_zone"]]

    summary = {
        "total_wards": total_wards,
        "average_stress": round(avg_stress, 1),
        "citywide_status": get_ward_status(int(avg_stress)),
        "status_distribution": status_counts,
        "critical_wards_count": len(critical_wards),
        "critical_wards": critical_wards[:10],  # Top 10 critical wards
        "it_zone_average": round(sum(w["traffic_score"] for w in it_zone_wards) / len(it_zone_wards), 1)
                             if it_zone_wards else 0,
        "last_updated": datetime.now().isoformat()
    }

    return summary

def simulate_stress_change(ward_id, change_factor: float) -> Dict:
    """
    Simulate stress change for a ward (for incident simulation). ward_id is
    the real canonical ward id.
    """
    current_data = get_ward_stress_by_id(ward_id)
    if not current_data:
        return None

    new_stress = int(current_data["traffic_score"] * change_factor)
    new_stress = min(100, max(0, new_stress))

    updated_data = current_data.copy()
    updated_data["traffic_score"] = new_stress
    updated_data["status"] = get_ward_status(new_stress)
    updated_data["color"] = get_status_color(updated_data["status"])
    updated_data["last_updated"] = datetime.now().isoformat()

    return updated_data
