from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
import asyncio
import json
import os
import math
import sqlite3
import requests
import uuid
import hashlib
import numpy as np
import pandas as pd
import openrouteservice
import networkx as nx
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass
from graph_builder import build_bengaluru_graph, get_nearest_node, get_route_geometry
from gnn_model import run_gnn
from routing_service import get_routing_service
from incident_service import get_incident_service
from route_comparison import get_route_comparison
from weather_logic import get_live_weather, get_weather_impact, classify_weather_impact
from location_data import BENGALURU_LOCATIONS as LOCATION_DB, get_all_locations
from ward_stress import generate_ward_stress_data, get_citywide_stress_summary, get_ward_stress_by_id
from it_shift_logic import get_next_shift_change, get_all_shift_timers
from real_gnn_service import get_route_traffic_signal, get_model_metrics
import integration_bridge
from data_status_service import get_traffic_data_status
import ward_registry_service
import citizen_registry  # Stage 1: citizen registration/alert-preferences (new, self-contained)
import citizen_otp       # Stage 1: dev-only OTP for the above (no real SMS provider)
def classify_status_from_delay_percentage(delay_percentage):
    if delay_percentage < 10:
        return "NORMAL"
    if delay_percentage < 25:
        return "MODERATE"
    if delay_percentage < 40:
        return "HIGH"
    return "CRITICAL"
def validate_prediction(prediction):
    required = ["predicted_speed_kmh", "base_duration_mins", "predicted_duration_mins", "delay_percentage"]
    if not isinstance(prediction, dict):
        return False
    if any(key not in prediction for key in required):
        return False
    predicted_speed = prediction.get("predicted_speed_kmh", 0)
    if predicted_speed <= 0 or predicted_speed > 120:
        return False
    base_duration = prediction.get("base_duration_mins", 0)
    predicted_duration = prediction.get("predicted_duration_mins", 0)
    if base_duration <= 0 or predicted_duration <= 0:
        return False
    if predicted_duration < base_duration * 0.8:
        return False
    if predicted_duration > base_duration * 2.5:
        return False
    delay_percentage = prediction.get("delay_percentage", 0)
    if delay_percentage < 0 or delay_percentage > 100:
        return False
    return True
BENGALURU_LOCATIONS = {name.lower(): [info["lat"], info["lon"]] for name, info in LOCATION_DB.items()}
BENGALURU_LOCATIONS.update({
    "new horizon college": [13.0120, 77.6350],  # Kasturinagar campus (corrected)
    "tin factory": [12.9456, 77.6123],
    "bellandur": [12.9259, 77.6676],
    "sarjapur": [12.9236, 77.6762],
    "bannerghatta": [12.8000, 77.5700],
    "jayadeva": [12.9250, 77.6000],
    "domlur": [12.9550, 77.6350],
    "old airport road": [12.9650, 77.6450],
    "majestic": [12.9767, 77.5713],
    "airport": [13.1986, 77.7066],
})
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
ORS_API_KEY = os.getenv("ORS_API_KEY") or os.getenv("OPENROUTESERVICE_API_KEY")
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY") or os.getenv("TRAFFIC_API_KEY")
OWM_API_KEY = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OWM_API_KEY")
class TrafficProvider:
    def get_live_traffic(self, route):
        return None
class TomTomTrafficProvider(TrafficProvider):
    def __init__(self, api_key=None):
        self.api_key = api_key or TOMTOM_API_KEY
    def get_live_traffic(self, route):
        if not self.api_key or not route.get("route_coords"):
            return None
        coords = route["route_coords"]
        if len(coords) < 2:
            return None
        try:
            samples = coords[:: max(1, len(coords) // 8)]
            query = ",".join(f"{lon},{lat}" for lat, lon in samples)
            url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/" \
                  "normal/json?point=" + query + f"&unit=KMPH&key={self.api_key}"
            response = requests.get(url, timeout=6)
            if response.status_code != 200:
                return None
            payload = response.json()
            segments = payload.get("flowSegmentData", [])
            if not isinstance(segments, list):
                segments = [payload.get("flowSegmentData")] if payload.get("flowSegmentData") else []
            points = []
            for idx, seg in enumerate(segments[:8]):
                try:
                    speed = float(seg.get("currentSpeed", 0.0))
                    free_speed = float(seg.get("freeFlowSpeed", max(speed, 35.0)))
                    congestion = max(0, min(100, int(round((1 - speed / max(free_speed, 1)) * 100))))
                    points.append({
                        "traffic_location": f"Route Point {idx + 1}",
                        "current_speed_kmh": round(speed, 1),
                        "free_flow_speed_kmh": round(free_speed, 1),
                        "congestion_percent": congestion,
                        "lat": samples[min(len(samples)-1, idx)][0],
                        "lon": samples[min(len(samples)-1, idx)][1],
                        "traffic_source": "LIVE",
                    })
                except Exception:
                    continue
            if points:
                return {
                    "current_speed_kmh": round(sum(p["current_speed_kmh"] for p in points) / max(1, len(points)), 1),
                    "free_flow_speed_kmh": round(sum(p["free_flow_speed_kmh"] for p in points) / max(1, len(points)), 1),
                    "congestion_ratio": max(0.0, min(1.0, sum((p["congestion_percent"] / 100.0) for p in points) / max(1, len(points)))),
                    "traffic_status": "LOW",
                    "traffic_points": points,
                    "traffic_source": "LIVE",
                }
        except Exception:
            return None
        return None
def normalize_place_name(name):
    text = (name or "").strip()
    aliases = {
        "mararthalli": "marathahalli",
        "marathahalli": "marathahalli",
        "new horizon college of engineering": "new horizon college",
        "new horizon college": "new horizon college",
        "new horizon": "new horizon college",
        "silkboard": "silk board",
        "silk board": "silk board",
        "tinfactory": "tin factory",
        "tin factory": "tin factory",
    }
    lowered = text.lower().strip()
    return aliases.get(lowered, lowered)
def geocode_location(location):
    text = normalize_place_name(location)
    # Same single source of truth as BENGALURU_LOCATIONS above — see that
    # dict's comment for why this used to be a separate, driftable copy.
    if text in BENGALURU_LOCATIONS:
        return BENGALURU_LOCATIONS[text]
    geolocator = Nominatim(user_agent="bengaluru_brain_v2", timeout=10)
    try:
        result = geolocator.geocode(f"{text}, Bengaluru, Karnataka, India")
        if result:
            return [result.latitude, result.longitude]
    except Exception:
        pass
    raise ValueError(f"Location not found: {location}")


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def compute_route_distance(route_coords):
    if len(route_coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(route_coords) - 1):
        lat1, lon1 = route_coords[i]
        lat2, lon2 = route_coords[i + 1]
        total += haversine_km(lat1, lon1, lat2, lon2)
    return total


def _get_osrm_route(src, dst):
    lat1, lon1 = src
    lat2, lon2 = dst
    url = (
        f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        "?overview=full&geometries=geojson&steps=true"
    )
    response = requests.get(url, timeout=12)
    response.raise_for_status()
    data = response.json()
    if not data.get("routes"):
        raise ValueError("Routing engine returned no route.")
    route = data["routes"][0]
    coords = route.get("geometry", {}).get("coordinates", [])
    route_coords = [[lat, lon] for lon, lat in coords]
    distance_m = float(route.get("distance", 0.0))
    duration_s = float(route.get("duration", 0.0))
    road_names = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            name = step.get("name")
            if name and name not in road_names:
                road_names.append(name)
    return {"route_coords": route_coords, "distance_m": distance_m, "duration_s": duration_s, "road_names": road_names}


def _get_ors_route(src, dst):
    if not ORS_API_KEY:
        return None
    try:
        client = openrouteservice.Client(key=ORS_API_KEY)
        route = client.directions(
            coordinates=[[src[1], src[0]], [dst[1], dst[0]]],
            profile="driving-car",
            format="geojson",
            validate=False,
        )
        feature = route["features"][0]
        geom = feature["geometry"]["coordinates"]
        route_coords = [[lat, lon] for lon, lat in geom]
        distance_m = float(feature["properties"]["summary"]["distance"])
        duration_s = float(feature["properties"]["summary"]["duration"])
        road_names = []
        for leg in feature.get("properties", {}).get("segments", []):
            for step in leg.get("steps", []):
                name = step.get("name")
                if name and name not in road_names:
                    road_names.append(name)
        return {"route_coords": route_coords, "distance_m": distance_m, "duration_s": duration_s, "road_names": road_names}
    except Exception:
        return None


def get_route_details(source, destination):
    source_coords = geocode_location(source)
    destination_coords = geocode_location(destination)
    for builder in [_get_ors_route, _get_osrm_route]:
        try:
            route = builder(tuple(source_coords), tuple(destination_coords))
            if route:
                route_coords = route["route_coords"]
                if not route_coords:
                    continue
                distance_km = route["distance_m"] / 1000.0 if route["distance_m"] else compute_route_distance(route_coords)
                duration_min = route["duration_s"] / 60.0 if route["duration_s"] else max(1.0, (distance_km / 30.0) * 60.0)
                road_names = route.get("road_names") or []
                return {
                    "source_coords": source_coords,
                    "destination_coords": destination_coords,
                    "route_coords": route_coords,
                    "distance_km": round(distance_km, 2),
                    "duration_min": duration_min,
                    "road_names": road_names,
                    "routing_engine": "ORS" if builder is _get_ors_route else "OSRM",
                }
        except Exception:
            continue
    raise ValueError(f"Unable to route from {source} to {destination}.")
def get_weather_for_route(lat, lon):
    api_key = OWM_API_KEY
    if not api_key:
        return {
            "condition": "clear",
            "temperature_c": 28.0,
            "humidity": 60,
            "rain": 0,
            "wind_speed": 8.0,
            "source": "ESTIMATED",
        }
    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        rain = float(data.get("rain", {}).get("1h", data.get("rain", {}).get("3h", 0.0)))
        return {
            "condition": weather.get("main", "Clear"),
            "temperature_c": float(main.get("temp", 28.0)),
            "humidity": int(main.get("humidity", 60)),
            "rain": rain,
            "wind_speed": float(data.get("wind", {}).get("speed", 8.0)),
            "source": "LIVE",
        }
    except Exception:
        return {
            "condition": "clear",
            "temperature_c": 28.0,
            "humidity": 60,
            "rain": 0,
            "wind_speed": 8.0,
            "source": "ESTIMATED",
        }
def classify_congestion_ratio(ratio):
    if ratio >= 0.75:
        return "SEVERE"
    if ratio >= 0.55:
        return "HIGH"
    if ratio >= 0.30:
        return "MODERATE"
    return "LOW"
def build_model_prediction(distance_km, current_speed_kmh, weather_info):
    weather_norm = {"Clear": 0.0, "Clouds": 0.15, "Rain": 0.35, "Drizzle": 0.25, "Thunderstorm": 0.55, "Mist": 0.2, "Fog": 0.25}
    weather_key = str(weather_info.get("condition", "Clear")).title()
    weather_factor = weather_norm.get(weather_key, 0.0)
    road_density = min(1.0, (distance_km / 25.0))
    base_features = [
        22000.0,
        1.20,
        50.0,
        70.0,
        1.0,
        120.0,
        45.0,
        75.0,
        35.0,
        80.0,
        max(distance_km * 1000.0, 100.0),
        4.0,
    ]
    normalized = [
        (base_features[0] / 50000.0),
        (base_features[1] / 2.0),
        (base_features[2] / 100.0),
        (base_features[3] / 100.0),
        (base_features[4] / 10.0),
        (base_features[5] / 200.0),
        (base_features[6] / 100.0),
        (base_features[7] / 100.0),
        (base_features[8] / 100.0),
        (base_features[9] / 200.0),
        min(1.0, base_features[10] / 2000.0),
        min(1.0, base_features[11] / 8.0),
    ]
    model_score = 0.55 + (1.0 - min(1.0, current_speed_kmh / 80.0)) * 0.30 + weather_factor * 0.15 + road_density * 0.10
    predicted_speed = max(10.0, min(80.0, current_speed_kmh * (0.92 + 0.18 * (1.0 - weather_factor))))
    return float(predicted_speed), float(max(0.25, min(0.9, model_score)))
def _build_traffic_points(route_coords, traffic_data=None, traffic_source="MODEL/HISTORICAL"):
    if traffic_data and isinstance(traffic_data.get("traffic_points"), list) and traffic_data["traffic_points"]:
        return traffic_data["traffic_points"]
    points = []
    if not route_coords:
        return points
    sample_step = max(1, len(route_coords) // 8)
    for idx, (lat, lon) in enumerate(route_coords[::sample_step][:8], start=1):
        speed = 30.0 + (idx % 5) * 2.5
        free_speed = 48.0 + (idx % 3) * 4.0
        ratio = max(0.0, min(1.0, 1 - (speed / max(1.0, free_speed))))
        points.append({
            "traffic_location": f"Estimated Traffic Point {idx}",
            "current_speed_kmh": round(speed, 1),
            "free_flow_speed_kmh": round(free_speed, 1),
            "congestion_percent": int(round(ratio * 100)),
            "lat": lat,
            "lon": lon,
            "traffic_source": traffic_source,
        })
    return points
def _load_gnn_model():
    checkpoint_path = os.path.join(os.path.dirname(__file__), "..", "models", "traffic_model_v2.pth")
    checkpoint_path = os.path.abspath(checkpoint_path)
    if not os.path.exists(checkpoint_path):
        return None
    try:
        import torch
        from torch_geometric.nn import GCNConv
        from torch.nn import Module, Linear, ReLU
        class TrafficGNN12(Module):
            def __init__(self, input_dim=12):
                super().__init__()
                self.conv1 = GCNConv(input_dim, 64)
                self.conv2 = GCNConv(64, 32)
                self.conv3 = GCNConv(32, 16)
                self.output = Linear(16, 1)
            def forward(self, x, edge_index):
                x = self.conv1(x, edge_index)
                x = ReLU()(x)
                x = self.conv2(x, edge_index)
                x = ReLU()(x)
                x = self.conv3(x, edge_index)
                x = ReLU()(x)
                x = self.output(x)
                return x.squeeze(-1)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model = TrafficGNN12(input_dim=checkpoint.get("input_dim", 12))
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        mean = checkpoint.get("feature_mean", {})
        std = checkpoint.get("feature_std", {})
        return {"model": model, "feature_mean": mean, "feature_std": std, "metrics": checkpoint.get("test_metrics", {})}
    except Exception:
        return None
MODEL_CACHE = _load_gnn_model()
class RouteRequest(BaseModel):

    source: str
    destination: str
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
WEATHER_MULTIPLIERS = {
    "clear": {"delay_multiplier": 1.00, "speed_reduction": 0.0},
    "cloudy": {"delay_multiplier": 1.05, "speed_reduction": 0.03},
    "light_rain": {"delay_multiplier": 1.10, "speed_reduction": 0.08},
    "rain": {"delay_multiplier": 1.15, "speed_reduction": 0.12},
    "heavy_rain": {"delay_multiplier": 1.20, "speed_reduction": 0.18},
    "storm": {"delay_multiplier": 1.25, "speed_reduction": 0.22},
    "fog": {"delay_multiplier": 1.12, "speed_reduction": 0.10}
}
def get_weather_context():
    """Fetch live weather context and return a richer signal for prediction."""
    weather_type = "clear"
    temp_c = 28.0
    humidity = 45.0
    try:
        import requests
        from realtime_data import OWM_API_KEY, BENGALURU_LAT, BENGALURU_LON

        if OWM_API_KEY == "your_free_key_from_openweathermap.org":
            return {
                "type": weather_type,
                "temp_c": temp_c,
                "humidity": humidity,
                "weather_score": 0.0,
                "weather_multiplier": 1.0,
            }
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={BENGALURU_LAT}&lon={BENGALURU_LON}&appid={OWM_API_KEY}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            weather_main = data["weather"][0]["main"].lower()
            temp_c = round(data.get("main", {}).get("temp", 298.0) - 273.15, 1)
            humidity = float(data.get("main", {}).get("humidity", 45.0))
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
            weather_type = weather_map.get(weather_main, "clear")
    except Exception as e:
        print(f"Weather API failed: {e}")
    weather_data = WEATHER_MULTIPLIERS.get(weather_type, WEATHER_MULTIPLIERS["clear"])
    weather_score = 0.0
    if weather_type == "heavy_rain":
        weather_score = 0.85
    elif weather_type == "rain":
        weather_score = 0.65
    elif weather_type == "fog":
        weather_score = 0.45
    elif weather_type == "light_rain":
        weather_score = 0.35
    elif weather_type == "cloudy":
        weather_score = 0.15
    if temp_c > 35:
        weather_score += 0.08
    if humidity > 80:
        weather_score += 0.08
    return {
        "type": weather_type,
        "temp_c": temp_c,
        "humidity": humidity,
        "weather_score": round(min(1.0, weather_score), 2),
        "weather_multiplier": weather_data["delay_multiplier"],
    }
def get_weather():
    """Backward-compatible helper returning weather category."""
    return get_weather_context()["type"]
EVENT_LOCATIONS = {
    "chinnaswamy stadium": {"event": "Cricket Match", "event_type": "cricket", "congestion_multiplier": 2.4},
    "mg road": {"event": "Concert", "event_type": "concert", "congestion_multiplier": 1.9},
    "palace grounds": {"event": "Festival", "event_type": "festival", "congestion_multiplier": 1.7},
    "cubbon park": {"event": "Public Gathering", "event_type": "festival", "congestion_multiplier": 1.5},
    "forum mall": {"event": "Weekend Mall Traffic", "event_type": "festival", "congestion_multiplier": 1.5},
    "phoenix mall": {"event": "Weekend Mall Traffic", "event_type": "festival", "congestion_multiplier": 1.5},
    "garuda mall": {"event": "Weekend Mall Traffic", "event_type": "festival", "congestion_multiplier": 1.4},
    "vidhana soudha": {"event": "Political Rally", "event_type": "political_rally", "congestion_multiplier": 2.0},
    "brigade road": {"event": "Concert", "event_type": "concert", "congestion_multiplier": 1.8},
}
def get_event_status(source, destination, hour, is_weekend):
    event_name = "No Major Event"
    event_multiplier = 1.0
    event_type = "none"
    event_score = 0.0
    route_text = f"{source.lower()} {destination.lower()}"
    for location, event_data in EVENT_LOCATIONS.items():
        if location.lower() in route_text:
            active_window = is_weekend and (18 <= hour <= 22) or (not is_weekend and (18 <= hour <= 21))
            if active_window:
                event_name = event_data["event"]
                event_multiplier = event_data["congestion_multiplier"]
                event_type = event_data["event_type"]
                event_score = 0.45 if event_type in {"festival", "concert"} else 0.6
    if event_name != "No Major Event" and event_score == 0.0:
        event_score = 0.3
    return event_name, event_multiplier, event_type, event_score
ROAD_CONDITIONS = {
    "outer ring road": {"condition": "Under Construction", "delay_multiplier": 1.16},
    "sarjapur road": {"condition": "Diversion", "delay_multiplier": 1.14},
    "hosur road": {"condition": "Road Closed", "delay_multiplier": 1.20},
    "bellary road": {"condition": "Diversion", "delay_multiplier": 1.12},
    "whitefield": {"condition": "Diversion", "delay_multiplier": 1.12},
    "electronic city": {"condition": "Under Construction", "delay_multiplier": 1.10},
}
FLOOD_PRONE_ROADS = {
    "outer ring road": 1.12,
    "marathahalli": 1.10,
    "bellandur": 1.11,
    "koramangala": 1.08,
    "silk board": 1.09,
}
def get_road_context(source, destination):
    route_text = f"{source.lower()} {destination.lower()}"
    conditions = []
    condition_multiplier = 1.0
    flood_score = 0.0
    flood_multiplier = 1.0
    for road_name, road_data in ROAD_CONDITIONS.items():
        if road_name in route_text:
            conditions.append(road_data["condition"])
            condition_multiplier *= road_data["delay_multiplier"]
    for road_name, multiplier in FLOOD_PRONE_ROADS.items():
        if road_name in route_text:
            flood_score = 0.55
            flood_multiplier = multiplier
    return {
        "conditions": conditions,
        "condition_multiplier": condition_multiplier,
        "flood_score": flood_score,
        "flood_multiplier": flood_multiplier,
    }
def get_coordinates(location):
    """Get coordinates for a location using custom dictionary first, then geocoder"""
    location_lower = location.lower().strip()
    
    # Check custom dictionary FIRST
    for key, coords in BENGALURU_LOCATIONS.items():
        if key in location_lower or location_lower in key:
            print(f"[GEOCODER] Using custom dictionary for '{location}' -> {key}")
            print(f"[GEOCODER] Coordinates: {coords}")
            return coords
    geolocator = Nominatim(user_agent="bengaluru_traffic")
    try:
        result = geolocator.geocode(f"{location}, Bengaluru, Karnataka, India")
        if result:
            print(f"[GEOCODER] Geocoded '{location}' to: {result.address}")
            print(f"[GEOCODER] Coordinates: [{result.latitude}, {result.longitude}]")
            return [result.latitude, result.longitude]
    except Exception as e:
        print(f"[GEOCODER] Geocoding failed for {location}: {e}")
    return None
def get_it_park_impact(source, destination, hour):
    it_impact = 1.0
    for park_name, park_data in IT_PARKS_DATA.items():
        if (park_name.lower() in source.lower() or 
            park_name.lower() in destination.lower() or
            any(corridor.lower() in source.lower() or corridor.lower() in destination.lower() 
                for corridor in park_data["corridors"])):
            if 8 <= hour <= 10:
                it_impact *= 1.20
            elif 10 <= hour <= 11:
                it_impact *= 1.15
            elif 17 <= hour <= 19:
                it_impact *= 1.25
            elif 19 <= hour <= 20:
                it_impact *= 1.20
            elif 7 <= hour <= 8 or 11 <= hour <= 12 or 16 <= hour <= 17 or 20 <= hour <= 21:
                it_impact *= 1.10
            employee_factor = 1 + min(0.10, park_data["employees"] / 200000)
            it_impact *= employee_factor
    return it_impact
SPEED_TABLE = {
    (True, range(0,  6)):  40,  # midnight - 5am: fast
    (True, range(6,  7)):  30,  # 6am: building up
    (True, range(7,  8)):  20,  # 7am: getting bad
    (True, range(8, 11)):  15,  # 8-11am: MORNING PEAK (12-18 km/h)
    (True, range(11,17)):  24,  # 11am-5pm: afternoon (20-28 km/h)
    (True, range(17,22)):  13,  # 5-10pm: EVENING PEAK (10-16 km/h)
    (True, range(22,24)):  35,  # 10pm+: late night (35-45 km/h)
    (False, range(0,  8)):  38,  # night/early: fast
    (False, range(8, 12)):  30,  # 8am-12pm: light
    (False, range(12,18)):  28,  # afternoon: moderate
    (False, range(18,21)):  25,  # evening: some traffic
    (False, range(21,24)):  35,  # night: good
}
def get_bengaluru_speed(hour, is_weekday, route_type):
    base_speed = 25  # default
    for (weekday, hours), speed in SPEED_TABLE.items():
        if weekday == is_weekday and hour in hours:
            base_speed = speed
            break
    if route_type == "orr":
        base_speed = base_speed * 0.75
    elif route_type == "clear":
        base_speed = base_speed * 1.15
    return max(10, min(50, base_speed))
def detect_route_type(source, destination):
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
    for zone, data in BENGALURU_CONGESTION_ZONES.items():
        if zone in location_key:
            if is_weekend:
                return data["base_multiplier"]
            elif 8 <= hour <= 10 or 17 <= hour <= 19:
                return data["peak_multiplier"]
            else:
                return data["base_multiplier"]
    return BENGALURU_CONGESTION_ZONES["default"]["base_multiplier"]
def calculate_fuel_and_co2(distance_km, vehicle_mileage_kmpl=14.0):
    fuel_liters = max(0.0, distance_km / vehicle_mileage_kmpl)
    co2_kg = fuel_liters * 2.31
    return round(fuel_liters, 2), round(co2_kg, 2)
def select_best_route(route_options):
    if not route_options:
        return None
    def score(option):
        fastest = option.get("travel_time", 999)
        shortest = option.get("distance_km", 999)
        least_congested = option.get("congestion_score", 100)
        return (fastest * 0.5) + (shortest * 0.3) + (least_congested * 0.2)
    return min(route_options, key=score)
def log_prediction(payload):
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "prediction_log.jsonl")
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    db_path = os.path.join("logs", "predictions.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                destination TEXT,
                route_selected TEXT,
                weather_score REAL,
                it_score REAL,
                event_score REAL,
                flood_score REAL,
                congestion_score REAL,
                final_travel_time REAL,
                prediction_confidence REAL,
                timestamp TEXT
            )
            """
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(predictions)")]
        if "base_time" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN base_time REAL")
        if "predicted_speed" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN predicted_speed REAL")
        if "predicted_delay" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN predicted_delay REAL")
        if "status" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN status TEXT")
        if "prediction_confidence" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN prediction_confidence REAL")
        conn.execute(
            """
            INSERT INTO predictions (
                source, destination, route_selected, weather_score, it_score,
                event_score, flood_score, congestion_score, final_travel_time,
                base_time, predicted_speed, predicted_delay, status,
                prediction_confidence, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("source"),
                payload.get("destination"),
                payload.get("route_selected"),
                payload.get("weather_score"),
                payload.get("it_score"),
                payload.get("event_score"),
                payload.get("flood_score"),
                payload.get("congestion_score"),
                payload.get("final_travel_time"),
                payload.get("base_time"),
                payload.get("predicted_speed"),
                payload.get("predicted_delay"),
                payload.get("status"),
                payload.get("prediction_confidence"),
                payload.get("timestamp"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
def _load_historical_graph_data():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    traffic_nodes_path = os.path.join(base_dir, "traffic_nodes.csv")
    edges_path = os.path.join(base_dir, "edges.csv")
    node_mapping_path = os.path.join(base_dir, "node_mapping.pkl")
    historical_nodes = None
    historical_edges = None
    node_mapping = None
    if os.path.exists(traffic_nodes_path):
        historical_nodes = pd.read_csv(traffic_nodes_path)
    if os.path.exists(edges_path):
        historical_edges = pd.read_csv(edges_path)
    if os.path.exists(node_mapping_path):
        try:
            import pickle
            with open(node_mapping_path, "rb") as handle:
                node_mapping = pickle.load(handle)
        except Exception:
            node_mapping = None
    return historical_nodes, historical_edges, node_mapping
def _get_historical_speed_for_route(historical_nodes, source_name, destination_name, graph, src_node, dst_node):
    if historical_nodes is None or src_node is None or dst_node is None:
        return None, None
    source_key = source_name.lower().strip()
    destination_key = destination_name.lower().strip()
    route_text = f"{source_key} {destination_key}"
    route_matches = []
    for _, row in historical_nodes.iterrows():
        row_text = str(row.get("node_id", "")).lower()
        if route_text and row_text:
            continue
    return None, None
def predict_traffic(source, destination):
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()
    is_weekday = weekday < 5  # Mon=0...Sun=6
    day_name = now.strftime("%A")

    coord1 = get_coordinates(source)
    coord2 = get_coordinates(destination)

    # Log location resolution
    print("=" * 60)
    print("LOCATION PIPELINE LOG")
    print("=" * 60)
    print(f"SOURCE TEXT: {source}")
    print(f"SOURCE LATITUDE: {coord1[0] if coord1 else 'N/A'}")
    print(f"SOURCE LONGITUDE: {coord1[1] if coord1 else 'N/A'}")
    print(f"DESTINATION TEXT: {destination}")
    print(f"DESTINATION LATITUDE: {coord2[0] if coord2 else 'N/A'}")
    print(f"DESTINATION LONGITUDE: {coord2[1] if coord2 else 'N/A'}")
    print("=" * 60)

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

    route_coords = []
    distance = 0.0
    base_duration_mins = 0.0
    road_names = []

    print(f"OpenRouteService Distance Request: {source} -> {destination}")

    try:
        # First try the project's existing route-details function
        route_data = get_route_details(source, destination)

        route_coords = route_data["route_coords"]
        distance = float(route_data["distance_km"])
        base_duration_mins = float(route_data["duration_min"])
        road_names = route_data.get("road_names", [])

        print(
            f"ROUTE GEOMETRY: "
            f"{route_data.get('routing_engine', 'UNKNOWN')} "
            f"{len(route_coords)} points, "
            f"{distance:.2f} km"
        )

    except Exception as routing_error:
        print(f"Routing failed using route_details: {routing_error}")
        try:
            ors_client = (
                openrouteservice.Client(key=ORS_API_KEY)
                if ORS_API_KEY
                else None
            )
            if ors_client is None:
                raise ValueError("ORS API key missing")
            route = ors_client.directions(
                coordinates=[
                    [coord1[1], coord1[0]],
                    [coord2[1], coord2[0]]
                ],
                profile="driving-car",
                format="geojson"
            )
            feature = route["features"][0]
            geometry = feature["geometry"]["coordinates"]
            route_coords = [
                [lat, lon]
                for lon, lat in geometry
            ]
            properties = feature["properties"]
            try:
                distance_m = properties["segments"][0]["distance"]
            except (KeyError, IndexError):
                distance_m = properties["summary"]["distance"]
            distance = float(distance_m) / 1000.0
            try:
                duration_s = properties["segments"][0]["duration"]
            except (KeyError, IndexError):
                duration_s = properties["summary"]["duration"]

            base_duration_mins = float(duration_s) / 60.0
            lat1 = math.radians(coord1[0])
            lon1 = math.radians(coord1[1])
            lat2 = math.radians(coord2[0])
            lon2 = math.radians(coord2[1])

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1)
                * math.cos(lat2)
                * math.sin(dlon / 2) ** 2
            )

            c = 2 * math.asin(math.sqrt(a))

            straight_line_distance = 6371.0 * c

            if (
                straight_line_distance > 0
                and distance > straight_line_distance * 1.6
            ):
                print(
                    f"WARNING: ORS distance {distance:.2f} km "
                    f"is unusually large compared with straight-line "
                    f"distance {straight_line_distance:.2f} km."
                )

                distance = straight_line_distance * 1.3

                base_duration_mins = (
                    distance / 30.0
                ) * 60.0

            print(f"ORS DISTANCE: {distance:.2f} km")
            print(
                f"ORS BASE DURATION: "
                f"{base_duration_mins:.2f} mins"
            )
            print(
                f"ORS ROUTE POINTS: "
                f"{len(route_coords)}"
            )
            print("=" * 60)

        except Exception as ors_error:
            print(
                f"ORS routing fallback failed: "
                f"{ors_error}"
            )

            # ---------------- FINAL DISTANCE FALLBACK ----------------

            if distance <= 0:

                lat1 = math.radians(coord1[0])
                lon1 = math.radians(coord1[1])
                lat2 = math.radians(coord2[0])
                lon2 = math.radians(coord2[1])

                dlat = lat2 - lat1
                dlon = lon2 - lon1

                a = (
                    math.sin(dlat / 2) ** 2
                    + math.cos(lat1)
                    * math.cos(lat2)
                    * math.sin(dlon / 2) ** 2
                )

                c = 2 * math.asin(math.sqrt(a))

                distance = 6371.0 * c

                base_duration_mins = (
                    distance / 30.0
                ) * 60.0

                print(
                    f"FINAL DISTANCE FALLBACK: "
                    f"{distance:.2f} km"
                )

                print(
                    f"FINAL BASE DURATION: "
                    f"{base_duration_mins:.2f} mins"
                )

    # ---------------- USE TRAINED GNN V2 MODEL ----------------
    # Initialize variables that might not be set in fallback
    route_type = detect_route_type(source, destination)
    weather_context = get_weather_context()
    weather = weather_context["type"]
    weather_mult = weather_context["weather_multiplier"]
    weather_score = weather_context["weather_score"]
    it_impact = get_it_park_impact(source, destination, hour)
    event_name, event_multiplier, event_type, event_score = get_event_status(source, destination, hour, is_weekday)
    road_context = get_road_context(source, destination)
    feature_importance = []
    
    try:
        from traffic_predictor_v2 import predict_route_v2
        v2_result = predict_route_v2(source, destination)
        
        # Use v2 results
        distance = v2_result['distance_km']
        predicted_duration_mins = v2_result['predicted_mins']
        base_duration_mins = v2_result['free_flow_mins']
        delay_mins = v2_result['delay_mins']
        delay_percentage = v2_result['delay_percentage']
        avg_speed = v2_result['avg_speed_kmh']
        status = v2_result['status']
        traffic_score = v2_result['traffic_score']
        confidence = v2_result['confidence']
        route_coords = v2_result['route_coords']
        
        print(f"V2 Prediction: {source} -> {destination}")
        print(f"Distance: {distance} km")
        print(f"Predicted time: {predicted_duration_mins} mins")
        print(f"Delay: {delay_mins} mins ({delay_percentage}%)")
        print(f"Status: {status}")
        print(f"Model: {v2_result['model_info']}")
        
    except Exception as e:
        print(f"V2 prediction failed, falling back to ORS: {e}")
        
        # Fallback to ORS-based prediction
        current_speed = get_bengaluru_speed(hour, is_weekday, route_type)
        
        # Simple multiplier-based prediction
        base_multiplier = 1.0
        if is_weekday:
            if 8 <= hour <= 10 or 17 <= hour <= 19:
                base_multiplier = 1.4
            elif 11 <= hour <= 16:
                base_multiplier = 1.2
        else:
            if 8 <= hour <= 10 or 17 <= hour <= 19:
                base_multiplier = 1.3
        
        combined_multiplier = base_multiplier * weather_mult * it_impact * event_multiplier
        combined_multiplier = min(2.0, combined_multiplier)
        
        predicted_duration_mins = base_duration_mins * combined_multiplier
        delay_mins = max(0, predicted_duration_mins - base_duration_mins)
        delay_percentage = (delay_mins / max(1.0, base_duration_mins)) * 100.0
        avg_speed = (distance / max(0.1, predicted_duration_mins)) * 60.0
        status = classify_status_from_delay_percentage(delay_percentage)
        traffic_score = int(delay_percentage)
        confidence = 0.5

    future_mins = predicted_duration_mins  # Same as current for daily data
    future_delay_percentage = delay_percentage
    future_status = status
    
    adjusted_duration_mins = int(round(predicted_duration_mins))

    factors = []
    if not is_weekday and (8 <= hour <= 10):
        factors.append("Morning office entry rush")
    elif not is_weekday and (17 <= hour <= 19):
        factors.append("Evening office exit rush")
    if route_type == "orr":
        factors.append("Outer Ring Road corridor")
    if weather != "clear":
        factors.append(f"{weather.replace('_', ' ').title()} impact")
    if road_context["conditions"]:
        factors.append("Road condition impact")
    if road_context["flood_score"] > 0:
        factors.append("Flood-prone segment")
    if event_name != "No Major Event":
        factors.append(event_name)
    if it_impact > 1.1:
        factors.append("IT corridor congestion")

    if feature_importance:
        explainable_factors = [
            (name, score) for name, score in feature_importance[:5]
        ]
    else:
        explainable_factors = [
            ("Historical Pattern", max(0.1, min(0.95, 0.35 + (traffic_score / 100) * 0.15))),
            ("Peak Hour", max(0.1, min(0.95, 0.2 + (1 if (8 <= hour <= 10 or 17 <= hour <= 19) else 0) * 0.2))),
            ("Weather", max(0.05, min(0.9, weather_score * 0.8))),
            ("IT Corridor", max(0.05, min(0.9, (it_impact - 1.0) * 0.6))),
            ("Road Capacity", max(0.05, min(0.9, 0.15 + (traffic_score / 100) * 0.15))),
        ]
    explainable_factors = sorted(explainable_factors, key=lambda item: item[1], reverse=True)
    factor_summary = [f"{name}: {int(round(score * 100))}%" for name, score in explainable_factors[:5]]
    factors = factor_summary + factors

    status_parts = [status]
    status_parts.append(f"{day_name} {now.strftime('%I:%M %p')}")
    if factors:
        status_parts.append(f"Factors: {', '.join(factors[:3])}")
    status_message = " | ".join(status_parts)

    fuel_used_l, co2_kg = calculate_fuel_and_co2(distance)
    route_options = [
        {
            "name": "Fastest",
            "travel_time": adjusted_duration_mins,
        "predicted_travel_time": adjusted_duration_mins,
        "current_travel_time": adjusted_duration_mins,
        "base_travel_time": round(base_duration_mins),
        "predicted_mins": adjusted_duration_mins,
        "delay_mins": delay_mins,
        "delay_min": delay_mins,
        "avg_speed_kmh": avg_speed,
            "distance_km": round(distance, 1),
            "congestion_score": traffic_score,
        },
        {
            "name": "Shortest",
            "travel_time": max(adjusted_duration_mins, round(base_duration_mins * 1.02)),
            "distance_km": max(round(distance, 1) - 0.8, 0.5),
            "congestion_score": max(traffic_score - 8, 0),
        },
        {
            "name": "Least Congested",
            "travel_time": max(adjusted_duration_mins, round(base_duration_mins * 1.05)),
            "distance_km": round(distance, 1),
            "congestion_score": max(traffic_score - 12, 0),
        },
    ]
    best_route = select_best_route(route_options)
    route_label = best_route["name"] if best_route else "Fastest"

    traffic_points = _build_traffic_points(
        route_coords,
        traffic_data={"traffic_points": []},
        traffic_source="LIVE" if ORS_API_KEY else "MODEL/HISTORICAL",
    )

    try:
        real_gnn_signal = get_route_traffic_signal(route_coords, hour, not is_weekday)
    except Exception as e:
        real_gnn_signal = {"covered": False, "reason": f"real GNN lookup failed: {e}", "source": "REAL_GNN_V1"}

    response = {
        "weather": weather,
        "event": event_name,
        "traffic": status,
        "traffic_source": "LIVE" if ORS_API_KEY else "MODEL/HISTORICAL",
        "real_gnn_signal": real_gnn_signal,
        "delay": delay_mins,
        "travel_time": adjusted_duration_mins,
        "predicted_travel_time": adjusted_duration_mins,
        "current_travel_time": adjusted_duration_mins,
        "base_travel_time": round(base_duration_mins),
        "predicted_mins": adjusted_duration_mins,
        "delay_mins": delay_mins,
        "delay_min": delay_mins,
        "avg_speed_kmh": avg_speed,
        "source_coords": [coord1[0], coord1[1]],
        "destination_coords": [coord2[0], coord2[1]],
        "route_coords": route_coords,
        "traffic_points": traffic_points,
        "distance_km": round(distance, 1),
        "avg_speed": avg_speed,
        "factors": factors,
        "confidence": round(confidence, 2),
        "status": status_message,
        "day_type": "Weekend" if not is_weekday else "Weekday",
        "day_name": day_name,
        "route_type": route_type,
        "base_duration_mins": round(base_duration_mins),
        "adjusted_duration_mins": adjusted_duration_mins,
        "current_speed_kmh": avg_speed,
        "traffic_score": traffic_score,
        "fuel_used_liters": fuel_used_l,
        "co2_kg": co2_kg,
        "route_selected": route_label,
        "weather_score": weather_score,
        "it_score": round(it_impact - 1.0, 2),
        "event_score": round(event_score, 2),
        "flood_score": round(road_context["flood_score"], 2),
        "congestion_score": round(traffic_score / 100, 2),
        "forecast_2hr": {
            "predicted_mins": future_mins,
            "delay_mins": max(0, future_mins - base_duration_mins),
            "status": future_status,
            "speed_kmh": round((distance / max(1, future_mins)) * 60, 1)
        }
    }

    log_prediction({
        "source": source,
        "destination": destination,
        "route_selected": response["route_selected"],
        "weather_score": response["weather_score"],
        "it_score": response["it_score"],
        "event_score": response["event_score"],
        "flood_score": response["flood_score"],
        "congestion_score": response["congestion_score"],
        "final_travel_time": response["travel_time"],
        "base_time": response["base_duration_mins"],
        "predicted_speed": response["avg_speed"],
        "predicted_delay": response["delay"],
        "status": response["traffic"],
        "prediction_confidence": response["confidence"],
        "timestamp": now.isoformat(),
    })

    return response
@app.get("/")
def home():

    return {
        "message": "Bengaluru Brain Running",
        "status": "ACTIVE",
        "endpoints": [
            "/predict-route", "/api/predict-enhanced",
            "/api/locations", "/api/ward-stress", "/api/incidents",
            "/api/shift-timers", "/api/weather", "/api/city-summary",
            "/api/health",
        ],
        "timestamp": datetime.now().isoformat(),
    }
@app.get("/api/reverse-geocode")
def api_reverse_geocode(lat: float = Query(...), lon: float = Query(...)):
    nearest_name, nearest_dist = None, None
    for name, info in LOCATION_DB.items():
        d = haversine_km(lat, lon, info["lat"], info["lon"])
        if nearest_dist is None or d < nearest_dist:
            nearest_name, nearest_dist = name, d

    reverse_result = None
    usable_address = None
    reverse_error = None
    try:
        geolocator = Nominatim(user_agent="bengaluru_brain_v2", timeout=10)
        result = geolocator.reverse((lat, lon), exactly_one=True, language="en")
        if result:
            reverse_result = result.address
            comp = result.raw.get("address", {})
            road = comp.get("road")
            suburb = comp.get("suburb") or comp.get("neighbourhood") or comp.get("city_district")
            if road and suburb:
                usable_address = f"{road}, {suburb}, Bengaluru"
            elif suburb:
                usable_address = f"{suburb}, Bengaluru"
            elif road:
                usable_address = f"{road}, Bengaluru"
    except Exception as e:
        reverse_error = str(e)

    return {
        "lat": lat,
        "lon": lon,
        "reverse_geocoded_address": reverse_result,
        "usable_address": usable_address,
        "reverse_geocode_error": reverse_error,
        "nearest_known_location": nearest_name,
        "nearest_known_location_distance_km": round(nearest_dist, 3) if nearest_dist is not None else None,
    }
@app.get("/api/locations")
def api_get_locations():
    try:
        return [
            {"name": name, "lat": info["lat"], "lon": info["lon"],
             "ward": info["ward"], "canonical_ward_id": info["canonical_ward_id"],
             "canonical_ward_name": info["canonical_ward_name"],
             "legacy_ward_id": info["legacy_ward_id"], "it_zone": info["it_zone"]}
            for name, info in LOCATION_DB.items()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get locations: {str(e)}")
@app.get("/api/ward-stress")
def api_get_ward_stress():
    try:
        return {
            "data_source": "SIMULATED",
            "wards": generate_ward_stress_data(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ward stress data: {str(e)}")
@app.get("/api/shift-timers")
def api_get_shift_timers():
    """IT park shift-change countdowns, computed from the static shift table
    in it_shift_logic.py (not a live feed, but deterministic real-time-of-day math)."""
    try:
        next_park, minutes_until, is_approaching = get_next_shift_change()
        return {
            "shift_timers": [
                {"park": name, "minutes_until": mins, "status": status}
                for name, mins, status in get_all_shift_timers()
            ],
            "next_shift_change": {
                "park": next_park,
                "minutes_until": minutes_until,
                "is_approaching": is_approaching,
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get shift timers: {str(e)}")
@app.get("/api/weather")
def api_get_weather():
    """Current Bengaluru weather via weather_logic.get_live_weather() (real
    OpenWeatherMap call; falls back to an explicitly-labeled estimate if no
    API key/network)."""
    try:
        weather_data = get_live_weather()
        return {"weather": weather_data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get weather data: {str(e)}")
@app.get("/api/city-summary")
def api_get_city_summary():
    """Citywide traffic summary aggregated from the simulated ward-stress data."""
    try:
        return {
            "data_source": "SIMULATED",
            "city_summary": get_citywide_stress_summary(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get city summary: {str(e)}")
@app.get("/api/usi/areas")
def api_usi_areas():
    """Areas with a real (verified, not invented) traffic+waste name overlap
    that the USI engine can score. See integration/README.md."""
    return integration_bridge.get_usi_areas()
@app.get("/api/usi/{area_name}")
def api_usi_for_area(area_name: str):
    result = integration_bridge.get_usi_for_area(area_name)
    if not result.get("available"):
        raise HTTPException(status_code=404, detail=result.get("reason", "USI unavailable for this area"))
    return result
@app.get("/api/alerts/active")
def api_active_alerts():
    result = integration_bridge.get_active_alerts()
    from traffic_alert_eligibility import get_active_traffic_incident_alerts
    try:
        result["traffic_incident_alerts"] = get_active_traffic_incident_alerts()
    except Exception as e:
        result["traffic_incident_alerts"] = []
        result["traffic_incident_alerts_error"] = str(e)
    return result
@app.get("/api/alerts/{area_name}")
def api_alert_for_area(area_name: str):
    result = integration_bridge.get_alert_for_area(area_name)
    if not result.get("available"):
        raise HTTPException(status_code=404, detail=result.get("reason", "Alert unavailable for this area"))
    return result
@app.get("/api/waste/summary")
def api_waste_summary():
    result = integration_bridge.get_waste_summary()
    if not result.get("available"):
        raise HTTPException(status_code=503, detail=result.get("reason", "Waste data unavailable"))
    return result
@app.get("/api/wards")
def api_wards_summary():
    return ward_registry_service.get_ward_summary()
@app.get("/api/wards/list")
def api_wards_list():
    """Full list of all 369 real wards with their coverage classification."""
    return ward_registry_service.get_all_wards()
@app.get("/api/wards/{ward_id}")
def api_ward_detail(ward_id: str):
    result = ward_registry_service.get_ward(ward_id)
    if not result.get("available"):
        raise HTTPException(status_code=404, detail=result.get("reason", "Ward not found"))
    return result
def _ward_traffic_signal(ward_id, ward_name, lat, lon):
    if lat is None or lon is None:
        return {"severity": None, "source": "NO_DATA", "detail": "Ward has no centroid coordinates."}
    try:
        now = datetime.now()
        signal = get_route_traffic_signal([[lat, lon]], now.hour, now.weekday() >= 5)
    except Exception as e:
        signal = {"covered": False, "reason": f"real GNN lookup failed: {e}"}

    if signal.get("covered"):
        seg = signal["matched_segments"][0]
        is_extrapolated = signal.get("source") == "REAL_GNN_V1_EXTRAPOLATED"
        severity = max(0.0, min(100.0, 100.0 * (1.0 - seg["predicted_speed_kmh"] / 40.0)))
        return {
            "severity": round(severity, 1),
            "source": "REAL_GNN_EXTRAPOLATED" if is_extrapolated else "REAL_GNN",
            "detail": f"{'Extrapolated, unvalidated' if is_extrapolated else 'Real'} GNN prediction near "
                      f"'{seg['road_name']}' ({seg['distance_from_route_m']}m from ward centroid): "
                      f"{seg['predicted_speed_kmh']} km/h predicted.",
        }

    ward_stress_data = get_ward_stress_by_id(ward_id)
    if ward_stress_data:
        return {
            "severity": float(ward_stress_data["traffic_score"]),
            "source": "SIMULATED_WARD_STRESS",
            "detail": f"No real GNN coverage near this ward's centroid; using its own simulated "
                      f"stress score (ward_stress.py, random-based, not a live feed).",
        }
    return {"severity": None, "source": "NO_DATA", "detail": "No real or simulated signal available for this ward."}

@app.get("/api/wards/full/schema")
def api_wards_full_schema():
    try:
        from waste_signal import get_waste_severity
        from usi_engine import compute_usi
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"USI/waste modules unavailable: {e}")

    all_wards = ward_registry_service.get_all_wards()
    wards = all_wards.get("wards", []) if isinstance(all_wards, dict) else all_wards
    rows = []
    for w in wards:
        ward_id = w.get("ward_id")
        ward_name = w.get("ward_name")
        lat, lon = w.get("centroid_lat"), w.get("centroid_lon")
        traffic = _ward_traffic_signal(ward_id, ward_name, lat, lon)
        waste = get_waste_severity(w.get("waste_area_name") or ward_name) if w.get("waste_data_available") else \
            {"severity": None, "source": "NO_DATA"}
        usi_val = None
        coverage_status = w.get("coverage_class", "INSUFFICIENT_DATA")
        if traffic.get("severity") is not None or waste.get("severity") is not None:
            try:
                usi_result = compute_usi(ward_name)
                usi_val = usi_result.get("usi")
                coverage_status = usi_result.get("coverage_status", coverage_status)
            except Exception:
                pass
        rows.append({
            "ward_id": ward_id,
            "ward_name": ward_name,
            "latitude": lat,
            "longitude": lon,
            "traffic_status": _level_label(traffic["severity"]) if traffic.get("severity") is not None else "NO_DATA",
            "traffic_score": traffic.get("severity"),
            "traffic_source": traffic.get("source"),
            "traffic_data_age": "no live feed \u2014 static model, see traffic_data_status" if traffic.get("source") in ("REAL_GNN", "REAL_GNN_EXTRAPOLATED")
                                 else ("simulated, not time-stamped" if traffic.get("source") == "SIMULATED_WARD_STRESS" else None),
            "waste_score": waste.get("severity"),
            "waste_source": waste.get("source"),
            "USI": round(usi_val, 1) if usi_val is not None else None,
            "coverage_status": coverage_status,
        })
    traffic_source_counts = {}
    for r in rows:
        traffic_source_counts[r["traffic_source"]] = traffic_source_counts.get(r["traffic_source"], 0) + 1
    return {
        "available": True,
        "total_wards": len(rows),
        "traffic_coverage_summary": {
            "real_monitored": traffic_source_counts.get("REAL_GNN", 0),
            "model_inferred_unvalidated": traffic_source_counts.get("REAL_GNN_EXTRAPOLATED", 0),
            "simulated_fallback": traffic_source_counts.get("SIMULATED_WARD_STRESS", 0),
            "no_data": traffic_source_counts.get("NO_DATA", 0),
        },
        "wards": rows,
    }



def _level_label(score):
    if score is None:
        return None
    if score < 40:
        return "LOW"
    if score < 70:
        return "MODERATE"
    if score < 90:
        return "HIGH"
    return "SEVERE"


@app.get("/api/traffic/data-status")
def api_traffic_data_status():
    return get_traffic_data_status()
_TRAFFIC_HISTORY_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bengaluru_traffic_history.csv")


@app.get("/api/traffic/forecast-2h")
def api_traffic_forecast_2h(
    source: Optional[str] = Query(None, description="Route source location (e.g. 'Hebbal')"),
    destination: Optional[str] = Query(None, description="Route destination location (e.g. 'Silk Board')"),
):
    if not source or not destination:
        return {
            "forecast_horizon_minutes": 120,
            "available": False,
            "reason": "source and destination query parameters are required for a route-level 2-hour forecast",
            "current": None,
            "forecast": None,
            "method": None,
            "confidence": None,
            "data_quality": None,
            "limitations": [],
        }
    from traffic_forecast_service import get_route_forecast_2h
    result = get_route_forecast_2h(source, destination)
    result["confidence"] = result.get("data_quality")
    return result
@app.get("/api/traffic/forecast-t120")
def api_traffic_forecast_t120(
    road_name: Optional[str] = Query(None, description="Real road name to forecast (must be one of the 8 segments the preliminary model was trained on)"),
):
    """Preliminary T+120 (2-hour-ahead) forecast for a single monitored
    road segment. Returns available=False with an honest reason if
    road_name is missing, unsupported, or no real recent observation
    exists -- never a fabricated or substituted value."""
    from forecasting.t120_preliminary_service import get_t120_forecast, get_supported_segments
    if not road_name:
        return {
            "available": False,
            "reason": "road_name query parameter is required.",
            "supported_segments": [s["road_name"] for s in get_supported_segments()],
        }
    return get_t120_forecast(road_name)


@app.get("/api/traffic/forecast-t120/segments")
def api_traffic_forecast_t120_segments():
    """The exact list of real road segments the preliminary T+120 model
    was trained on and currently has data for -- backs the frontend's
    segment picker/matching. Empty list if the model isn't available."""
    from forecasting.t120_preliminary_service import get_supported_segments
    return {"segments": get_supported_segments()}


@app.post("/api/traffic/forecast-t120/for-route")
def api_traffic_forecast_t120_for_route(payload: dict):
    """Preliminary T+120 forecast for whichever of the 8 trained segments
    (if any) the GIVEN route geometry actually passes near, plus an
    honest whole-route future-ETA assessment. This is the endpoint the
    Traffic page's "Predict After 2 Hours" option calls: the frontend
    passes the exact `route_coords` (and `distance_km`) already returned
    by /api/predict-enhanced for this route (same geometry/distance the
    map and "Predict Now" use), so this can never disagree about which
    route is being asked about, and never recomputes/changes the route's
    distance -- `distance_km` is used only to judge what fraction of the
    route real monitored segments actually cover."""
    from forecasting.t120_preliminary_service import get_t120_forecast_for_route
    route_coords = payload.get("route_coords") or []
    route_distance_km = payload.get("distance_km")
    if not route_coords:
        return {"available": False, "reason": "route_coords is required (the route's geometry)."}
    return get_t120_forecast_for_route(route_coords, route_distance_km)


@app.get("/api/traffic/forecast-t120/model-info")
def api_traffic_forecast_t120_model_info():
    """Generic T+120 model/training metadata (pair counts, segment
    counts, train/val/test split, real test metrics, persistence-baseline
    comparison) read entirely from the training script's saved report.
    This is the one place the frontend queries for these numbers, so
    retraining the pipeline on more collected data (overwriting the two
    saved artifacts) updates the UI automatically -- no frontend or
    hardcoded-constant changes needed."""
    from forecasting.t120_preliminary_service import get_model_metadata
    return get_model_metadata()


@app.get("/api/traffic/incidents")
def api_traffic_incidents(
    source: Optional[str] = Query(None, description="Optional: check whether any incident intersects this route (on-demand only, never auto-subscribes)"),
    destination: Optional[str] = Query(None, description="Paired with source"),
):
    """Real-time traffic anomaly detection over whatever has already been
    collected (no new TomTom calls here — see traffic_incident_service.py
    for the classification hierarchy: NORMAL_CONGESTION / HEAVY_CONGESTION /
    TRAFFIC_ANOMALY / POSSIBLE_TRAFFIC_BLOCKAGE / PROVIDER_CONFIRMED_INCIDENT).
    This project's TomTom integration has no incident-confirmation endpoint
    wired up, so PROVIDER_CONFIRMED_INCIDENT never fires here — disclosed
    in every response, not hidden."""
    from traffic_incident_service import (
        analyze_all_segments, load_recent_observations_from_csv, latest_observation_timestamp,
        get_data_mode, check_route_impact, _ESCALATED_STATES,
    )
    from traffic_alert_eligibility import is_alert_eligible, get_all_alert_state, build_bilingual_alert_message

    tomtom_configured = bool(os.getenv("TOMTOM_API_KEY") or os.getenv("TRAFFIC_API_KEY"))

    if not os.path.exists(_TRAFFIC_HISTORY_CSV):
        return {
            "available": False,
            "data_mode": get_data_mode(tomtom_configured, None),
            "reason": "no traffic history file has been collected yet",
            "incidents": [],
        }

    by_segment = load_recent_observations_from_csv(_TRAFFIC_HISTORY_CSV)
    last_ts = latest_observation_timestamp(by_segment)
    age_seconds = (datetime.now() - last_ts).total_seconds() if last_ts else None

    results = analyze_all_segments(by_segment)
    incidents = [r for r in results if r["type"] in _ESCALATED_STATES]
    # Evidence-level rank, not a fabricated float — HIGH first.
    _rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    incidents.sort(key=lambda r: _rank.get(r["evidence_level"], 0), reverse=True)
    for inc in incidents:
        eligible, reason = is_alert_eligible(inc["segment_id"], inc["type"], inc.get("latitude"), inc.get("longitude"))
        inc["alert_eligible"] = eligible
        inc["alert_eligibility_reason"] = reason
        inc["alert_message"] = build_bilingual_alert_message(inc) if eligible else None
        inc["route_impact"] = None

    response = {
        "available": True,
        "data_mode": get_data_mode(tomtom_configured, age_seconds),
        "segments_checked": len(results),
        "incident_count": len(incidents),
        "provider_incident_feed_configured": False,
        "as_of": last_ts.isoformat() if last_ts else None,
        "incidents": incidents,
    }

    if source and destination:
        route_impact = check_route_impact(source, destination, incidents)
        response["route_impact"] = route_impact
        affected_segment_ids = {i["segment_id"] for i in route_impact.get("incidents_on_route", [])}
        for inc in incidents:
            inc["route_impact"] = inc["segment_id"] in affected_segment_ids

    return response


@app.post("/api/traffic/location")
def api_traffic_location(payload: dict):
    """Registers/refreshes a browser-consented user's current location for
    incident-alert matching (PART 5/6). Ephemeral, in-memory only (see
    user_location_service.py) — never written to disk, never exposed to
    other clients, expires automatically if not refreshed. Returns ONLY
    the calling session's own nearby-incident matches — never other
    users' locations."""
    from traffic_incident_service import (
        analyze_all_segments, load_recent_observations_from_csv, latest_observation_timestamp, _ESCALATED_STATES,
    )
    from traffic_alert_eligibility import match_users_to_incident, build_alert_message, build_bilingual_alert_message
    from user_location_service import update_location

    session_id = payload.get("session_id")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")

    if not session_id or latitude is None or longitude is None:
        raise HTTPException(status_code=400, detail="session_id, latitude, and longitude are required")

    try:
        loc = update_location(str(session_id), float(latitude), float(longitude))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger_msg_segments_checked = 0
    nearby_incidents = []

    if os.path.exists(_TRAFFIC_HISTORY_CSV):
        by_segment = load_recent_observations_from_csv(_TRAFFIC_HISTORY_CSV)
        results = analyze_all_segments(by_segment)
        incidents = [r for r in results if r["type"] in _ESCALATED_STATES]
        logger_msg_segments_checked = len(results)

        affected_locations = [
            {"segment_id": inc["segment_id"], "latitude": inc.get("latitude"), "longitude": inc.get("longitude")}
            for inc in incidents
        ]
        matches = match_users_to_incident(affected_locations, [loc])
        matched_segment_ids = {m["matched_segment_id"] for m in matches}

        for inc in incidents:
            if inc["segment_id"] in matched_segment_ids:
                match = next(m for m in matches if m["matched_segment_id"] == inc["segment_id"])
                nearby_incidents.append({
                    **inc,
                    "distance_km": match["distance_km"],
                    "message": build_alert_message(inc),
                    "message_bilingual": build_bilingual_alert_message(inc),
                })

    return {
        "session_id": loc.session_id,
        "last_updated": loc.last_updated.isoformat(),
        "segments_checked": logger_msg_segments_checked,
        "nearby_incident_count": len(nearby_incidents),
        "nearby_incidents": nearby_incidents,
    }


@app.delete("/api/traffic/location/{session_id}")
def api_traffic_location_delete(session_id: str):
    """Explicit opt-out — called when the user revokes location permission."""
    from user_location_service import remove_location
    remove_location(session_id)
    return {"removed": True, "session_id": session_id}


@app.get("/api/traffic/live-status")
def api_traffic_live_status():
    """Whether TomTom is actually configured right now (key presence
    only — never the value), and how fresh the last real collected
    observation is. Does not make a live API call."""
    from traffic_incident_service import load_recent_observations_from_csv, latest_observation_timestamp, get_data_mode
    from user_location_service import active_user_count

    tomtom_configured = bool(os.getenv("TOMTOM_API_KEY") or os.getenv("TRAFFIC_API_KEY"))

    if not os.path.exists(_TRAFFIC_HISTORY_CSV):
        return {
            "tomtom_configured": tomtom_configured,
            "data_mode": get_data_mode(tomtom_configured, None),
            "historical_data_available": False,
            "last_observation_at": None,
            "active_location_sessions": active_user_count(),
            "reason": "no traffic history file has been collected yet",
        }

    by_segment = load_recent_observations_from_csv(_TRAFFIC_HISTORY_CSV, max_per_segment=1)
    last_ts = latest_observation_timestamp(by_segment)
    age_seconds = (datetime.now() - last_ts).total_seconds() if last_ts else None
    age_minutes = age_seconds / 60.0 if age_seconds is not None else None

    return {
        "tomtom_configured": tomtom_configured,
        "data_mode": get_data_mode(tomtom_configured, age_seconds),
        "historical_data_available": bool(by_segment),
        "segments_with_data": len(by_segment),
        "last_observation_at": last_ts.isoformat() if last_ts else None,
        "last_observation_age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
        "active_location_sessions": active_user_count(),
        "note": (
            "Reflects the collector's last saved snapshot, not a live call made just now. "
            "Live polling is manual/explicit (see collect_bengaluru_traffic_production.py) "
            "and is never triggered automatically by this endpoint or by opening the dashboard."
        ),
    }


@app.get("/api/waste/routes")
def api_waste_routes(
    num_vehicles: Optional[int] = Query(None, description="Override the auto-determined vehicle count"),
    vehicle_capacity_kg: Optional[int] = Query(None, description="Override the default 10,000kg per-vehicle capacity"),
    areas: Optional[str] = Query(None, description="Pipe-separated ('|') area names to restrict routing to; omit for all areas. NOT comma-separated — many real area names in this dataset contain literal commas (e.g. 'Bengaluru area (12.97, 77.60)')."),
    force_refresh: bool = Query(False, description="Bypass the cache and force a fresh OR-Tools solve"),
    time_limit_seconds: Optional[int] = Query(None, description="Real OR-Tools search budget in seconds (default 8)"),
):
    """Genuinely re-solves the real OR-Tools capacitated VRP whenever any
    input changes (area selection, vehicle count, capacity) or the
    underlying data changes — never presents a stale/cached solve for
    different inputs as if it were fresh. See TEST_REPORT.md for the
    infeasibility/edge-case test matrix (insufficient vehicles, oversized
    demand, invalid area names, etc.)."""
    area_list = [a.strip() for a in areas.split("|") if a.strip()] if areas else None
    result = integration_bridge.get_waste_routing_summary(
        area_names=area_list,
        num_vehicles=num_vehicles,
        vehicle_capacity_kg=vehicle_capacity_kg,
        time_limit_seconds=time_limit_seconds,
        force_refresh=force_refresh,
    )
    if not result.get("available"):
        # NO_FEASIBLE_SOLUTION / INVALID_INPUT / ERROR are all legitimate,
        # honest domain answers, not server errors — return 200 with the
        # explicit status rather than masking them as a 503/500.
        return result
    return result


@app.get("/api/health")
def api_health_check():
    try:
        return {
            "status": "HEALTHY",
            "gnn_checkpoint_v2_loaded": MODEL_CACHE is not None,
            "gnn_checkpoint_v2_metrics": (MODEL_CACHE or {}).get("metrics", {}),
            "gnn_checkpoint_v2_note": "loaded but NOT used for live prediction (kept as historical baseline; "
                                      "see real_gnn_v1 below for the model actually wired into inference)",
            "real_gnn_v1": get_model_metrics(),
            "traffic_data_status": get_traffic_data_status(),
            "ward_coverage": ward_registry_service.get_ward_summary(),
            "usi_integration": integration_bridge.verify_area_coverage(),
            "locations_count": len(LOCATION_DB),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

class AddIncidentRequest(BaseModel):
    type: str  # accident, road_closure, congestion, construction
    location: str  # Location name
    severity: str  # low, moderate, high, severe
    description: str
    impact_min: int = 0  # Optional, will be estimated if not provided

class RemoveIncidentRequest(BaseModel):
    incident_id: str

@app.post("/api/incident/add")
def add_incident(req: AddIncidentRequest):
    """Add a new incident for testing/demo purposes"""
    try:
        incident_service = get_incident_service()
        incident = incident_service.add_incident(
            incident_type=req.type,
            location_name=req.location,
            severity=req.severity,
            description=req.description,
            impact_min=req.impact_min
        )
        return {
            "success": True,
            "incident": incident.to_dict(),
            "message": f"Incident added: {req.description}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/incident/remove")
def remove_incident(req: RemoveIncidentRequest):
    """Remove an incident by ID"""
    try:
        incident_service = get_incident_service()
        success = incident_service.remove_incident(req.incident_id)
        if success:
            return {"success": True, "message": f"Incident {req.incident_id} removed"}
        else:
            raise HTTPException(status_code=404, detail="Incident not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/incident/list")
def list_incidents():
    """List all active incidents"""
    try:
        incident_service = get_incident_service()
        incidents = incident_service.get_active_incidents()
        return {"success": True, "incidents": incidents, "count": len(incidents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/incident/clear")
def clear_incidents():
    """Clear all active incidents"""
    try:
        incident_service = get_incident_service()
        incident_service.clear_all_incidents()
        return {"success": True, "message": "All incidents cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict-route")
def predict_route(req: RouteRequest):

    result = predict_traffic(
        req.source,
        req.destination
    )

    return result

@app.post("/api/predict-enhanced")
def predict_enhanced(req: RouteRequest):
    """
    Enhanced prediction using modular services
    - Real routing provider (OSRM/ORS/Google Maps)
    - Incident detection and handling
    - Alternative route comparison
    - Weather impact
    - GNN prediction for future traffic
    """
    try:
        now = datetime.now()
        hour = now.hour
        is_weekday = now.weekday() < 5

        # Unique per-request identity (Priority 6: proving repeated
        # predictions are genuinely independent, not silently reusing a
        # cached/previous result). prediction_id is unique per HTTP call;
        # route_hash is deterministic on (source, destination, weather,
        # hour-bucket) so identical repeated requests can be recognized as
        # "the same route asked again" without conflating them with a
        # different request's result — the two are DIFFERENT fields on
        # purpose (uuid4 proves independence, the hash proves the route
        # was echoed correctly).
        prediction_id = str(uuid.uuid4())
        route_hash_input = f"{req.source.strip().lower()}|{req.destination.strip().lower()}|{getattr(req, 'weather', None)}|{hour}"
        route_hash = hashlib.sha256(route_hash_input.encode()).hexdigest()[:16]

        # Get routing service
        routing_service = get_routing_service()
        
        # Get route from routing provider
        route_data = routing_service.get_route(req.source, req.destination)
        
        if not route_data or not route_data.get("primary_route"):
            raise HTTPException(status_code=400, detail="Unable to find route")
        
        primary_route = route_data["primary_route"]
        alternative_routes = route_data.get("alternative_routes", [])
        
        # Get weather data
        weather_data = get_live_weather()
        weather_impact = get_weather_impact()
        weather_multiplier = weather_impact["multiplier"]
        
        # Get incident service and check for incidents on route
        incident_service = get_incident_service()
        route_coords = [(coord[0], coord[1]) for coord in primary_route["geometry"]]
        incident_impact = incident_service.calculate_total_impact(route_coords)
        
        # Calculate base and current travel times.
        # NOTE ON HONESTY: base_duration_min is only ever distinct from
        # duration_min for a traffic-aware provider (Google Maps); OSRM/ORS
        # set them equal (see routing_service.py) because they have no live
        # traffic signal of their own. current_time_min below is therefore
        # a STATIC routing estimate, not a live measurement, until/unless
        # the real GNN or weather/incidents adjust it below.
        base_time_min = primary_route.get("base_duration_min", primary_route["duration_min"])
        current_time_min = primary_route["duration_min"] * weather_multiplier
        if incident_impact["has_incident"]:
            current_time_min += incident_impact["total_impact_min"]

        # Real GNN lookup FIRST — this is the one genuinely validated signal
        # (retrained on real TomTom/OSM data; spatial-test R²=0.62, MAE 5.9
        # km/h — see traffic_model_real_v1_metrics.json) and it now actually
        # drives the prediction when it has coverage, instead of sitting
        # next to a disconnected heuristic number as before.
        try:
            real_gnn_signal = get_route_traffic_signal(primary_route["geometry"], hour, not is_weekday)
        except Exception as e:
            real_gnn_signal = {"covered": False, "reason": f"real GNN lookup failed: {e}", "source": "REAL_GNN_V1"}
        distance_km = primary_route["distance_km"]
        free_flow_speed_est = (distance_km / base_time_min) * 60 if base_time_min > 0 else 0.0
        if real_gnn_signal.get("covered"): 
            is_extrapolated = real_gnn_signal.get("source") == "REAL_GNN_V1_EXTRAPOLATED"
            traffic_source = "REAL_GNN_EXTRAPOLATED" if is_extrapolated else "REAL_GNN"
            real_avg_speed = real_gnn_signal["avg_predicted_speed_kmh"]
            
            slowdown_ratio = max(0.2, min(1.3, real_avg_speed / free_flow_speed_est)) if free_flow_speed_est > 0 else 1.0
            predicted_time_min = current_time_min / slowdown_ratio
            predicted_speed = real_avg_speed
            spatial_r2 = real_gnn_signal.get("model_metrics", {}).get("spatial_test", {}).get("R2", 0.5)
            if is_extrapolated:
                # No test-set validation exists for this specific edge —
                # cap confidence well below the validated tier regardless of
                # the model's overall spatial-test R², rather than implying
                # the same accuracy guarantee.
                confidence = 0.25
                model_used = ("Real GNN (extrapolated: same trained model, real OSM edge, "
                              "but this segment has no TomTom ground-truth label — unvalidated estimate)")
            else:
                confidence = max(0.3, min(0.9, float(spatial_r2)))
                model_used = f"Real GNN (retrained on TomTom/OSM data, spatial-test R²={spatial_r2:.2f})"
            n_matched = len(real_gnn_signal.get("matched_segments", []))
            # Real, backend-computed congestion score (0-100) — derived
            # directly from the real measured slowdown ratio, not a
            # client-side lookup table.
            congestion_score = round(max(0.0, min(1.0, 1.0 - slowdown_ratio)) * 100, 1)
        else:
            traffic_source = "HEURISTIC_FALLBACK"
            # No live traffic and no real-GNN coverage for this route: be
            # honest that "predicted" is not an independent measurement —
            # it equals the (weather/incident-adjusted) static estimate.
            predicted_time_min = current_time_min
            predicted_speed = (distance_km / predicted_time_min) * 60 if predicted_time_min > 0 else 0.0
            confidence = 0.3
            model_used = "Heuristic (static routing + weather/incident adjustment only — no live traffic or real-GNN coverage for this route)"
            n_matched = 0
            congestion_score = round(max(0.0, min(1.0, (current_time_min - base_time_min) / max(base_time_min, 1e-6))) * 100, 1)
        route_comparison = get_route_comparison()
        primary_for_comparison = {
            "distance_km": primary_route["distance_km"],
            "duration_min": current_time_min,
            "base_duration_min": base_time_min,
            "geometry": primary_route["geometry"]
        }

        comparison_result = route_comparison.compare_routes(
            primary_for_comparison, alternative_routes, incident_impact
        )

        # Calculate delays
        delay_min = current_time_min - base_time_min
        predicted_delay_min = predicted_time_min - base_time_min
        current_speed = (primary_route["distance_km"] / current_time_min) * 60 if current_time_min > 0 else 0
        if real_gnn_signal.get("covered"):
            if slowdown_ratio >= 0.85:
                traffic_level = "LOW"
            elif slowdown_ratio >= 0.65:
                traffic_level = "MODERATE"
            elif slowdown_ratio >= 0.45:
                traffic_level = "HIGH"
            else:
                traffic_level = "SEVERE"
        elif delay_min <= base_time_min * 0.1:
            traffic_level = "LOW"
        elif delay_min <= base_time_min * 0.3:
            traffic_level = "MODERATE"
        elif delay_min <= base_time_min * 0.6:
            traffic_level = "HIGH"
        else:
            traffic_level = "SEVERE"

        # Sampled points along the route the real-GNN lookup actually
        # checked, vs how many had a real monitored segment nearby — the
        # honest "coverage" figure the audit asked for.
        sampled_points = max(1, len(primary_route["geometry"][:: max(1, len(primary_route["geometry"]) // 40) or 1]))
        coverage_info = {
            "road_segments_used": n_matched,
            "road_segments_sampled": sampled_points,
            "percentage_real": round(100.0 * n_matched / sampled_points, 1) if sampled_points else 0.0,
        }

        # Honest real-time-status fields. There is no live TomTom/telemetry
        # feed wired into this environment (no TOMTOM_API_KEY configured),
        # and the GNN is a static, offline-trained checkpoint — not a
        # continuously-refreshed live model. Rather than fabricate a
        # "freshness" timestamp for either path, report that plainly:
        # traffic_data_timestamp/data_age_seconds are null and
        # traffic_data_status says so explicitly. This is real GNN inference
        # against real trained edges (REAL_GNN) or an honest static-only
        # fallback (HEURISTIC_FALLBACK) — never labeled as a live feed.
        traffic_data_status = (
            "REAL_GNN_STATIC_MODEL_NO_LIVE_FEED" if traffic_source == "REAL_GNN"
            else "REAL_GNN_EXTRAPOLATED_STATIC_MODEL_NO_LIVE_FEED" if traffic_source == "REAL_GNN_EXTRAPOLATED"
            else "NO_LIVE_FEED_NO_GNN_COVERAGE"
        )

        # Format response
        response = {
            "source": req.source,
            "destination": req.destination,
            
            # Coordinates
            "source_coords": [routing_service.geocode(req.source)[0], routing_service.geocode(req.source)[1]],
            "destination_coords": [routing_service.geocode(req.destination)[0], routing_service.geocode(req.destination)[1]],
            
            # Distance
            "distance_km": round(primary_route["distance_km"], 2),
            
            # Travel times
            "base_travel_time_min": round(base_time_min, 1),
            "current_travel_time_min": round(current_time_min, 1),
            "predicted_travel_time_min": round(predicted_time_min, 1),
            
            # Delays
            "delay_min": round(delay_min, 1),
            "predicted_delay_min": round(predicted_delay_min, 1),
            
            # Speeds
            "current_speed_kmh": round(current_speed, 1),
            "predicted_speed_kmh": round(predicted_speed, 1),
            
            # Traffic
            "traffic": traffic_level,
            "traffic_source": traffic_source,  # REAL_GNN or HEURISTIC_FALLBACK — see model_info.model for detail
            "coverage": coverage_info,
            "confidence": round(confidence, 2),

            # Weather
            "weather": {
                "condition": weather_data.get("condition", "unknown"),
                "temperature": weather_data.get("temperature", 0),
                "rain": weather_data.get("humidity", 0) if weather_data.get("condition") in ["rain", "drizzle", "thunderstorm"] else 0,
                "visibility": weather_data.get("visibility", 10),
                "impact": classify_weather_impact(weather_multiplier),
                "multiplier": weather_multiplier
            },
            
            # Incident
            "incident": {
                "detected": incident_impact["has_incident"],
                "type": incident_impact["incidents"][0]["type"] if incident_impact["incidents"] else None,
                "severity": incident_impact["severity"],
                "location": incident_impact["incidents"][0]["location"] if incident_impact["incidents"] else None,
                "impact_min": incident_impact["total_impact_min"],
                "count": incident_impact.get("count", 0),
                "incidents": incident_impact["incidents"]
            },
            "route": {
                "distance_km": round(primary_route["distance_km"], 2),
                "base_time_min": round(base_time_min, 1),
                "current_time_min": round(current_time_min, 1),
                "predicted_time_min": round(predicted_time_min, 1),
                "geometry": primary_route["geometry"],
                "polyline": primary_route.get("polyline", "")
            },
            "alternative_routes": [
                route_comparison.format_route_for_response(alt)
                for alt in comparison_result["sorted_routes"]
                if not alt["is_primary"]
            ],
            
            # Recommendation
            "recommended_route": comparison_result["best_route"]["name"],
            "recommendation": comparison_result["recommendation"],
            
            "real_gnn_signal": real_gnn_signal,

            # Model info
            "model_info": {
                "model": model_used,
                "prediction_used": confidence > 0.4,
                "routing_provider": route_data["provider"],
                "traffic_aware": route_data.get("traffic_aware", False)
            },
            
            # Data sources
            "data_sources": {
                "traffic": (f"Real GNN ({n_matched} monitored segment(s) matched)" if traffic_source == "REAL_GNN"
                            else (f"Real GNN, extrapolated ({n_matched} unvalidated segment(s) matched)" if traffic_source == "REAL_GNN_EXTRAPOLATED"
                            else ("OSRM (no real-time traffic)" if route_data["provider"] == "OSRM"
                                  else f"{route_data['provider']} (traffic-aware)"))),
                "weather": ("OpenWeatherMap (live)" if weather_data.get("source") == "LIVE"
                            else f"Estimated fallback ({weather_data.get('source', 'no API key configured')})"),
                "routing": route_data["provider"],
                "incidents": "Simulated/Demo" if incident_impact["has_incident"] else "None"
            },
            
            # Legacy fields for compatibility
            "route_coords": primary_route["geometry"],
            "traffic_points": [],  # Not implemented in this version
            "road_names": [],  # Not implemented in this version
            "travel_time": round(predicted_time_min, 1),
            "predicted_mins": round(predicted_time_min, 1),
            "avg_speed": round(predicted_speed, 1),

            # Timestamp
            "last_updated": now.isoformat(),
            "prediction_id": prediction_id,
            "route_hash": route_hash,
        
            "route_label": f"{req.source} -> {req.destination}",
            "free_flow_eta_min": round(base_time_min, 1),
            "current_eta_min": round(current_time_min, 1),
            "predicted_eta_min": round(predicted_time_min, 1),
            "traffic_status": traffic_level,
    
            "congestion_score": congestion_score,
            "prediction_timestamp": now.isoformat(),
            "model": model_used,
            "model_version": ("traffic_model_real_v1" if traffic_source == "REAL_GNN"
                               else "traffic_model_real_v1_extrapolated" if traffic_source == "REAL_GNN_EXTRAPOLATED"
                               else "heuristic_v1"),
            "model_confidence": round(confidence, 2),
            "route_coverage": coverage_info,
            "matched_segments": n_matched,
            "total_segments": sampled_points,
            "data_age": "no live feed — static model / static routing (see traffic_data_status)",
            "traffic_data_timestamp": None,
            "data_age_seconds": None,
            "traffic_data_status": traffic_data_status,
            "number_of_real_observations": n_matched,
            "number_of_matched_route_segments": n_matched,
            "route_coverage_percentage": coverage_info["percentage_real"],
        }
    
        response["route_detail"] = {
            "distance_km": round(primary_route["distance_km"], 2),
            "base_time_min": round(base_time_min, 1),
            "current_time_min": round(current_time_min, 1),
            "predicted_time_min": round(predicted_time_min, 1),
            "geometry": primary_route["geometry"],
            "polyline": primary_route.get("polyline", "")
        }
        
        return response
        
    except Exception as e:
        print(f"Enhanced prediction error: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to existing prediction
        result = predict_traffic(req.source, req.destination)
        result["data_sources"] = {
            "traffic": "Fallback to historical model",
            "weather": "OpenWeatherMap (live)",
            "routing": "Fallback",
            "incidents": "Error checking"
        }
        
        result.setdefault("predicted_eta_min", result.get("predicted_travel_time"))
        result.setdefault("current_eta_min", result.get("current_travel_time"))
        result.setdefault("free_flow_eta_min", result.get("base_travel_time"))
        return result


# ================================================================
# CITIZEN REGISTRATION & ALERT PREFERENCES (Stage 1 foundation only)
#
# Everything below is new and self-contained (citizen_registry.py +
# citizen_otp.py, its own SQLite file data/citizen_alerts.sqlite). It
# does NOT read, write, or import any existing Traffic ML/prediction
# module, the Waste prediction module, friend_waste, the USI engine, or
# the existing Traffic/Waste alert-detection modules (traffic_incident_
# service.py, traffic_alert_eligibility.py, user_location_service.py,
# integration/usi_engine.py, integration/alerts.py). Those are untouched
# and keep working exactly as before -- this block only ADDS new routes.
#
# No real SMS/OTP provider, no BHASHINI, no USSD here -- see
# citizen_otp.py's docstring. OTP codes are only ever exposed through a
# clearly-labeled dev response ("dev_otp"/"dev_notice") and a clearly-
# labeled console log line, never presented as sent to a real phone.
# ================================================================

class CitizenRegisterRequest(BaseModel):
    mobile_number: str
    preferred_language: str = "English"
    traffic_alerts_enabled: bool = False
    waste_alerts_enabled: bool = False
    location_consent: bool = False
    ward_id: Optional[str] = None


class CitizenUpdateRequest(BaseModel):
    preferred_language: Optional[str] = None
    traffic_alerts_enabled: Optional[bool] = None
    waste_alerts_enabled: Optional[bool] = None
    location_consent: Optional[bool] = None
    ward_id: Optional[str] = None  # pass "" to clear an existing ward
    status: Optional[str] = None   # "active" | "inactive"


class CitizenLocationUpdateRequest(BaseModel):
    """FINAL FEATURE: a registered citizen's browser-reported current
    coordinates. Never a mobile-number-inferred guess -- latitude/
    longitude must come from the browser's own Geolocation API, with the
    browser's own permission prompt already granted (see
    CitizenAlertRegistration.jsx)."""
    latitude: float
    longitude: float


class CitizenVerifyOtpRequest(BaseModel):
    mobile_number: str
    otp_code: str


def _dev_otp_fields(otp_result: dict) -> dict:
    """Only ever attaches the raw code to an HTTP response while
    citizen_otp.DEV_MODE is on -- see citizen_otp.py's own docstring for
    why that currently defaults on (no SMS provider exists yet)."""
    if not citizen_otp.DEV_MODE:
        return {"dev_mode": False}
    return {
        "dev_mode": True,
        "dev_otp": otp_result["code"],
        "dev_notice": citizen_otp.DEV_NOTICE,
    }


@app.post("/api/citizens/register")
def api_citizen_register(req: CitizenRegisterRequest):
    """Creates a new citizen subscription (status=pending_verification)
    and issues a registration OTP. Never fabricates a GPS location --
    only an optional, registry-validated ward_id is stored (see
    citizen_registry.resolve_ward); a mobile number never implies
    coordinates."""
    try:
        mobile = citizen_registry.validate_mobile_number(req.mobile_number)
        language = citizen_registry.normalize_language(req.preferred_language)
        ward_id, ward_name = citizen_registry.resolve_ward(req.ward_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        citizen = citizen_registry.create_citizen(
            mobile_number=mobile,
            preferred_language=language,
            traffic_alerts_enabled=req.traffic_alerts_enabled,
            waste_alerts_enabled=req.waste_alerts_enabled,
            location_consent=req.location_consent,
            ward_id=ward_id,
            ward_name=ward_name,
        )
    except citizen_registry.MobileAlreadyRegistered as e:
        raise HTTPException(status_code=409, detail={
            "message": "This mobile number is already registered.",
            "citizen_id": e.existing["id"],
            "status": e.existing["status"],
        })

    otp_result = citizen_otp.generate_otp(citizen["id"], mobile, purpose="registration")
    response = {
        "citizen": citizen,
        "verification_required": True,
        "otp_expires_at": otp_result["expires_at"],
    }
    response.update(_dev_otp_fields(otp_result))
    return response


@app.post("/api/citizens/verify-otp")
def api_citizen_verify_otp(req: CitizenVerifyOtpRequest):
    """Verifies the registration OTP and activates the subscription.
    Never claims an OTP was sent -- it only ever checks a code that was
    generated (and, in dev mode, shown/logged) by /api/citizens/register
    or the resend endpoint below."""
    try:
        mobile = citizen_registry.validate_mobile_number(req.mobile_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    citizen = citizen_registry.get_citizen_by_mobile(mobile)
    if citizen is None:
        raise HTTPException(status_code=404, detail="No registration found for this mobile number")

    ok, reason = citizen_otp.verify_otp(citizen["id"], mobile, req.otp_code, purpose="registration")
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    updated = citizen_registry.update_citizen(citizen["id"], mobile_verified=True, status="active")
    return {"citizen": updated, "verified": True}


@app.post("/api/citizens/{citizen_id}/resend-otp")
def api_citizen_resend_otp(citizen_id: int):
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")
    if citizen["mobile_verified"]:
        raise HTTPException(status_code=400, detail="This citizen is already verified")

    otp_result = citizen_otp.generate_otp(citizen_id, citizen["mobile_number"], purpose="registration")
    response = {"otp_expires_at": otp_result["expires_at"]}
    response.update(_dev_otp_fields(otp_result))
    return response


@app.get("/api/citizens/{citizen_id}")
def api_citizen_get(citizen_id: int):
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")
    return citizen


@app.patch("/api/citizens/{citizen_id}")
def api_citizen_update(citizen_id: int, req: CitizenUpdateRequest):
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")

    fields = {}
    try:
        if req.preferred_language is not None:
            fields["preferred_language"] = citizen_registry.normalize_language(req.preferred_language)
        if req.traffic_alerts_enabled is not None:
            fields["traffic_alerts_enabled"] = req.traffic_alerts_enabled
        if req.waste_alerts_enabled is not None:
            fields["waste_alerts_enabled"] = req.waste_alerts_enabled
        if req.location_consent is not None:
            fields["location_consent"] = req.location_consent
        if req.ward_id is not None:
            ward_id, ward_name = citizen_registry.resolve_ward(req.ward_id)
            fields["ward_id"] = ward_id
            fields["ward_name"] = ward_name
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.status is not None:
        if req.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'")
        if req.status == "active" and not citizen["mobile_verified"]:
            raise HTTPException(status_code=400, detail="Cannot activate before the mobile number is verified")
        fields["status"] = req.status

    if not fields:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    updated = citizen_registry.update_citizen(citizen_id, **fields)

    # FINAL FEATURE: stop live-location tracking the moment consent is
    # turned off or the citizen is deactivated -- never wait out the
    # ephemeral store's own TTL when we already know tracking should stop.
    if fields.get("location_consent") is False or fields.get("status") == "inactive":
        import citizen_alert_dispatch
        citizen_alert_dispatch.remove_live_location_for_citizen(citizen_id)

    return updated


@app.delete("/api/citizens/{citizen_id}")
def api_citizen_delete(citizen_id: int):
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")
    citizen_registry.delete_citizen(citizen_id)
    import citizen_alert_dispatch
    citizen_alert_dispatch.remove_live_location_for_citizen(citizen_id)
    return {"deleted": True, "id": citizen_id}


# ----------------------------------------------------------------
# FINAL FEATURE: live browser geolocation for a registered citizen.
#
# Reuses the EXISTING, untouched ephemeral/in-memory user_location_
# service.py (the same TTL-bound store /api/traffic/location already
# uses for anonymous browser sessions) -- no new storage, no lat/lon
# ever written to disk. citizen_alert_dispatch.citizen_location_
# session_id() is the single source of truth for the session key these
# two endpoints and dispatch_traffic_alerts() all use, so they can never
# drift apart.
#
# Fails closed: a citizen who has not turned location_consent on, or
# who is not active, is refused -- this endpoint can never be used to
# track someone who hasn't explicitly opted in via the existing
# location_consent preference. It records/removes a coordinate only; it
# never decides eligibility, cooldown, or deduplication -- that remains
# entirely citizen_alert_dispatch.py's job, unchanged.
# ----------------------------------------------------------------

@app.post("/api/citizens/{citizen_id}/location")
def api_citizen_location_update(citizen_id: int, req: CitizenLocationUpdateRequest):
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")
    if not citizen["location_consent"]:
        raise HTTPException(status_code=403, detail="Citizen has not given location consent")
    if citizen["status"] != "active":
        raise HTTPException(status_code=403, detail="Citizen is not an active subscriber")

    import citizen_alert_dispatch
    from user_location_service import update_location
    try:
        loc = update_location(
            citizen_alert_dispatch.citizen_location_session_id(citizen_id),
            req.latitude, req.longitude,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"citizen_id": citizen_id, "tracking": True, "last_updated": loc.last_updated.isoformat()}


@app.delete("/api/citizens/{citizen_id}/location")
def api_citizen_location_delete(citizen_id: int):
    """Explicit opt-out -- called when the browser loses/revokes
    permission or the alert panel stops tracking this citizen."""
    import citizen_alert_dispatch
    citizen_alert_dispatch.remove_live_location_for_citizen(citizen_id)
    return {"removed": True, "citizen_id": citizen_id}


# ================================================================
# CITIZEN ALERT DISPATCH (Stage 2 -- connects the Stage 1 registry to
# the EXISTING alert sources)
#
# citizen_alert_dispatch.py reads ONLY the existing read-only accessors
# (traffic_alert_eligibility.get_active_traffic_incident_alerts(),
# integration_bridge.get_active_alerts()) -- it never calls
# is_alert_eligible(), maybe_alert_and_send(), or check_and_update().
# No real SMS/BHASHINI/USSD/WhatsApp provider anywhere in this block --
# every delivery is SIMULATED_NOT_SENT, same posture as Stage 1.
# ================================================================

@app.post("/api/citizens/dispatch/run")
def api_citizens_dispatch_run():
    """Reads ALREADY-fired alerts from both existing engines' own read-
    only accessors and records a SIMULATED delivery for every matching,
    verified, active, consenting citizen. Never re-triggers either
    engine's eligibility/cooldown logic -- see citizen_alert_dispatch.py's
    own docstring for why."""
    import citizen_alert_dispatch
    return citizen_alert_dispatch.run_dispatch()


@app.get("/api/citizens/{citizen_id}/alert-deliveries")
def api_citizen_alert_deliveries(citizen_id: int):
    """Truthful per-citizen delivery history for the My Alerts panel --
    a pure read of this citizen's own rows only, never a fabricated
    subscriber/delivery count."""
    citizen = citizen_registry.get_citizen(citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")
    import citizen_alert_dispatch
    return {"citizen_id": citizen_id, "deliveries": citizen_alert_dispatch.get_deliveries_for_citizen(citizen_id)}


# ================================================================
# AUTOMATIC CITIZEN ALERT DISPATCH (BACKGROUND LOOP)
#
# Schedules the EXISTING citizen_alert_dispatch.run_dispatch() -- the same
# function POST /api/citizens/dispatch/run already calls manually above --
# on a periodic timer so it no longer requires a manual HTTP call.
#
# This block does not reimplement dispatch, SMS, eligibility, cooldown, or
# deduplication. It only schedules the existing, already-safe/idempotent
# entry point. See citizen_alert_dispatch.py's own docstring for why
# run_dispatch() is safe to call repeatedly.
# ================================================================

CITIZEN_ALERT_DISPATCH_INTERVAL_SECONDS = 60

_citizen_dispatch_task = None  # guards against starting more than one loop


async def _citizen_alert_dispatch_loop():
    import citizen_alert_dispatch
    while True:
        try:
            citizen_alert_dispatch.run_dispatch()
        except Exception as exc:
            # One failed cycle must never stop future cycles. Log only the
            # exception type/message -- never citizen data or credentials.
            print(f"[CITIZEN_DISPATCH_LOOP] dispatch cycle failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(CITIZEN_ALERT_DISPATCH_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_citizen_alert_dispatch_loop():
    """Starts exactly one background dispatch loop. Does not block startup --
    asyncio.create_task schedules the loop and returns immediately."""
    global _citizen_dispatch_task
    if _citizen_dispatch_task is not None:
        return
    _citizen_dispatch_task = asyncio.create_task(_citizen_alert_dispatch_loop())


@app.on_event("shutdown")
async def _stop_citizen_alert_dispatch_loop():
    """Cancels the background dispatch loop cleanly on app shutdown."""
    global _citizen_dispatch_task
    if _citizen_dispatch_task is None:
        return
    _citizen_dispatch_task.cancel()
    try:
        await _citizen_dispatch_task
    except asyncio.CancelledError:
        pass
    _citizen_dispatch_task = None


# ---------------- MAIN ----------------

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

