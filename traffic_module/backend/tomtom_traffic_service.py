"""
TomTom Traffic Service - Real-time traffic data from TomTom API
Consolidates TomTom integration for route and coordinate-based traffic queries
"""

import requests
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

class TomTomTrafficService:
    """
    Service for fetching real-time traffic data from TomTom API
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TOMTOM_API_KEY") or os.getenv("TRAFFIC_API_KEY")
        self.base_url = "https://api.tomtom.com/traffic/services/4"
        self.timeout = 10
        
    def is_available(self) -> bool:
        """Check if TomTom API key is configured"""
        return bool(self.api_key)
    
    def get_route_traffic(self, route_coords: List[Tuple[float, float]]) -> Dict:
        """
        Get traffic data for a route
        
        Args:
            route_coords: List of (lat, lon) coordinates along the route
            
        Returns:
            Dictionary with traffic information
        """
        if not self.is_available():
            return {
                "available": False,
                "source": "TomTom",
                "error": "API key not configured"
            }
        
        if not route_coords:
            return {
                "available": False,
                "source": "TomTom",
                "error": "No route coordinates provided"
            }
        
        try:
            # Sample points along route (up to 5 points for API efficiency and rate limits)
            num_samples = min(5, max(1, len(route_coords)))
            step = max(1, len(route_coords) // num_samples)
            samples = route_coords[::step][:num_samples]
            
            current_speeds = []
            free_flow_speeds = []
            confidences = []
            last_error = None
            last_status = None
            
            for lat, lon in samples:
                url = f"{self.base_url}/flowSegmentData/absolute/10/json"
                params = {
                    "point": f"{lat},{lon}",
                    "unit": "KMPH",
                    "key": self.api_key
                }
                
                try:
                    response = requests.get(url, params=params, timeout=self.timeout)
                    if response.status_code == 200:
                        data = response.json()
                        flow_data = data.get("flowSegmentData", {})
                        if flow_data:
                            c_speed = flow_data.get("currentSpeed")
                            f_speed = flow_data.get("freeFlowSpeed")
                            conf = flow_data.get("confidence", 0.8)
                            if c_speed is not None:
                                current_speeds.append(float(c_speed))
                            if f_speed is not None:
                                free_flow_speeds.append(float(f_speed))
                            if conf is not None:
                                confidences.append(float(conf))
                    else:
                        last_error = f"API returned HTTP {response.status_code}"
                        last_status = response.status_code
                except Exception as ex:
                    last_error = str(ex)
            
            if not current_speeds:
                return {
                    "available": False,
                    "source": "TomTom",
                    "error": last_error or "No traffic data returned from TomTom segments",
                    "http_status": last_status
                }
            
            avg_current_speed = sum(current_speeds) / len(current_speeds)
            avg_free_flow_speed = sum(free_flow_speeds) / len(free_flow_speeds) if free_flow_speeds else avg_current_speed
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.8
            
            # Calculate traffic status
            if avg_free_flow_speed > 0:
                speed_ratio = avg_current_speed / avg_free_flow_speed
                if speed_ratio >= 0.8:
                    traffic_status = "LOW"
                elif speed_ratio >= 0.6:
                    traffic_status = "MODERATE"
                elif speed_ratio >= 0.4:
                    traffic_status = "HIGH"
                else:
                    traffic_status = "SEVERE"
            else:
                speed_ratio = 1.0
                traffic_status = "UNKNOWN"
            
            return {
                "available": True,
                "source": "TomTom",
                "current_speed_kmh": round(avg_current_speed, 2),
                "free_flow_speed_kmh": round(avg_free_flow_speed, 2),
                "confidence": round(avg_confidence, 2),
                "traffic_status": traffic_status,
                "speed_ratio": round(speed_ratio, 2),
                "segments_analyzed": len(current_speeds),
                "timestamp": datetime.now().isoformat()
            }
            
        except requests.Timeout:
            return {
                "available": False,
                "source": "TomTom",
                "error": "Request timeout"
            }
        except requests.RequestException as e:
            return {
                "available": False,
                "source": "TomTom",
                "error": f"Request failed: {str(e)}"
            }
        except Exception as e:
            return {
                "available": False,
                "source": "TomTom",
                "error": f"Unexpected error: {str(e)}"
            }
    
    def get_point_traffic(self, lat: float, lon: float) -> Dict:
        """
        Get traffic data for a single point
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Dictionary with traffic information
        """
        if not self.is_available():
            return {
                "available": False,
                "source": "TomTom",
                "error": "API key not configured"
            }
        
        try:
            url = f"{self.base_url}/flowSegmentData/absolute/10/json"
            params = {
                "point": f"{lat},{lon}",
                "unit": "KMPH",
                "key": self.api_key
            }
            
            response = requests.get(url, params=params, timeout=self.timeout)
            
            if response.status_code != 200:
                return {
                    "available": False,
                    "source": "TomTom",
                    "error": f"API returned {response.status_code}"
                }
            
            data = response.json()
            flow_data = data.get("flowSegmentData", {})
            
            current_speed = flow_data.get("currentSpeed", 0)
            free_flow_speed = flow_data.get("freeFlowSpeed", 0)
            
            return {
                "available": True,
                "source": "TomTom",
                "current_speed_kmh": current_speed,
                "free_flow_speed_kmh": free_flow_speed,
                "confidence": flow_data.get("confidence", 0),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "available": False,
                "source": "TomTom",
                "error": str(e)
            }


# Singleton instance
_tomtom_service = None

def get_tomtom_service() -> TomTomTrafficService:
    """Get or create the TomTom traffic service singleton"""
    global _tomtom_service
    if _tomtom_service is None:
        _tomtom_service = TomTomTrafficService()
    return _tomtom_service
