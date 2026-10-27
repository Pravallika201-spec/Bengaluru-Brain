import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
sys.path.append('backend')
from backend.weather_logic import get_live_weather, get_weather_impact, classify_weather_impact
from backend.incident_service import get_incident_service
from backend.route_comparison import get_route_comparison
from backend.usi_service import get_usi_service
from backend.kannada_messages import get_kannada_service

print('Testing Backend Services')
print('=' * 50)

# Test Weather
print('\n1. Testing Weather Service')
try:
    weather = get_live_weather()
    print(f'Weather condition: {weather.get("condition")}')
    print(f'Temperature: {weather.get("temperature")}C')
    print(f'Humidity: {weather.get("humidity")}%')
    print(f'Description: {weather.get("description")}')
    
    impact = get_weather_impact()
    print(f'Weather multiplier: {impact["multiplier"]}')
    print(f'Impact level: {impact["impact_level"]}')
    print('SUCCESS: Weather service working')
except Exception as e:
    print(f'ERROR: Weather service failed: {e}')

# Test Incident Service
print('\n2. Testing Incident Service')
try:
    incident_service = get_incident_service()
    # Add a test incident
    incident = incident_service.add_incident(
        incident_type="accident",
        location_name="Hebbal",
        severity="moderate",
        description="Test accident for verification"
    )
    print(f'Added incident: {incident.id}')
    print(f'Incident type: {incident.type}')
    print(f'Impact: {incident.impact_min} min')
    
    # Check impact on a sample route
    route_coords = [(13.0358, 77.5970), (13.0200, 77.6200), (12.9591, 77.6974)]
    impact = incident_service.calculate_total_impact(route_coords)
    print(f'Incident on route: {impact["has_incident"]}')
    print(f'Total impact: {impact["total_impact_min"]} min')
    print(f'Severity: {impact["severity"]}')
    
    # Clear the test incident
    incident_service.clear_all_incidents()
    print('SUCCESS: Incident service working')
except Exception as e:
    print(f'ERROR: Incident service failed: {e}')

# Test Route Comparison
print('\n3. Testing Route Comparison')
try:
    route_comparison = get_route_comparison()
    primary_route = {
        "distance_km": 21.69,
        "duration_min": 27.6,
        "base_duration_min": 25.0,
        "geometry": [(13.0358, 77.5970), (12.9591, 77.6974)]
    }
    alternative_routes = [
        {"distance_km": 23.5, "duration_min": 30.0, "base_duration_min": 28.0, "geometry": [(13.0358, 77.5970), (12.9591, 77.6974)]}
    ]
    incident_impact = {"has_incident": False, "total_impact_min": 0, "severity": "none"}
    
    comparison = route_comparison.compare_routes(primary_route, alternative_routes, incident_impact)
    print(f'Best route: {comparison["best_route"]["name"]}')
    print(f'Recommendation: {comparison["recommendation"]}')
    print('SUCCESS: Route comparison working')
except Exception as e:
    print(f'ERROR: Route comparison failed: {e}')

# Test USI Service
print('\n4. Testing USI Service')
try:
    usi_service = get_usi_service()
    usi_result = usi_service.calculate_usi(
        {"speed": 30.0, "status": "MODERATE"},
        {"distance": 21.69},
        {"condition": "clear", "temperature": 28}
    )
    print(f'USI status: {usi_result["status"]}')
    print(f'USI message: {usi_result.get("message", "N/A")}')
    print('SUCCESS: USI service working (in placeholder state)')
except Exception as e:
    print(f'ERROR: USI service failed: {e}')

# Test Kannada Messages
print('\n5. Testing Kannada Messages Service')
try:
    kannada_service = get_kannada_service()
    message = kannada_service.generate_message(
        traffic_status="MODERATE",
        has_incident=False,
        weather_impact=False,
        reroute_recommended=False
    )
    print(f'English message: {message["english"]}')
    print(f'Kannada message: {message["kannada"]}')
    print('SUCCESS: Kannada messages working')
except Exception as e:
    print(f'ERROR: Kannada messages failed: {e}')

print('\n' + '=' * 50)
print('All services tested')
