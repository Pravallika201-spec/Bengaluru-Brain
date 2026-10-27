"""
Routing Service - Handles routing provider integration
Uses OSRM as primary (free, no API key required)
Can be extended to use ORS or Google Maps with API keys
"""

import requests
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import polyline
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from location_data import BENGALURU_LOCATIONS

class RoutingService:
    """
    Routing service for getting routes, distances, and travel times
    """
    
    def __init__(self):
        self.osrm_base_url = "https://router.project-osrm.org"
        self.ors_api_key = os.getenv("ORS_API_KEY")
        self.google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        
        self.provider = "OSRM"  # Default to free OSRM
        if self.google_maps_api_key:
            self.provider = "Google Maps"
        elif self.ors_api_key:
            self.provider = "ORS"
    
    def geocode(self, place_name: str) -> Tuple[float, float]:
        """
        Geocode a place name to coordinates
        Returns (lat, lon)
        """
        text = (place_name or "").strip()
        if not text:
            raise ValueError("Unable to geocode: empty place name")

        if text in BENGALURU_LOCATIONS:
            loc = BENGALURU_LOCATIONS[text]
            return loc['lat'], loc['lon']

        lowered = text.lower()
        for name, loc in BENGALURU_LOCATIONS.items():
            if name.lower() == lowered:
                return loc['lat'], loc['lon']
        
        # Fallback to Nominatim
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="bengaluru_traffic")
        location = geolocator.geocode(f"{text}, Bengaluru, Karnataka, India")
        if location:
            return location.latitude, location.longitude
        
        raise ValueError(f"Unable to geocode: {place_name}")
    
    def get_route_osrm(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Dict:
        """
        Get route using OSRM (free, no API key)
        
        Returns:
            dict with route information
        """
        lon1, lat1 = origin[1], origin[0]
        lon2, lat2 = destination[1], destination[0]
        
        url = f"{self.osrm_base_url}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "full",
            "geometries": "polyline",
            "alternatives": "true"  # Request alternative routes
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != "Ok":
                raise ValueError(f"OSRM error: {data.get('message')}")
            
            routes = []
            for route in data.get("routes", []):
                # polyline.decode returns (lat, lon) tuples
                decoded = polyline.decode(route["geometry"])
                route_coords = [[lat, lon] for lat, lon in decoded]
                duration_min = route["duration"] / 60
                
                routes.append({
                    "distance_km": route["distance"] / 1000,
                    "duration_min": duration_min,
                    # OSRM is not real-time traffic; base time equals static duration
                    "base_duration_min": duration_min,
                    "geometry": route_coords,
                    "polyline": route["geometry"]
                })
            
            # Return primary route and alternatives
            primary = routes[0] if routes else None
            alternatives = routes[1:] if len(routes) > 1 else []
            
            return {
                "provider": "OSRM",
                "primary_route": primary,
                "alternative_routes": alternatives,
                "has_traffic": False,  # OSRM does not provide real-time traffic
                "traffic_aware": False
            }
            
        except requests.RequestException as e:
            print(f"OSRM routing error: {e}")
            raise
    
    def get_route_ors(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Dict:
        """
        Get route using OpenRouteService (requires API key)
        Supports traffic-aware routing
        """
        if not self.ors_api_key:
            raise ValueError("ORS_API_KEY not configured")
        
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": self.ors_api_key}
        
        params = {
            "start": f"{origin[1]},{origin[0]}",
            "end": f"{destination[1]},{destination[0]}",
            "alternative_routes": {"share_factor": 0.6, "target_count": 2}
        }
        
        try:
            response = requests.post(url, json=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            routes = []
            for route in data.get("routes", []):
                decoded = polyline.decode(route["geometry"])
                route_coords = [[lat, lon] for lat, lon in decoded]
                
                duration_min = route["summary"]["duration"] / 60
                routes.append({
                    "distance_km": route["summary"]["distance"] / 1000,
                    "duration_min": duration_min,
                    "base_duration_min": duration_min,
                    "geometry": route_coords,
                    "polyline": route["geometry"]
                })
            
            primary = routes[0] if routes else None
            alternatives = routes[1:] if len(routes) > 1 else []
            
            return {
                "provider": "ORS",
                "primary_route": primary,
                "alternative_routes": alternatives,
                "has_traffic": False,  # ORS basic routing
                "traffic_aware": False
            }
            
        except requests.RequestException as e:
            print(f"ORS routing error: {e}")
            raise
    
    def get_route(self, source: str, destination: str) -> Dict:
        """
        Get route between two locations
        Tries providers in order: Google Maps -> ORS -> OSRM
        """
        # Geocode locations
        origin = self.geocode(source)
        dest = self.geocode(destination)
        
        # Try providers in order
        if self.google_maps_api_key:
            try:
                return self.get_route_google(origin, dest)
            except Exception as e:
                print(f"Google Maps routing failed: {e}, falling back to OSRM")
        
        if self.ors_api_key:
            try:
                return self.get_route_ors(origin, dest)
            except Exception as e:
                print(f"ORS routing failed: {e}, falling back to OSRM")
        
        # Default to OSRM (free, no API key)
        return self.get_route_osrm(origin, dest)
    
    def get_route_google(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Dict:
        """
        Get route using Google Maps Routes API (requires API key)
        Supports traffic-aware routing and alternatives
        """
        if not self.google_maps_api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY not configured")
        
        url = f"https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.google_maps_api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.staticDuration,routes.polyline.encodedPolyline,routes.routeLabels"
        }
        
        body = {
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": True,
            "routeModifiers": {"avoidTolls": False, "avoidHighways": False, "avoidFerries": False}
        }
        
        try:
            response = requests.post(url, json=body, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            routes = []
            for route in data.get("routes", []):
                decoded = polyline.decode(route["polyline"]["encodedPolyline"])
                route_coords = [[lat, lon] for lat, lon in decoded]
                
                # Google provides both duration (traffic-aware) and staticDuration (base)
                duration_min = route["duration"] / 60
                static_duration_min = route["staticDuration"] / 60
                
                routes.append({
                    "distance_km": route["distanceMeters"] / 1000,
                    "duration_min": duration_min,
                    "base_duration_min": static_duration_min,
                    "geometry": route_coords,
                    "polyline": route["polyline"]["encodedPolyline"]
                })
            
            primary = routes[0] if routes else None
            alternatives = routes[1:] if len(routes) > 1 else []
            
            return {
                "provider": "Google Maps",
                "primary_route": primary,
                "alternative_routes": alternatives,
                "has_traffic": True,
                "traffic_aware": True
            }
            
        except requests.RequestException as e:
            print(f"Google Maps routing error: {e}")
            raise

# Singleton instance
_routing_service = None

def get_routing_service():
    """Get or create singleton routing service"""
    global _routing_service
    if _routing_service is None:
        _routing_service = RoutingService()
    return _routing_service
