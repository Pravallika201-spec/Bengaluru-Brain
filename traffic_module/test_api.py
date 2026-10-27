import requests
import json

url = "http://127.0.0.1:8000/predict-route"
payload = {
    "source": "Hebbal",
    "destination": "Marathahalli",
    "weather": "clear"
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
