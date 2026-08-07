from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from datetime import datetime, timedelta

from geopy.geocoders import Nominatim

import openrouteservice
import math
import numpy as np

# ---------------- CUSTOM BENGALURU LOCATIONS ----------------

BENGALURU_LOCATIONS = {
    "silk board": [12.9177, 77.6238],
    "new horizon college": [12.9676, 77.7150],
    "hebbal": [13.0358, 77.5970],
    "marathahalli": [12.9591, 77.6974],
    "tin factory": [12.9456, 77.6123],
    "electronic city": [12.8440, 77.6757],
    "whitefield": [12.9698, 77.7500],
    "mg road": [12.9747, 77.6093],
    "indiranagar": [12.9742, 77.6414],
    "koramangala": [12.9352, 77.6245],
    "hsr layout": [12.9106, 77.6385],
    "bellandur": [12.9259, 77.6676],
    "sarjapur": [12.9236, 77.6762],
    "kr puram": [13.0167, 77.5537],
    "yelahanka": [13.0996, 77.5866],
    "bannerghatta": [12.8000, 77.5700],
    "jayadeva": [12.9250, 77.6000],
    "domlur": [12.9550, 77.6350],
    "old airport road": [12.9650, 77.6450],
    "outer ring road": [12.9500, 77.6500],
    "majestic": [12.9767, 77.5713],
    "airport": [13.1986, 77.7066],
    "btm layout": [12.9165, 77.6101],
}
# ---------------- APP ----------------

app = FastAPI()

# ---------------- CORS ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- OPENROUTESERVICE ----------------

client = openrouteservice.Client(
    key="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjIzOTQ1YjdiMjVjNzQ1YTk5YmFhMzhhZTA5M2JjOTFjIiwiaCI6Im11cm11cjY0In0="
)

# ---------------- GEOCODER ----------------

geolocator = Nominatim(
    user_agent="bengaluru_brain",
    timeout=10
)

# ---------------- REQUEST MODEL ----------------

class RouteRequest(BaseModel):

    source: str
    destination: str

# ---------------- REALISTIC BENGALURU CONGESTION DATA ----------------

BENGALURU_CONGESTION_ZONES = {
    "hebbal": {"base_multiplier": 1.10, "peak_multiplier": 1.35, "corridor": "bellary"},
    "silk board": {"base_multiplier": 1.15, "peak_multiplier": 1.45, "corridor": "hosur"},
    "marathahalli": {"base_multiplier": 1.10, "peak_multiplier": 1.40, "corridor": "orr"},
    "bellandur": {"base_multiplier": 1.08, "peak_multiplier": 1.35, "corridor": "orr"},
    "whitefield": {"base_multiplier": 1.10, "peak_multiplier": 1.38, "corridor": "whitefield"},
    "electronic city": {"base_multiplier": 1.12, "peak_multiplier": 1.42, "corridor": "hosur"},
    "kr puram": {"base_multiplier": 1.08, "peak_multiplier": 1.32, "corridor": "bellary"},
    "outer ring road": {"base_multiplier": 1.08, "peak_multiplier": 1.35, "corridor": "orr"},
    "koramangala": {"base_multiplier": 1.05, "peak_multiplier": 1.25, "corridor": "inner"},
    "indiranagar": {"base_multiplier": 1.05, "peak_multiplier": 1.22, "corridor": "inner"},
    "mg road": {"base_multiplier": 1.05, "peak_multiplier": 1.20, "corridor": "central"},
    "majestic": {"base_multiplier": 1.08, "peak_multiplier": 1.30, "corridor": "central"},
    "btm layout": {"base_multiplier": 1.05, "peak_multiplier": 1.25, "corridor": "south"},
    "hsr layout": {"base_multiplier": 1.05, "peak_multiplier": 1.22, "corridor": "south"},
    "jayanagar": {"base_multiplier": 1.03, "peak_multiplier": 1.18, "corridor": "south"},
    "basavanagudi": {"base_multiplier": 1.02, "peak_multiplier": 1.15, "corridor": "south"},
    "malleswaram": {"base_multiplier": 1.03, "peak_multiplier": 1.18, "corridor": "north"},
    "yeshwanthpur": {"base_multiplier": 1.05, "peak_multiplier": 1.22, "corridor": "north"},
    "rajajinagar": {"base_multiplier": 1.02, "peak_multiplier": 1.15, "corridor": "west"},
    "vijayanagar": {"base_multiplier": 1.02, "peak_multiplier": 1.15, "corridor": "west"},
    "default": {"base_multiplier": 1.00, "peak_multiplier": 1.20, "corridor": "unknown"}
}

# ---------------- IT PARK INTELLIGENCE ----------------

IT_PARKS_DATA = {
    "electronic city": {
        "employees": 150000,
        "morning_shift": "8:30-9:30",
        "evening_shift": "17:30-19:00",
        "corridors": ["hosur road", "silk board", "btm layout"]
    },
    "whitefield": {
        "employees": 120000,
        "morning_shift": "9:00-10:00",
        "evening_shift": "18:00-20:00",
        "corridors": ["marathahalli", "outer ring road", "varthur road"]
    },
    "manyata tech park": {
        "employees": 80000,
        "morning_shift": "8:00-9:00",
        "evening_shift": "17:00-18:30",
        "corridors": ["hebbal", "bellary road", "nh44"]
    },
    "bellandur": {
        "employees": 60000,
        "morning_shift": "8:30-9:30",
        "evening_shift": "17:30-19:00",
        "corridors": ["outer ring road", "marathahalli", "sarjapur road"]
    },
    "marathahalli": {
        "employees": 50000,
        "morning_shift": "9:00-10:00",
        "evening_shift": "18:00-19:30",
        "corridors": ["outer ring road", "whitefield", "hal airport road"]
    },
    "hsr layout": {
        "employees": 40000,
        "morning_shift": "9:00-10:00",
        "evening_shift": "18:00-19:00",
        "corridors": ["sarjapur road", "koramangala", "silk board"]
    }
}

# ---------------- WEATHER INTELLIGENCE ----------------

WEATHER_MULTIPLIERS = {
    "clear": {"delay_multiplier": 1.00, "speed_reduction": 0.0},
    "cloudy": {"delay_multiplier": 1.05, "speed_reduction": 0.03},
    "light_rain": {"delay_multiplier": 1.10, "speed_reduction": 0.08},
    "rain": {"delay_multiplier": 1.15, "speed_reduction": 0.12},
    "heavy_rain": {"delay_multiplier": 1.20, "speed_reduction": 0.18},
    "storm": {"delay_multiplier": 1.25, "speed_reduction": 0.22},
    "fog": {"delay_multiplier": 1.12, "speed_reduction": 0.10}
}

def get_weather():
    """Get real weather from OpenWeatherMap API"""
    try:
        import requests
        from realtime_data import OWM_API_KEY, BENGALURU_LAT, BENGALURU_LON
        
        if OWM_API_KEY == "your_free_key_from_openweathermap.org":
            return "clear"  # Default if no API key
        
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={BENGALURU_LAT}&lon={BENGALURU_LON}&appid={OWM_API_KEY}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            weather_main = data["weather"][0]["main"].lower()
            
            # Map OpenWeatherMap weather to our system
            weather_map = {
                "clear": "clear",
                "clouds": "cloudy",
                "mist": "fog",
                "fog": "fog",
                "haze": "fog",
                "drizzle": "light_rain",
                "rain": "rain",
                "thunderstorm": "heavy_rain",
                "squall": "heavy_rain",
                "tornado": "heavy_rain"
            }
            
            return weather_map.get(weather_main, "clear")
        else:
            return "clear"  # Default if API fails
    except Exception as e:
        print(f"Weather API failed: {e}")
        return "clear"  # Default on any error

# ---------------- EVENT INTELLIGENCE ----------------

EVENT_LOCATIONS = {
    "chinnaswamy stadium": {"event": "IPL Match", "congestion_multiplier": 2.5},
    "mg road": {"event": "Concert", "congestion_multiplier": 2.0},
    "palace grounds": {"event": "Public Event", "congestion_multiplier": 1.8},
    "cubbon park": {"event": "Weekend Event", "congestion_multiplier": 1.5},
    "forum mall": {"event": "Weekend Mall Traffic", "congestion_multiplier": 1.6},
    "phoenix mall": {"event": "Weekend Mall Traffic", "congestion_multiplier": 1.6},
    "garuda mall": {"event": "Weekend Mall Traffic", "congestion_multiplier": 1.5}
}

def get_event_status(source, destination, hour, is_weekend):
    event_name = "No Major Event"
    event_multiplier = 1.0
    
    for location, event_data in EVENT_LOCATIONS.items():
        if (location.lower() in source.lower() or 
            location.lower() in destination.lower()):
            
            # Check if event is active (weekend evenings)
            if is_weekend and (18 <= hour <= 22):
                event_name = event_data["event"]
                event_multiplier = event_data["congestion_multiplier"]
            elif not is_weekend and (18 <= hour <= 21):
                event_name = event_data["event"]
                event_multiplier = event_data["congestion_multiplier"] * 0.8
    
    return event_name, event_multiplier

# ---------------- GET COORDINATES ----------------

def get_coordinates(location):
    """Get coordinates for a location using custom dictionary first, then geocoder"""
    location_lower = location.lower().strip()
    
    # Check custom dictionary FIRST
    for key, coords in BENGALURU_LOCATIONS.items():
        if key in location_lower or location_lower in key:
            return coords
    
    # Use geocoder if not found in dictionary
    geolocator = Nominatim(user_agent="bengaluru_traffic")
    try:
        result = geolocator.geocode(f"{location}, Bengaluru, Karnataka, India")
        if result:
            return [result.latitude, result.longitude]
    except Exception as e:
        print(f"Geocoding failed for {location}: {e}")
    return None

# ---------------- ENHANCED TRAFFIC PREDICTION ----------------

def get_it_park_impact(source, destination, hour):
    """Calculate IT park impact based on employee count and shift timings"""
    it_impact = 1.0
    
    for park_name, park_data in IT_PARKS_DATA.items():
        if (park_name.lower() in source.lower() or 
            park_name.lower() in destination.lower() or
            any(corridor.lower() in source.lower() or corridor.lower() in destination.lower() 
                for corridor in park_data["corridors"])):
            
            # Morning shift impact (8-11 AM): +15-25%
            if 8 <= hour <= 10:
                it_impact *= 1.20
            elif 10 <= hour <= 11:
                it_impact *= 1.15
            # Evening shift impact (5-8 PM): +20-30%
            elif 17 <= hour <= 19:
                it_impact *= 1.25
            elif 19 <= hour <= 20:
                it_impact *= 1.20
            # Shift overlap periods: +10-15%
            elif 7 <= hour <= 8 or 11 <= hour <= 12 or 16 <= hour <= 17 or 20 <= hour <= 21:
                it_impact *= 1.10
            
            # Employee count scaling (max +10%)
            employee_factor = 1 + min(0.10, park_data["employees"] / 200000)
            it_impact *= employee_factor
    
    return it_impact

# REAL BENGALURU SPEED TABLE (verified from actual travel)
SPEED_TABLE = {
    # (is_weekday, hour_range): avg speed km/h
    # WEEKDAY speeds
    (True, range(0,  6)):  40,  # midnight - 5am: fast
    (True, range(6,  7)):  30,  # 6am: building up
    (True, range(7,  8)):  20,  # 7am: getting bad
    (True, range(8, 11)):  15,  # 8-11am: MORNING PEAK (12-18 km/h)
    (True, range(11,17)):  24,  # 11am-5pm: afternoon (20-28 km/h)
    (True, range(17,22)):  13,  # 5-10pm: EVENING PEAK (10-16 km/h)
    (True, range(22,24)):  35,  # 10pm+: late night (35-45 km/h)
    
    # WEEKEND speeds (always faster, 25-35 km/h average)
    (False, range(0,  8)):  38,  # night/early: fast
    (False, range(8, 12)):  30,  # 8am-12pm: light
    (False, range(12,18)):  28,  # afternoon: moderate
    (False, range(18,21)):  25,  # evening: some traffic
    (False, range(21,24)):  35,  # night: good
}

def get_bengaluru_speed(hour, is_weekday, route_type):
    """
    route_type: "orr" (Outer Ring Road - worst)
                "normal" (regular roads)
                "clear" (NH/wide roads)
    """
    # Find base speed from table
    base_speed = 25  # default
    for (weekday, hours), speed in SPEED_TABLE.items():
        if weekday == is_weekday and hour in hours:
            base_speed = speed
            break
    
    # ORR corridor always 25% worse than average
    if route_type == "orr":
        base_speed = base_speed * 0.75
    elif route_type == "clear":
        base_speed = base_speed * 1.15
    
    # Never below 10, never above 50
    return max(10, min(50, base_speed))

def detect_route_type(source, destination):
    """
    Detects if route uses ORR or normal roads based on location names.
    """
    route_str = f"{source.lower()} {destination.lower()}"
    
    if any(x in route_str for x in [
        "outer ring", "orr", "sarjapur", "marathahalli", "whitefield", "electronic city"
    ]):
        return "orr"
    elif any(x in route_str for x in [
        "national highway", "nh", "tumkur", "bellary", "hosur", "mysore"
    ]):
        return "clear"
    else:
        return "normal"

def get_congestion_multiplier(location, hour, is_weekend):
    """Get congestion multiplier for a specific location"""
    location_key = location.lower()
    
    # Find matching congestion zone
    for zone, data in BENGALURU_CONGESTION_ZONES.items():
        if zone in location_key:
            if is_weekend:
                return data["base_multiplier"]
            elif 8 <= hour <= 10 or 17 <= hour <= 19:
                return data["peak_multiplier"]
            else:
                return data["base_multiplier"]
    
    return BENGALURU_CONGESTION_ZONES["default"]["base_multiplier"]

def predict_traffic(source, destination):

    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()
    is_weekday = weekday < 5  # Mon=0...Sun=6
    day_name = now.strftime("%A")

    coord1 = get_coordinates(source)
    coord2 = get_coordinates(destination)

    if not coord1 or not coord2:
        return {
            "traffic": "UNKNOWN",
            "delay": 0,
            "travel_time": 0,
            "weather": "unknown",
            "event": "unknown",
            "source_coords": [12.9716, 77.5946],
            "destination_coords": [12.9716, 77.5946],
            "route_coords": [],
            "distance_km": 0,
            "avg_speed": 0,
            "factors": [],
            "confidence": 0,
            "status": "Unable to predict"
        }

    # ---------------- ROUTING ----------------

    try:
        route = client.directions(
            coordinates=[[coord1[1], coord1[0]], [coord2[1], coord2[0]]],
            profile='driving-car',
            format='geojson'
        )
        geometry = route["features"][0]["geometry"]["coordinates"]
        route_coords = [[lat, lon] for lon, lat in geometry]
        
        # Get ACTUAL road distance from OpenRouteService (in meters)
        # Try different possible response structures
        try:
            distance_m = route["features"][0]["properties"]["segments"][0]["distance"]
        except (KeyError, IndexError):
            # Fallback to summary distance
            distance_m = route["features"][0]["properties"]["summary"]["distance"]
        
        distance = distance_m / 1000  # Convert to km
        
        # Get ACTUAL route duration from OpenRouteService (in seconds)
        try:
            duration_s = route["features"][0]["properties"]["segments"][0]["duration"]
        except (KeyError, IndexError):
            # Fallback to summary duration
            duration_s = route["features"][0]["properties"]["summary"]["duration"]
        
        base_duration_mins = duration_s / 60  # Convert to minutes
        
        # Validate route realism - check if distance is > 1.6x straight-line distance
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        straight_line_distance = 6371 * c  # Earth's radius in km
        
        if distance > straight_line_distance * 1.6:
            print(f"Warning: Route distance ({distance:.2f} km) is > 1.6x straight-line ({straight_line_distance:.2f} km)")
            print("This may indicate incorrect location matching. Using straight-line distance as fallback.")
            distance = straight_line_distance * 1.3  # Realistic road distance multiplier
            base_duration_mins = (distance / 30) * 60  # Re-estimate duration
        
        print(f"Route: {source} → {destination}")
        print(f"Distance: {distance:.2f} km (from ORS: {distance_m:.0f} m)")
        print(f"Base Duration: {base_duration_mins:.2f} mins (from ORS: {duration_s:.0f} s)")
    except Exception as e:
        print(f"Routing failed: {e}")
        route_coords = []
        # Fallback to haversine if routing fails
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance = 6371 * c
        base_duration_mins = (distance / 30) * 60  # Estimate

    # ---------------- REALISTIC TRAFFIC MULTIPLIERS ----------------

    # Detect route type
    route_type = detect_route_type(source, destination)
    
    # Get REAL speed for current time
    current_speed = get_bengaluru_speed(hour, is_weekday, route_type)
    
    # Weather adjustment (small, realistic)
    weather = get_weather()
    weather_adjustments = {
        "clear":      1.00,
        "light_rain": 0.85,  # 15% slower
        "heavy_rain": 0.65,  # 35% slower
        "storm":      0.50,  # 50% slower
        "fog":        0.75,  # 25% slower
    }
    weather_mult = weather_adjustments.get(weather, 1.0)
    
    # Apply traffic multiplier to ACTUAL route duration
    # Calculate multiplier based on time of day and route type
    if not is_weekday and (8 <= hour <= 11 or 17 <= hour <= 21):
        # Weekday peak hours (8-11 AM, 5-9 PM): 1.20-1.50
        traffic_multiplier = 1.35
    elif not is_weekday:
        # Weekday normal hours: 1.00-1.15
        traffic_multiplier = 1.08
    else:
        # Weekend: 1.05-1.15 (lower congestion)
        traffic_multiplier = 1.10
    
    # Apply congestion zone multiplier
    for zone_name, zone_data in BENGALURU_CONGESTION_ZONES.items():
        if zone_name in source.lower() or zone_name in destination.lower():
            if not is_weekday and (8 <= hour <= 11 or 17 <= hour <= 21):
                traffic_multiplier = max(traffic_multiplier, zone_data["peak_multiplier"])
            else:
                traffic_multiplier = max(traffic_multiplier, zone_data["base_multiplier"])
            break
    
    # Apply IT park impact (10-35%)
    it_impact = get_it_park_impact(source, destination, hour)
    traffic_multiplier *= it_impact
    
    # Apply event impact (5-20%)
    event_name, event_multiplier = get_event_status(source, destination, hour, is_weekday)
    traffic_multiplier *= event_multiplier
    
    # Apply weather multiplier (5-25%)
    weather_data = WEATHER_MULTIPLIERS.get(weather, {"delay_multiplier": 1.00})
    weather_mult = weather_data["delay_multiplier"]
    final_multiplier = traffic_multiplier * weather_mult
    
    # Calculate realistic duration based on actual route duration
    adjusted_duration_mins = round(base_duration_mins * final_multiplier)
    
    # Calculate delay
    delay_mins = max(0, adjusted_duration_mins - base_duration_mins)
    delay_mins = round(delay_mins)  # Ensure integer
    
    # Calculate average speed from actual distance and adjusted duration
    avg_speed = round((distance / adjusted_duration_mins) * 60, 1)
    
    # Calculate GNN traffic score (0-100)
    try:
        from gnn_model import run_gnn
        import osmnx as ox
        # Load Bengaluru graph (simplified for demo)
        G = ox.load_graphml("data/bangalore_road_graph.graphml") if os.path.exists("data/bangalore_road_graph.graphml") else None
        if G:
            weather_code = 0  # 0=clear, 1=cloudy, 2=rain, 3=heavy_rain, 4=storm
            if weather == "cloudy": weather_code = 1
            elif weather == "rain": weather_code = 2
            elif weather == "heavy_rain": weather_code = 3
            elif weather == "storm": weather_code = 4
            
            gnn_scores = run_gnn(G, hour, is_weekday, weather_code)
            # Get average score for route nodes (simplified)
            traffic_score = int(np.mean(list(gnn_scores.values())) * 100)
        else:
            # Fallback: calculate traffic score from delay percentage
            delay_percentage = (delay_mins / base_duration_mins) * 100
            traffic_score = min(100, int(delay_percentage * 1.5))
    except Exception as e:
        print(f"GNN prediction failed: {e}")
        # Fallback: calculate traffic score from delay percentage
        delay_percentage = (delay_mins / base_duration_mins) * 100
        traffic_score = min(100, int(delay_percentage * 1.5))
    
    # Status based on traffic score
    if traffic_score >= 76:      status = "CRITICAL"
    elif traffic_score >= 51:    status = "HIGH"
    elif traffic_score >= 26:    status = "MODERATE"
    elif traffic_score >= 1:     status = "LOW"
    else:                        status = "CLEAR"
    
    # Calculate confidence score (70-95%)
    confidence = 85
    if weather == "clear": confidence += 5
    if event_name == "No Major Event": confidence += 3
    if distance > 0: confidence += 2
    confidence = min(95, confidence)
    
    # 2-hour forecast
    future_hour = (hour + 2) % 24
    future_speed = get_bengaluru_speed(future_hour, is_weekday, route_type)
    
    if not is_weekday and (8 <= future_hour <= 10 or 17 <= future_hour <= 19):
        future_multiplier = 1.35
    elif not is_weekday and (11 <= future_hour <= 16):
        future_multiplier = 1.15
    elif not is_weekday:
        future_multiplier = 1.10
    else:
        future_multiplier = 1.08
    
    if route_type == "orr":
        future_multiplier += 0.20
    
    future_multiplier = future_multiplier * weather_mult
    future_mins = round(base_duration_mins * future_multiplier)
    
    future_delay_percentage = ((future_mins - base_duration_mins) / base_duration_mins) * 100
    if future_delay_percentage > 50:      future_status = "CRITICAL"
    elif future_delay_percentage > 30:    future_status = "HIGH"
    elif future_delay_percentage > 15:    future_status = "MODERATE"
    elif future_delay_percentage > 5:     future_status = "LOW"
    else:                                 future_status = "CLEAR"
    
    # Generate contributing factors
    factors = []
    
    if not is_weekday and (8 <= hour <= 10):
        factors.append("Morning office entry rush")
    elif not is_weekday and (17 <= hour <= 19):
        factors.append("Evening office exit rush")
    
    if route_type == "orr":
        factors.append("Outer Ring Road corridor")
    
    if weather != "clear":
        factors.append(f"{weather.replace('_', ' ').title()} impact")

    # Calculate confidence
    confidence = 0.85
    if len(factors) > 0:
        confidence = min(0.95, confidence + 0.05)
    if weather == "clear":
        confidence = min(0.95, confidence + 0.03)

    # Build status message
    status_parts = [status]
    if not is_weekday:
        status_parts.append(f"{day_name} {now.strftime('%I:%M %p')}")
    else:
        status_parts.append(f"{day_name} {now.strftime('%I:%M %p')}")
    if factors:
        status_parts.append(f"Factors: {', '.join(factors[:3])}")
    status_message = " | ".join(status_parts)

    # ---------------- RESPONSE ----------------

    return {
        "weather": weather,
        "event": event_name,
        "traffic": status,
        "delay": delay_mins,
        "travel_time": adjusted_duration_mins,
        "source_coords": [coord1[0], coord1[1]],
        "destination_coords": [coord2[0], coord2[1]],
        "route_coords": route_coords,
        "distance_km": round(distance, 1),
        "avg_speed": avg_speed,
        "factors": factors,
        "confidence": confidence,
        "status": status_message,
        "day_type": "Weekend" if not is_weekday else "Weekday",
        "day_name": day_name,
        "route_type": route_type,
        "base_duration_mins": round(base_duration_mins),
        "adjusted_duration_mins": adjusted_duration_mins,
        "current_speed_kmh": avg_speed,
        "traffic_score": traffic_score,
        "forecast_2hr": {
            "predicted_mins": future_mins,
            "delay_mins": max(0, future_mins - base_duration_mins),
            "status": future_status,
            "speed_kmh": round((distance / future_mins) * 60, 1)
        }
    }

# ---------------- HOME ----------------

@app.get("/")
def home():

    return {
        "message": "Bengaluru Brain Running"
    }

# ---------------- API ----------------

@app.post("/predict-route")
def predict_route(req: RouteRequest):

    result = predict_traffic(
        req.source,
        req.destination
    )

    return result

# ---------------- MAIN ----------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )