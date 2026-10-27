"""
Route Comparison Service - Compares routes and recommends the best option
"""

from typing import Dict, List, Optional
from datetime import datetime

class RouteComparison:
    """
    Compares multiple routes and recommends the best one
    """
    
    @staticmethod
    def compare_routes(primary_route: Dict, alternative_routes: List[Dict], 
                       incident_impact: Dict) -> Dict:
        """
        Compare primary route with alternatives and recommend the best one
        
        Args:
            primary_route: Primary route data
            alternative_routes: List of alternative route data
            incident_impact: Incident impact information
        
        Returns:
            dict with comparison results and recommendation
        """
        # Apply incident impact to primary route
        primary_with_incident = primary_route.copy()
        if incident_impact["has_incident"]:
            primary_with_incident["duration_min"] += incident_impact["total_impact_min"]
            primary_with_incident["has_incident"] = True
            primary_with_incident["incident_impact_min"] = incident_impact["total_impact_min"]
        else:
            primary_with_incident["has_incident"] = False
            primary_with_incident["incident_impact_min"] = 0
        
        # Collect all routes for comparison
        all_routes = [{
            "name": "Primary Route",
            "distance_km": primary_with_incident["distance_km"],
            "duration_min": primary_with_incident["duration_min"],
            "base_duration_min": primary_with_incident.get("base_duration_min", primary_with_incident["duration_min"]),
            "geometry": primary_with_incident["geometry"],
            "has_incident": primary_with_incident["has_incident"],
            "incident_impact_min": primary_with_incident.get("incident_impact_min", 0),
            "is_primary": True
        }]
        
        # Add alternatives
        for i, alt in enumerate(alternative_routes):
            all_routes.append({
                "name": f"Alternative Route {i + 1}",
                "distance_km": alt["distance_km"],
                "duration_min": alt["duration_min"],
                "base_duration_min": alt.get("base_duration_min", alt["duration_min"]),
                "geometry": alt["geometry"],
                "has_incident": False,  # Alternatives not checked for incidents in this version
                "incident_impact_min": 0,
                "is_primary": False
            })
        
        # Sort by duration (primary factor)
        all_routes_sorted = sorted(all_routes, key=lambda r: r["duration_min"])
        
        # Select best route
        best_route = all_routes_sorted[0]
        
        # Generate recommendation
        recommendation = RouteComparison._generate_recommendation(
            primary_with_incident, all_routes_sorted, incident_impact
        )
        
        return {
            "all_routes": all_routes,
            "sorted_routes": all_routes_sorted,
            "best_route": best_route,
            "recommendation": recommendation,
            "primary_route_affected_by_incident": incident_impact["has_incident"]
        }
    
    @staticmethod
    def _generate_recommendation(primary_route: Dict, sorted_routes: List[Dict], 
                                 incident_impact: Dict) -> str:
        """Generate human-readable recommendation"""
        best_route = sorted_routes[0]
        primary_route = sorted_routes[0] if sorted_routes[0]["is_primary"] else [r for r in sorted_routes if r["is_primary"]][0]
        
        if not incident_impact["has_incident"]:
            if best_route["is_primary"]:
                return "Stay on current route. No incidents detected and it is the fastest option."
            else:
                time_saved = primary_route["duration_min"] - best_route["duration_min"]
                return f"Alternative route recommended. Saves approximately {time_saved:.1f} minutes compared to primary route."
        
        # There is an incident
        if best_route["is_primary"]:
            # Primary is still best despite incident
            return (f"Incident detected on current route ({incident_impact['severity']} severity), "
                   f"but no faster alternative is currently available. "
                   f"Estimated delay: {incident_impact['total_impact_min']} minutes.")
        else:
            # Alternative is better
            time_saved = primary_route["duration_min"] - best_route["duration_min"]
            return (f"Alternative route recommended. An incident ({incident_impact['severity']} severity) "
                   f"is causing {incident_impact['total_impact_min']} minutes delay on the primary route. "
                   f"Alternative route saves approximately {time_saved:.1f} minutes.")
    
    @staticmethod
    def calculate_traffic_level(duration_min: float, base_duration_min: float) -> str:
        """
        Calculate traffic level based on delay ratio
        """
        if base_duration_min == 0:
            return "UNKNOWN"
        
        delay_ratio = (duration_min - base_duration_min) / base_duration_min
        
        if delay_ratio <= 0.1:
            return "LOW"
        elif delay_ratio <= 0.3:
            return "MODERATE"
        elif delay_ratio <= 0.6:
            return "HIGH"
        else:
            return "SEVERE"
    
    @staticmethod
    def format_route_for_response(route: Dict) -> Dict:
        """Format route data for API response"""
        return {
            "name": route["name"],
            "distance_km": round(route["distance_km"], 2),
            "current_time_min": round(route["duration_min"], 1),
            "base_time_min": round(route["base_duration_min"], 1),
            "delay_min": round(route["duration_min"] - route["base_duration_min"], 1),
            "has_incident": route["has_incident"],
            "incident_impact_min": route["incident_impact_min"],
            "geometry": route["geometry"],
            "traffic_level": RouteComparison.calculate_traffic_level(
                route["duration_min"], route["base_duration_min"]
            )
        }

# Singleton instance
_route_comparison = None

def get_route_comparison():
    """Get or create singleton route comparison service"""
    global _route_comparison
    if _route_comparison is None:
        _route_comparison = RouteComparison()
    return _route_comparison
