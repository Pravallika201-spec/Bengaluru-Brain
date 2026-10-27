import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import requests
import json
import time

print('Testing Backend API Endpoint')
print('=' * 50)

# Test the enhanced API endpoint
url = "http://127.0.0.1:8000/api/predict-enhanced"

test_cases = [
    {"source": "Hebbal", "destination": "Marathahalli"},
    {"source": "Electronic City", "destination": "Yelahanka"},
    {"source": "Whitefield", "destination": "Electronic City"}
]

for i, test_case in enumerate(test_cases, 1):
    print(f'\nTest {i}: {test_case["source"]} -> {test_case["destination"]}')
    print('-' * 40)
    
    try:
        response = requests.post(url, json=test_case, timeout=30)
        
        print(f'Status Code: {response.status_code}')
        
        if response.status_code == 200:
            data = response.json()
            
            print('SUCCESS: API call successful')
            print(f'Status: {data.get("status")}')
            
            # Extract key information
            route = data.get('route', {})
            traffic = data.get('traffic', {})
            prediction = data.get('prediction', {})
            weather = data.get('weather', {})
            incidents = data.get('incidents', {})
            recommendation = data.get('recommendation', {})
            usi = data.get('usi', {})
            messages = data.get('messages', {})
            data_sources = data.get('data_sources', {})
            
            print(f'\nRoute Information:')
            print(f'  Distance: {route.get("distance_km")} km')
            print(f'  Base time: {route.get("base_travel_time_min")} min')
            print(f'  Current time: {route.get("current_travel_time_min")} min')
            print(f'  Predicted time: {route.get("predicted_travel_time_min")} min')
            
            print(f'\nTraffic Information:')
            print(f'  Source: {traffic.get("source")}')
            print(f'  Current speed: {traffic.get("current_speed_kmh")} km/h')
            print(f'  Free flow speed: {traffic.get("free_flow_speed_kmh")} km/h')
            print(f'  Traffic status: {traffic.get("traffic_status")}')
            print(f'  Traffic aware: {traffic.get("traffic_aware")}')
            print(f'  Delay: {traffic.get("delay_min")} min')
            
            print(f'\nGNN Prediction:')
            print(f'  Source: {prediction.get("source")}')
            print(f'  Predicted speed: {prediction.get("predicted_speed_kmh")} km/h')
            print(f'  Predicted time: {prediction.get("predicted_travel_time_min")} min')
            print(f'  Confidence: {prediction.get("confidence")}')
            
            print(f'\nWeather:')
            print(f'  Condition: {weather.get("condition")}')
            print(f'  Temperature: {weather.get("temperature")}C')
            print(f'  Impact: {weather.get("impact")}')
            print(f'  Multiplier: {weather.get("multiplier")}')
            
            print(f'\nIncidents:')
            print(f'  Detected: {incidents.get("detected")}')
            print(f'  Count: {incidents.get("count")}')
            print(f'  Severity: {incidents.get("severity")}')
            
            print(f'\nRecommendation:')
            print(f'  Route: {recommendation.get("route")}')
            print(f'  Reason: {recommendation.get("reason")}')
            
            print(f'\nUSI:')
            print(f'  Status: {usi.get("status")}')
            
            print(f'\nMessages:')
            print(f'  English: {messages.get("english")}')
            print(f'  Kannada: {messages.get("kannada")}')
            
            print(f'\nData Sources:')
            print(f'  Routing: {data_sources.get("routing")}')
            print(f'  Traffic: {data_sources.get("traffic")}')
            print(f'  Prediction: {data_sources.get("prediction")}')
            print(f'  Weather: {data_sources.get("weather")}')
            
            # Save full response to file
            filename = f'api_response_test_{i}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'\nFull response saved to: {filename}')
            
        else:
            print(f'ERROR: API returned status {response.status_code}')
            print(f'Error detail: {response.text}')
            
    except requests.exceptions.Timeout:
        print('ERROR: Request timed out')
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    
    # Small delay between tests
    if i < len(test_cases):
        time.sleep(2)

print('\n' + '=' * 50)
print('API endpoint testing completed')
