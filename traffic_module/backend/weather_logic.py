"""
Weather Impact Logic for Bengaluru Traffic Prediction
Handles OpenWeatherMap API integration and weather multipliers
"""

import requests
from datetime import datetime
import os

# OpenWeatherMap API configuration
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "your_key_here")
BENGALURU_LAT = 12.9716
BENGALURU_LON = 77.5946

# Weather multipliers
WEATHER_MULTIPLIERS = {
    "clear": 1.0,
    "light_rain": 1.3,
    "heavy_rain": 1.7,
    "storm": 2.2,
    "fog": 1.5,
    "clouds": 1.1,
    "mist": 1.2,
    "thunderstorm": 2.0,
    "drizzle": 1.2
}

def get_weather_multiplier(weather_condition):
    """
    Get weather multiplier based on condition
    """
    condition = weather_condition.lower()
    
    # Map various weather conditions to our categories
    if condition in ["clear", "sunny"]:
        return WEATHER_MULTIPLIERS["clear"]
    elif condition in ["rain", "light rain", "shower rain"]:
        return WEATHER_MULTIPLIERS["light_rain"]
    elif condition in ["heavy rain", "extreme rain", "very heavy rain"]:
        return WEATHER_MULTIPLIERS["heavy_rain"]
    elif condition in ["storm", "thunderstorm", "severe thunderstorm"]:
        return WEATHER_MULTIPLIERS["storm"]
    elif condition in ["fog", "foggy", "dense fog"]:
        return WEATHER_MULTIPLIERS["fog"]
    elif condition in ["clouds", "cloudy", "overcast", "broken clouds", "scattered clouds"]:
        return WEATHER_MULTIPLIERS["clouds"]
    elif condition in ["mist", "haze"]:
        return WEATHER_MULTIPLIERS["mist"]
    elif condition in ["thunderstorm", "thunderstorm with rain", "thunderstorm with drizzle"]:
        return WEATHER_MULTIPLIERS["thunderstorm"]
    elif condition in ["drizzle", "light intensity drizzle", "drizzle rain"]:
        return WEATHER_MULTIPLIERS["drizzle"]
    else:
        return 1.0  # Default to clear weather

def get_live_weather():
    """
    Fetch live weather data from OpenWeatherMap API
    Returns weather info or None if API call fails
    """
    if OPENWEATHER_API_KEY == "your_key_here":
        # Return mock data for demo if no API key
        return {
            "condition": "clear",
            "temperature": 28,
            "humidity": 65,
            "description": "clear sky"
        }
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": BENGALURU_LAT,
            "lon": BENGALURU_LON,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric"
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract relevant weather information
        weather_info = {
            "condition": data["weather"][0]["main"].lower(),
            "description": data["weather"][0]["description"],
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data.get("wind", {}).get("speed", 0),
            "visibility": data.get("visibility", 10000) / 1000,  # Convert to km
            "timestamp": datetime.now().isoformat()
        }
        
        return weather_info
        
    except requests.exceptions.RequestException as e:
        print(f"Weather API error: {e}")
        # Return mock data on error
        return {
            "condition": "clear",
            "temperature": 28,
            "humidity": 65,
            "description": "clear sky"
        }

def get_weather_impact(weather_condition=None):
    """
    Get weather impact for traffic prediction
    If no condition provided, fetches live weather
    """
    if weather_condition:
        # Use provided condition
        multiplier = get_weather_multiplier(weather_condition)
        condition = weather_condition
    else:
        # Fetch live weather
        weather_info = get_live_weather()
        condition = weather_info["condition"]
        multiplier = get_weather_multiplier(condition)
    
    return {
        "condition": condition,
        "multiplier": multiplier,
        "impact_level": classify_weather_impact(multiplier)
    }

def classify_weather_impact(multiplier):
    """
    Classify weather impact level
    """
    if multiplier <= 1.0:
        return "LOW"
    elif multiplier <= 1.3:
        return "MODERATE"
    elif multiplier <= 1.7:
        return "HIGH"
    else:
        return "SEVERE"

def get_weather_forecast(hours_ahead=2):
    """
    Get weather forecast for next few hours
    Returns simplified forecast for traffic prediction
    """
    # For now, return current weather as forecast
    # In a real implementation, you'd call the forecast API
    current_weather = get_live_weather()
    
    # Simulate slight changes in weather
    forecast = []
    for i in range(1, hours_ahead + 1):
        future_weather = current_weather.copy()
        
        # Simple weather progression simulation
        if current_weather["condition"] == "clear":
            if i == 1:
                future_weather["condition"] = "clouds"
                future_weather["description"] = "few clouds"
        elif current_weather["condition"] == "clouds":
            if i == 2:
                future_weather["condition"] = "light_rain"
                future_weather["description"] = "light rain"
        
        forecast.append({
            "hours_ahead": i,
            "condition": future_weather["condition"],
            "multiplier": get_weather_multiplier(future_weather["condition"]),
            "temperature": future_weather["temperature"] + (i * 0.5)  # Slight temp change
        })
    
    return forecast

def is_severe_weather():
    """
    Check if current weather conditions are severe
    """
    weather_info = get_live_weather()
    return get_weather_multiplier(weather_info["condition"]) >= 1.7
