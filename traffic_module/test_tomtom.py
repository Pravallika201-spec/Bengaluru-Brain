import os
import sys
sys.path.append('backend')
from backend.tomtom_traffic_service import TomTomTrafficService

print('Testing TomTom Traffic Service')
print('=' * 50)

# Check for API key
api_key = os.getenv('TOMTOM_API_KEY')
print(f'TOMTOM_API_KEY environment variable: {"SET" if api_key else "NOT SET"}')
if api_key:
    print(f'API key length: {len(api_key)} characters')
    print(f'API key prefix: {api_key[:8]}...' if len(api_key) > 8 else 'API key too short')

# Create service
tomtom_service = TomTomTrafficService()
print(f'TomTom service available: {tomtom_service.is_available()}')

# Test with sample Bengaluru coordinates (Hebbal to Marathahalli route)
test_coords = [
    (13.0358, 77.5970),  # Hebbal
    (13.0200, 77.6200),  # Intermediate point
    (13.0000, 77.6500),  # Intermediate point
    (12.9591, 77.6974)   # Marathahalli
]

print(f'\nTesting with {len(test_coords)} sample coordinates along Hebbal-Marathahalli route')
print('Coordinates:', test_coords)

try:
    result = tomtom_service.get_route_traffic(test_coords)
    print('\nTomTom API Result:')
    print(f'Available: {result.get("available")}')
    print(f'Source: {result.get("source")}')
    
    if result.get('available'):
        print(f'Current speed: {result.get("current_speed_kmh")} km/h')
        print(f'Free flow speed: {result.get("free_flow_speed_kmh")} km/h')
        print(f'Traffic status: {result.get("traffic_status")}')
        print(f'Confidence: {result.get("confidence")}')
        print(f'Segments analyzed: {result.get("segments_analyzed")}')
        print(f'Speed ratio: {result.get("speed_ratio")}')
        print('\nSUCCESS: TomTom real-time traffic is working')
    else:
        print(f'Error: {result.get("error")}')
        if 'http_status' in result:
            print(f'HTTP Status: {result.get("http_status")}')
        print('\nFAILED: TomTom API call failed')
        
except Exception as e:
    print(f'\nERROR: Exception during TomTom test: {e}')
    import traceback
    traceback.print_exc()
