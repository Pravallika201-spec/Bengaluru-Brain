"""
Test script to verify distance comes from routing provider
Tests multiple routes to ensure distances vary based on actual routes
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_route(source, destination):
    """Test a single route and return key metrics"""
    payload = {
        "source": source,
        "destination": destination
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/predict-enhanced", json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        return {
            "source": source,
            "destination": destination,
            "distance_km": data.get("distance_km"),
            "base_time_min": data.get("base_travel_time_min"),
            "current_time_min": data.get("current_travel_time_min"),
            "predicted_time_min": data.get("predicted_travel_time_min"),
            "routing_provider": data.get("model_info", {}).get("routing_provider"),
            "traffic_aware": data.get("model_info", {}).get("traffic_aware"),
            "data_sources": data.get("data_sources", {})
        }
    except Exception as e:
        print(f"Error testing {source} -> {destination}: {e}")
        return None

def main():
    print("=" * 70)
    print("DISTANCE VERIFICATION TEST")
    print("=" * 70)
    
    # Test multiple routes
    test_cases = [
        ("Hebbal", "Marathahalli"),
        ("Electronic City", "Yelahanka"),
        ("Silk Board", "Whitefield"),
        ("MG Road", "Manyata Tech Park"),
        ("Koramangala", "JP Nagar")
    ]
    
    results = []
    
    for source, destination in test_cases:
        print(f"\nTesting: {source} -> {destination}")
        result = test_route(source, destination)
        if result:
            results.append(result)
            print(f"  ✅ Distance: {result['distance_km']} km")
            print(f"  ✅ Base Time: {result['base_time_min']} min")
            print(f"  ✅ Current Time: {result['current_time_min']} min")
            print(f"  ✅ Provider: {result['routing_provider']}")
            print(f"  ✅ Traffic Aware: {result['traffic_aware']}")
            print(f"  ✅ Data Sources: {result['data_sources']}")
    
    print("\n" + "=" * 70)
    print("SUMMARY - Distance Comparison")
    print("=" * 70)
    
    for result in results:
        print(f"{result['source']:20} → {result['destination']:20}: {result['distance_km']:6.2f} km")
    
    # Check if distances vary
    distances = [r['distance_km'] for r in results]
    if len(set([round(d, 1) for d in distances])) > 1:
        print("\n✅ DISTANCES VARY - Confirmed: Distance comes from routing provider")
    else:
        print("\n❌ DISTANCES ARE CONSTANT - Issue detected")
    
    print("\n" + "=" * 70)
    print("ROUTING PROVIDER INFO")
    print("=" * 70)
    
    providers = [r['routing_provider'] for r in results]
    print(f"Provider used: {providers[0] if providers else 'Unknown'}")
    print(f"Traffic-aware: {results[0]['traffic_aware'] if results else 'Unknown'}")

if __name__ == "__main__":
    main()
