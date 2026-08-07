"""
Ward Stress Generator for Bengaluru Traffic Prediction
Generates realistic mock USI stress data for all 369 wards
"""

import random
from datetime import datetime, time
from typing import List, Dict
from location_data import BENGALURU_LOCATIONS, get_it_zones, get_ward_name

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

# IT zones (higher baseline stress)
IT_ZONE_WARDS = [info["ward"] for info in BENGALURU_LOCATIONS.values() if info["it_zone"]]

# Major traffic corridors (higher stress during peak hours)
MAJOR_CORRIDORS = [
    6,   # Hebbal
    7,   # Manyata Tech Park
    24,  # KR Puram
    68,  # Koramangala
    74,  # Shivajinagar
    76,  # MG Road
    81,  # Indiranagar
    84,  # Whitefield
    85,  # Marathahalli
    174, # Silk Board
    175, # Sarjapur Road
    195, # Electronic City
]

def get_base_stress_score(ward_id: int, current_hour: int) -> int:
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
    Generate mock ward stress data for all 369 wards
    """
    current_hour = datetime.now().hour
    ward_data = []
    
    for ward_id in range(1, 370):  # Wards 1-369
        stress_score = get_base_stress_score(ward_id, current_hour)
        status = get_ward_status(stress_score)
        color = get_status_color(status)
        
        # Get ward name if available
        ward_name = get_ward_name(ward_id)
        
        ward_info = {
            "ward_id": ward_id,
            "ward_name": ward_name,
            "traffic_score": stress_score,
            "status": status,
            "color": color,
            "is_it_zone": ward_id in IT_ZONE_WARDS,
            "is_major_corridor": ward_id in MAJOR_CORRIDORS,
            "last_updated": datetime.now().isoformat()
        }
        
        ward_data.append(ward_info)
    
    return ward_data

def get_ward_stress_by_id(ward_id: int) -> Dict:
    """
    Get stress data for a specific ward
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

def get_stress_trend(ward_id: int, hours_back: int = 12) -> List[Dict]:
    """
    Generate mock stress trend data for a ward
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
    Get citywide stress summary
    """
    all_wards = generate_ward_stress_data()
    
    total_wards = len(all_wards)
    avg_stress = sum(ward["traffic_score"] for ward in all_wards) / total_wards
    
    status_counts = {}
    for status in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        status_counts[status] = len([w for w in all_wards if w["status"] == status])
    
    critical_wards = [w for w in all_wards if w["status"] == "CRITICAL"]
    
    summary = {
        "total_wards": total_wards,
        "average_stress": round(avg_stress, 1),
        "citywide_status": get_ward_status(int(avg_stress)),
        "status_distribution": status_counts,
        "critical_wards_count": len(critical_wards),
        "critical_wards": critical_wards[:10],  # Top 10 critical wards
        "it_zone_average": round(
            sum(w["traffic_score"] for w in all_wards if w["is_it_zone"]) / 
            len([w for w in all_wards if w["is_it_zone"]]), 1
        ) if len([w for w in all_wards if w["is_it_zone"]]) > 0 else 0,
        "last_updated": datetime.now().isoformat()
    }
    
    return summary

def simulate_stress_change(ward_id: int, change_factor: float) -> Dict:
    """
    Simulate stress change for a ward (for incident simulation)
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
