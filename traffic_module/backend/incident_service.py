"""
Incident Service - Handles incident detection and impact calculation
Supports accident, road closure, congestion, construction incidents
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import math
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from location_data import BENGALURU_LOCATIONS

class Incident:
    """
    Represents a traffic incident
    """
    def __init__(self, incident_id: str, incident_type: str, location: Tuple[float, float],
                 severity: str, description: str, impact_min: int = 0, 
                 affected_radius_km: float = 1.0):
        self.id = incident_id
        self.type = incident_type  # accident, road_closure, congestion, construction
        self.location = location  # (lat, lon)
        self.severity = severity  # low, moderate, high, severe
        self.description = description
        self.impact_min = impact_min  # Estimated delay in minutes
        self.affected_radius_km = affected_radius_km
        self.created_at = datetime.now()
        self.active = True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "type": self.type,
            "location": self.location,
            "severity": self.severity,
            "description": self.description,
            "impact_min": self.impact_min,
            "affected_radius_km": self.affected_radius_km,
            "created_at": self.created_at.isoformat(),
            "active": self.active
        }

class IncidentService:
    """
    Service for managing incidents and calculating their impact on routes
    """
    
    def __init__(self):
        self.active_incidents: List[Incident] = []
        self.incident_counter = 0
    
    def add_incident(self, incident_type: str, location_name: str, severity: str,
                    description: str, impact_min: int = 0) -> Incident:
        """
        Add a new incident
        
        Args:
            incident_type: Type of incident (accident, road_closure, congestion, construction)
            location_name: Name of location (e.g., "Hebbal")
            severity: Severity level (low, moderate, high, severe)
            description: Human-readable description
            impact_min: Estimated delay in minutes
        
        Returns:
            Incident object
        """
        self.incident_counter += 1
        incident_id = f"INC_{self.incident_counter:04d}"
        
        # Geocode location
        if location_name in BENGALURU_LOCATIONS:
            loc = BENGALURU_LOCATIONS[location_name]
            location = (loc['lat'], loc['lon'])
        else:
            # Default to Bengaluru center if location not found
            location = (12.9716, 77.5946)
        
        # Estimate impact based on severity if not provided
        if impact_min == 0:
            impact_min = self._estimate_impact(incident_type, severity)
        
        incident = Incident(
            incident_id=incident_id,
            incident_type=incident_type,
            location=location,
            severity=severity,
            description=description,
            impact_min=impact_min,
            affected_radius_km=self._get_radius(incident_type, severity)
        )
        
        self.active_incidents.append(incident)
        return incident
    
    def remove_incident(self, incident_id: str) -> bool:
        """Remove an incident by ID"""
        for incident in self.active_incidents:
            if incident.id == incident_id:
                incident.active = False
                self.active_incidents.remove(incident)
                return True
        return False
    
    def clear_all_incidents(self):
        """Clear all active incidents"""
        self.active_incidents.clear()
    
    def get_active_incidents(self) -> List[Dict]:
        """Get all active incidents"""
        return [inc.to_dict() for inc in self.active_incidents if inc.active]
    
    def _estimate_impact(self, incident_type: str, severity: str) -> int:
        """Estimate impact in minutes based on type and severity"""
        base_impacts = {
            "accident": {"low": 5, "moderate": 15, "high": 30, "severe": 45},
            "road_closure": {"low": 10, "moderate": 20, "high": 40, "severe": 60},
            "congestion": {"low": 3, "moderate": 8, "high": 15, "severe": 25},
            "construction": {"low": 5, "moderate": 10, "high": 20, "severe": 30}
        }
        return base_impacts.get(incident_type, {}).get(severity, 10)
    
    def _get_radius(self, incident_type: str, severity: str) -> float:
        """Get affected radius in km based on type and severity"""
        # Increased radii to better match sparse OSRM route coordinates
        base_radii = {
            "accident": {"low": 2.0, "moderate": 3.0, "high": 5.0, "severe": 7.0},
            "road_closure": {"low": 2.0, "moderate": 3.0, "high": 5.0, "severe": 8.0},
            "congestion": {"low": 1.5, "moderate": 2.5, "high": 4.0, "severe": 6.0},
            "construction": {"low": 2.0, "moderate": 3.0, "high": 5.0, "severe": 7.0}
        }
        return base_radii.get(incident_type, {}).get(severity, 3.0)
    
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in km"""
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def check_incident_on_route(self, route_coords: List[Tuple[float, float]]) -> List[Dict]:
        """
        Check if any active incidents affect the given route
        
        Args:
            route_coords: List of (lat, lon) coordinates representing the route
        
        Returns:
            List of incidents that affect the route
        """
        affecting_incidents = []
        
        for incident in self.active_incidents:
            if not incident.active:
                continue
            
            # Check if any route point is within the incident's affected radius
            for coord in route_coords:
                distance = self.haversine_distance(
                    coord[0], coord[1],
                    incident.location[0], incident.location[1]
                )
                
                if distance <= incident.affected_radius_km:
                    affecting_incidents.append(incident.to_dict())
                    break  # Only count each incident once
        
        return affecting_incidents
    
    def calculate_total_impact(self, route_coords: List[Tuple[float, float]]) -> Dict:
        """
        Calculate total impact of all incidents on a route
        
        Returns:
            dict with impact information
        """
        affecting_incidents = self.check_incident_on_route(route_coords)
        
        if not affecting_incidents:
            return {
                "has_incident": False,
                "incidents": [],
                "total_impact_min": 0,
                "severity": "none"
            }
        
        # Sum impacts (simplified - in reality would consider overlapping incidents)
        total_impact = sum(inc["impact_min"] for inc in affecting_incidents)
        
        # Determine overall severity
        severities = [inc["severity"] for inc in affecting_incidents]
        severity_order = ["low", "moderate", "high", "severe"]
        max_severity_index = max(severity_order.index(s) for s in severities)
        overall_severity = severity_order[max_severity_index]
        
        return {
            "has_incident": True,
            "incidents": affecting_incidents,
            "total_impact_min": total_impact,
            "severity": overall_severity,
            "count": len(affecting_incidents)
        }

# Singleton instance
_incident_service = None

def get_incident_service():
    """Get or create singleton incident service"""
    global _incident_service
    if _incident_service is None:
        _incident_service = IncidentService()
    return _incident_service
