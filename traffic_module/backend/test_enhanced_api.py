"""
Test script for enhanced API endpoints
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_enhanced_prediction():
    """Test the enhanced prediction endpoint"""
    print("Testing enhanced prediction endpoint...")
    
    payload = {
        "source": "Hebbal",
        "destination": "Marathahalli"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/predict-enhanced", json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print("✅ Enhanced prediction successful!")
        print(f"Source: {data['source']}")
        print(f"Destination: {data['destination']}")
        print(f"Distance: {data['distance_km']} km")
        print(f"Base travel time: {data['base_travel_time_min']} min")
        print(f"Current travel time: {data['current_travel_time_min']} min")
        print(f"Predicted travel time: {data['predicted_travel_time_min']} min")
        print(f"Current speed: {data['current_speed_kmh']} km/h")
        print(f"Predicted speed: {data['predicted_speed_kmh']} km/h")
        print(f"Traffic: {data['traffic']}")
        print(f"Confidence: {data['confidence']}")
        print(f"Weather: {data['weather']['condition']} (impact: {data['weather']['impact']})")
        print(f"Incident detected: {data['incident']['detected']}")
        print(f"Routing provider: {data['model_info']['routing_provider']}")
        print(f"Traffic aware: {data['model_info']['traffic_aware']}")
        print(f"Alternative routes: {len(data['alternative_routes'])}")
        print(f"Recommendation: {data['recommendation']}")
        print(f"\nData sources:")
        for key, value in data['data_sources'].items():
            print(f"  {key}: {value}")
        
        return True
    except Exception as e:
        print(f"❌ Enhanced prediction failed: {e}")
        return False

def test_incident_add():
    """Test adding an incident"""
    print("\nTesting incident addition...")
    
    payload = {
        "type": "accident",
        "location": "Hebbal",
        "severity": "high",
        "description": "Accident on Hebbal flyover",
        "impact_min": 20
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/incident/add", json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print("✅ Incident added successfully!")
        print(f"Incident ID: {data['incident']['id']}")
        print(f"Type: {data['incident']['type']}")
        print(f"Severity: {data['incident']['severity']}")
        print(f"Impact: {data['incident']['impact_min']} min")
        
        return data['incident']['id']
    except Exception as e:
        print(f"❌ Incident addition failed: {e}")
        return None

def test_incident_list():
    """Test listing incidents"""
    print("\nTesting incident list...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/incident/list", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Active incidents: {data['count']}")
        for inc in data['incidents']:
            print(f"  - {inc['id']}: {inc['type']} at {inc['severity']} severity")
        
        return True
    except Exception as e:
        print(f"❌ Incident list failed: {e}")
        return False

def test_incident_remove(incident_id):
    """Test removing an incident"""
    print(f"\nTesting incident removal for {incident_id}...")
    
    payload = {"incident_id": incident_id}
    
    try:
        response = requests.post(f"{BASE_URL}/api/incident/remove", json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print("✅ Incident removed successfully!")
        return True
    except Exception as e:
        print(f"❌ Incident removal failed: {e}")
        return False

def test_incident_clear():
    """Test clearing all incidents"""
    print("\nTesting incident clear...")
    
    try:
        response = requests.post(f"{BASE_URL}/api/incident/clear", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print("✅ All incidents cleared!")
        return True
    except Exception as e:
        print(f"❌ Incident clear failed: {e}")
        return False

def test_prediction_with_incident():
    """Test prediction with an active incident"""
    print("\nTesting prediction with incident...")
    
    # Add incident
    incident_id = test_incident_add()
    if not incident_id:
        return False
    
    # Test prediction with incident
    payload = {
        "source": "Hebbal",
        "destination": "Marathahalli"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/predict-enhanced", json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print("✅ Prediction with incident successful!")
        print(f"Incident detected: {data['incident']['detected']}")
        print(f"Incident impact: {data['incident']['impact_min']} min")
        print(f"Recommendation: {data['recommendation']}")
        
        # Clean up
        test_incident_clear()
        
        return True
    except Exception as e:
        print(f"❌ Prediction with incident failed: {e}")
        test_incident_clear()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Enhanced API Endpoints")
    print("=" * 60)
    
    # Test enhanced prediction
    test_enhanced_prediction()
    
    # Test incident management
    incident_id = test_incident_add()
    if incident_id:
        test_incident_list()
        test_incident_remove(incident_id)
    
    # Test prediction with incident
    test_prediction_with_incident()
    
    print("\n" + "=" * 60)
    print("Testing Complete")
    print("=" * 60)
