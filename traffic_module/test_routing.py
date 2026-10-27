import sys
sys.path.append('backend')
from backend.routing_service import RoutingService

print('Testing Routing Service')
print('=' * 50)

# Create service
routing_service = RoutingService()
print(f'Routing provider: {routing_service.provider}')

# Test routes
test_routes = [
    ("Hebbal", "Marathahalli"),
    ("Whitefield", "Electronic City"),
    ("MG Road", "Indiranagar")
]

for source, destination in test_routes:
    print(f'\nTesting route: {source} -> {destination}')
    try:
        result = routing_service.get_route(source, destination)
        
        if result and result.get('primary_route'):
            primary = result['primary_route']
            print(f'Distance: {primary["distance_km"]:.2f} km')
            print(f'Duration: {primary["duration_min"]:.1f} min')
            print(f'Provider: {result["provider"]}')
            print(f'Traffic aware: {result.get("traffic_aware", False)}')
            print(f'Alternatives: {len(result.get("alternative_routes", []))}')
            
            # Check that geometry exists
            if primary.get('geometry'):
                print(f'Route coordinates: {len(primary["geometry"])} points')
            else:
                print('WARNING: No route geometry')
        else:
            print('ERROR: No primary route returned')
            
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()

print('\nRouting service test completed')
