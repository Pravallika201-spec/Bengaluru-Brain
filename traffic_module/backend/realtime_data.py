import requests
from datetime import datetime
import json

# ── WEATHER (OpenWeatherMap free API) ──────────────
# Get your FREE API key at: https://openweathermap.org/api
# Free tier: 1,000 calls/day (plenty for demo)
# Replace "your_free_key_from_openweathermap.org" with your actual key
OWM_API_KEY = "REDACTED-ROTATED-KEY-SEE-SECURITY-NOTES"
BENGALURU_LAT = 12.9716
BENGALURU_LON = 77.5946

def get_live_weather():
    """
    Fetches real current weather for Bengaluru.
    Free tier: 1000 calls/day. More than enough.
    Get key free at: openweathermap.org/api
    """
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={BENGALURU_LAT}&lon={BENGALURU_LON}"
            f"&appid={OWM_API_KEY}&units=metric"
        )
        r = requests.get(url, timeout=5)
        data = r.json()
        
        weather_id = data["weather"][0]["id"]
        temp = data["main"]["temp"]
        description = data["weather"][0]["description"]
        
        # Map OpenWeatherMap codes to your weather types
        if weather_id >= 800:
            weather_type = "clear"
            weather_code = 0
        elif weather_id >= 700:
            weather_type = "fog"
            weather_code = 4
        elif weather_id >= 500:
            rain_mm = data.get("rain", {}).get("1h", 0)
            if rain_mm > 10:
                weather_type = "heavy_rain"
                weather_code = 2
            else:
                weather_type = "light_rain"
                weather_code = 1
        elif weather_id >= 200:
            weather_type = "storm"
            weather_code = 3
        else:
            weather_type = "clear"
            weather_code = 0

        # Weather multiplier for travel time
        weather_multipliers = {
            "clear": 1.0,
            "light_rain": 1.25,
            "heavy_rain": 1.55,
            "storm": 1.80,
            "fog": 1.35
        }
        
        return {
            "type": weather_type,
            "code": weather_code,
            "description": description,
            "temp_c": round(temp, 1),
            "multiplier": weather_multipliers[weather_type]
        }
    except Exception as e:
        print(f"Weather API failed: {e}, using clear")
        return {
            "type": "clear", "code": 0,
            "description": "clear sky", "temp_c": 28.0,
            "multiplier": 1.0
        }


# ── IT PARK SHIFT TIMINGS ──────────────────────────
IT_PARKS = {
    "Manyata Tech Park": {
        "wards": [6, 7, 8],
        "shifts": [
            {"start": 8,  "end": 9,  "type": "IN",  "mult": 2.2},
            {"start": 17, "end": 19, "type": "OUT", "mult": 2.6},
            {"start": 21, "end": 22, "type": "OUT", "mult": 1.8},
        ]
    },
    "Electronic City": {
        "wards": [194, 195, 196],
        "shifts": [
            {"start": 8,  "end": 10, "type": "IN",  "mult": 2.3},
            {"start": 17, "end": 20, "type": "OUT", "mult": 2.8},
            {"start": 22, "end": 23, "type": "OUT", "mult": 1.6},
        ]
    },
    "Whitefield ITPL": {
        "wards": [83, 84, 85],
        "shifts": [
            {"start": 9,  "end": 10, "type": "IN",  "mult": 2.4},
            {"start": 18, "end": 20, "type": "OUT", "mult": 2.9},
        ]
    },
    "Outer Ring Road (Marathahalli-Sarjapur)": {
        "wards": [85, 174, 175],
        "shifts": [
            {"start": 8,  "end": 10, "type": "IN",  "mult": 2.6},
            {"start": 17, "end": 20, "type": "OUT", "mult": 3.0},
        ]
    },
    "Hebbal Tech Corridor": {
        "wards": [5, 6, 7],
        "shifts": [
            {"start": 8,  "end": 9,  "type": "IN",  "mult": 2.1},
            {"start": 17, "end": 19, "type": "OUT", "mult": 2.4},
        ]
    }
}

def get_active_it_shifts(hour, is_weekday):
    """
    Returns which IT parks are in active shift change
    right now and their traffic multiplier.
    """
    if not is_weekday:
        return [], 1.0

    active = []
    max_mult = 1.0

    for park_name, park_data in IT_PARKS.items():
        for shift in park_data["shifts"]:
            if shift["start"] <= hour < shift["end"]:
                active.append({
                    "park": park_name,
                    "shift_type": shift["type"],
                    "multiplier": shift["mult"],
                    "wards": park_data["wards"]
                })
                max_mult = max(max_mult, shift["mult"])

    return active, max_mult


# ── LIVE EVENTS (Bengaluru) ────────────────────────
BENGALURU_EVENTS_2025 = [
    # IPL RCB home matches at Chinnaswamy
    {"name": "IPL: RCB vs MI",   "date": "2025-04-02",
     "time_start": 19, "time_end": 23,
     "location": "Chinnaswamy Stadium",
     "affected_wards": [74,75,76,80,81], "mult": 2.1},
    {"name": "IPL: RCB vs CSK",  "date": "2025-04-15",
     "time_start": 19, "time_end": 23,
     "location": "Chinnaswamy Stadium",
     "affected_wards": [74,75,76,80,81], "mult": 2.1},
    {"name": "IPL: RCB vs KKR",  "date": "2025-04-27",
     "time_start": 15, "time_end": 19,
     "location": "Chinnaswamy Stadium",
     "affected_wards": [74,75,76,80,81], "mult": 2.0},
    # Concerts and events
    {"name": "Bengaluru Marathon", "date": "2025-10-19",
     "time_start": 5, "time_end": 12,
     "location": "MG Road",
     "affected_wards": [74,75,76,77,78], "mult": 2.5},
    # Festivals
    {"name": "Dasara",    "date": "2025-10-02",
     "time_start": 0, "time_end": 23,
     "location": "citywide", "affected_wards": [],
     "citywide": True, "mult": 1.6},
    {"name": "Ugadi",     "date": "2025-03-30",
     "time_start": 0, "time_end": 23,
     "location": "citywide", "affected_wards": [],
     "citywide": True, "mult": 1.4},
    {"name": "Ganesh Chaturthi", "date": "2025-08-27",
     "time_start": 0, "time_end": 23,
     "location": "citywide", "affected_wards": [],
     "citywide": True, "mult": 1.5},
]

def get_active_events(affected_ward_ids=None):
    """
    Returns events active RIGHT NOW that affect 
    the given wards.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    active = []
    max_mult = 1.0

    for event in BENGALURU_EVENTS_2025:
        if event["date"] != today_str:
            continue
        if not (event["time_start"] <= current_hour 
                <= event["time_end"]):
            continue
        
        # Check if event affects route wards
        is_citywide = event.get("citywide", False)
        affects_route = is_citywide
        
        if not is_citywide and affected_ward_ids:
            overlap = set(event["affected_wards"]) & \
                      set(affected_ward_ids)
            affects_route = len(overlap) > 0

        if affects_route:
            active.append(event)
            max_mult = max(max_mult, event["mult"])

    return active, max_mult


# ── COMBINED REAL-TIME MULTIPLIER ─────────────────
def get_realtime_multiplier(hour, is_weekday, 
                             affected_wards=None):
    """
    Combines weather + IT shifts + events into 
    one final multiplier for travel time.
    """
    weather = get_live_weather()
    it_shifts, it_mult = get_active_it_shifts(
        hour, is_weekday
    )
    events, event_mult = get_active_events(affected_wards)

    # Combine: use max of IT/event, then multiply by weather
    # Cap total so it stays realistic
    traffic_mult = max(it_mult, event_mult)
    final_mult = min(traffic_mult * weather["multiplier"], 3.0)

    return {
        "final_multiplier": round(final_mult, 2),
        "weather": weather,
        "active_it_shifts": it_shifts,
        "active_events": events,
        "breakdown": {
            "weather_mult": weather["multiplier"],
            "it_shift_mult": round(it_mult, 2),
            "event_mult": round(event_mult, 2),
        }
    }
