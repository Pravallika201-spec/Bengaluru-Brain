"""
=========================================================
Urban Predictive Intelligence System
Real-time Weather Integration Module
=========================================================

Integrates real-time weather data from multiple APIs:
- OpenWeatherMap API
- Open-Meteo API (free, no API key required)
- Weather impact modeling on waste generation
- Seasonal pattern adjustment based on weather
- Extreme weather event detection

Replaces the empty weather module with full implementation.
=========================================================
"""

import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
CACHE_DIR = PROJECT_ROOT / "cache"
CONFIG_FILE = PROJECT_ROOT / "waste_module" / "config.py"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Weather API Configuration
WEATHER_CONFIG = {
    'open_meteo': {
        'base_url': 'https://api.open-meteo.com/v1/forecast',
        'timeout': 30,
        'use_free_tier': True  # Open-Meteo is free
    },
    'openweathermap': {
        'base_url': 'https://api.openweathermap.org/data/2.5',
        'api_key': os.getenv('OPENWEATHER_API_KEY', ''),
        'timeout': 30
    }
}

# Try to import optional dependencies
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("TextBlob not available - sentiment analysis disabled")

# Bengaluru coordinates
BENGALURU_COORDS = {
    'lat': 12.9716,
    'lon': 77.5946
}

# Weather impact factors on waste generation
WEATHER_IMPACT_FACTORS = {
    'temperature': {
        'extreme_hot_threshold': 35,  # Celsius
        'extreme_cold_threshold': 15,
        'optimal_range': (20, 30),
        'hot_impact': 1.15,  # 15% increase in extreme heat
        'cold_impact': 0.90,  # 10% decrease in cold
    },
    'precipitation': {
        'heavy_rain_threshold': 10,  # mm per day
        'moderate_rain_threshold': 5,
        'light_rain_threshold': 1,
        'heavy_rain_impact': 0.85,  # 15% decrease (people stay indoors)
        'moderate_rain_impact': 0.95,
        'light_rain_impact': 1.0,
    },
    'humidity': {
        'high_humidity_threshold': 80,  # %
        'low_humidity_threshold': 30,
        'high_humidity_impact': 1.05,  # 5% increase
        'low_humidity_impact': 0.98,
    },
    'wind': {
        'strong_wind_threshold': 20,  # km/h
        'strong_wind_impact': 1.10,  # 10% increase (more debris)
    }
}

# =========================================================
# OPEN-METEO API INTEGRATION (Free, no API key required)
# =========================================================

class OpenMeteoWeatherAPI:
    """Open-Meteo weather API integration (free tier)."""
    
    def __init__(self, config: Dict = None):
        self.config = config or WEATHER_CONFIG['open_meteo']
        self.base_url = self.config['base_url']
        self.timeout = self.config['timeout']
    
    def get_current_weather(self, lat: float, lon: float) -> Dict:
        """Get current weather data."""
        params = {
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
            'timezone': 'auto'
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if 'current' in data:
                return {
                    'source': 'open-meteo',
                    'timestamp': datetime.now(),
                    'temperature_c': data['current'].get('temperature_2m'),
                    'humidity_percent': data['current'].get('relative_humidity_2m'),
                    'precipitation_mm': data['current'].get('precipitation', 0),
                    'wind_speed_kmh': data['current'].get('wind_speed_10m', 0),
                    'raw_data': data
                }
            else:
                return None
                
        except Exception as e:
            print(f"Error fetching Open-Meteo weather: {e}")
            return None
    
    def get_forecast(self, lat: float, lon: float, days: int = 7) -> List[Dict]:
        """Get weather forecast for specified days."""
        params = {
            'latitude': lat,
            'longitude': lon,
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean',
            'timezone': 'auto',
            'forecast_days': days
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            forecast_data = []
            if 'daily' in data:
                daily = data['daily']
                for i in range(len(daily.get('time', []))):
                    forecast_data.append({
                        'source': 'open-meteo',
                        'date': daily['time'][i],
                        'temperature_max_c': daily['temperature_2m_max'][i],
                        'temperature_min_c': daily['temperature_2m_min'][i],
                        'precipitation_mm': daily['precipitation_sum'][i],
                        'wind_speed_max_kmh': daily['wind_speed_10m_max'][i],
                        'humidity_mean_percent': daily['relative_humidity_2m_mean'][i]
                    })
            
            return forecast_data
            
        except Exception as e:
            print(f"Error fetching Open-Meteo forecast: {e}")
            return []

# =========================================================
# OPENWEATHERMAP API INTEGRATION (Requires API key)
# =========================================================

class OpenWeatherMapAPI:
    """OpenWeatherMap API integration."""
    
    def __init__(self, config: Dict = None):
        self.config = config or WEATHER_CONFIG['openweathermap']
        self.base_url = self.config['base_url']
        self.api_key = self.config['api_key']
        self.timeout = self.config['timeout']
    
    def get_current_weather(self, lat: float, lon: float) -> Optional[Dict]:
        """Get current weather data."""
        if not self.api_key:
            print("OpenWeatherMap API key not configured")
            return None
        
        url = f"{self.base_url}/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': 'metric'
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            return {
                'source': 'openweathermap',
                'timestamp': datetime.now(),
                'temperature_c': data['main']['temp'],
                'humidity_percent': data['main']['humidity'],
                'precipitation_mm': data.get('rain', {}).get('1h', 0) + data.get('snow', {}).get('1h', 0),
                'wind_speed_kmh': data['wind']['speed'] * 3.6,  # Convert m/s to km/h
                'description': data['weather'][0]['description'],
                'raw_data': data
            }
            
        except Exception as e:
            print(f"Error fetching OpenWeatherMap weather: {e}")
            return None
    
    def get_forecast(self, lat: float, lon: float, days: int = 5) -> List[Dict]:
        """Get weather forecast."""
        if not self.api_key:
            print("OpenWeatherMap API key not configured")
            return []
        
        url = f"{self.base_url}/forecast"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': 'metric',
            'cnt': days * 8  # 8 forecasts per day (3-hour intervals)
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            forecast_data = []
            for item in data['list']:
                forecast_data.append({
                    'source': 'openweathermap',
                    'datetime': datetime.fromtimestamp(item['dt']),
                    'temperature_c': item['main']['temp'],
                    'humidity_percent': item['main']['humidity'],
                    'precipitation_mm': item.get('rain', {}).get('3h', 0) + item.get('snow', {}).get('3h', 0),
                    'wind_speed_kmh': item['wind']['speed'] * 3.6,
                    'description': item['weather'][0]['description']
                })
            
            return forecast_data
            
        except Exception as e:
            print(f"Error fetching OpenWeatherMap forecast: {e}")
            return []

# =========================================================
# WEATHER IMPACT ANALYZER
# =========================================================

class WeatherImpactAnalyzer:
    """Analyze weather impact on waste generation."""
    
    def __init__(self, impact_factors: Dict = None):
        self.impact_factors = impact_factors or WEATHER_IMPACT_FACTORS
    
    def calculate_temperature_impact(self, temp_c: float) -> float:
        """Calculate temperature impact factor."""
        temp_config = self.impact_factors['temperature']
        
        if temp_c >= temp_config['extreme_hot_threshold']:
            return temp_config['hot_impact']
        elif temp_c <= temp_config['extreme_cold_threshold']:
            return temp_config['cold_impact']
        elif temp_config['optimal_range'][0] <= temp_c <= temp_config['optimal_range'][1]:
            return 1.0
        else:
            # Linear interpolation for intermediate temperatures
            if temp_c < temp_config['optimal_range'][0]:
                factor = temp_config['cold_impact'] + (1.0 - temp_config['cold_impact']) * \
                        ((temp_c - temp_config['extreme_cold_threshold']) / 
                         (temp_config['optimal_range'][0] - temp_config['extreme_cold_threshold']))
            else:
                factor = 1.0 + (temp_config['hot_impact'] - 1.0) * \
                        ((temp_c - temp_config['optimal_range'][1]) / 
                         (temp_config['extreme_hot_threshold'] - temp_config['optimal_range'][1]))
            return max(min(factor, 1.2), 0.8)
    
    def calculate_precipitation_impact(self, precipitation_mm: float) -> float:
        """Calculate precipitation impact factor."""
        precip_config = self.impact_factors['precipitation']
        
        if precipitation_mm >= precip_config['heavy_rain_threshold']:
            return precip_config['heavy_rain_impact']
        elif precipitation_mm >= precip_config['moderate_rain_threshold']:
            return precip_config['moderate_rain_impact']
        elif precipitation_mm >= precip_config['light_rain_threshold']:
            return precip_config['light_rain_impact']
        else:
            return 1.0
    
    def calculate_humidity_impact(self, humidity_percent: float) -> float:
        """Calculate humidity impact factor."""
        humidity_config = self.impact_factors['humidity']
        
        if humidity_percent >= humidity_config['high_humidity_threshold']:
            return humidity_config['high_humidity_impact']
        elif humidity_percent <= humidity_config['low_humidity_threshold']:
            return humidity_config['low_humidity_impact']
        else:
            return 1.0
    
    def calculate_wind_impact(self, wind_speed_kmh: float) -> float:
        """Calculate wind impact factor."""
        wind_config = self.impact_factors['wind']
        
        if wind_speed_kmh >= wind_config['strong_wind_threshold']:
            return wind_config['strong_wind_impact']
        else:
            return 1.0
    
    def calculate_total_impact(self, weather_data: Dict) -> Dict:
        """Calculate total weather impact on waste generation."""
        temp_c = weather_data.get('temperature_c', 25)
        precipitation_mm = weather_data.get('precipitation_mm', 0)
        humidity_percent = weather_data.get('humidity_percent', 50)
        wind_speed_kmh = weather_data.get('wind_speed_kmh', 10)
        
        temp_impact = self.calculate_temperature_impact(temp_c)
        precip_impact = self.calculate_precipitation_impact(precipitation_mm)
        humidity_impact = self.calculate_humidity_impact(humidity_percent)
        wind_impact = self.calculate_wind_impact(wind_speed_kmh)
        
        # Combined impact (weighted average)
        total_impact = (
            0.35 * temp_impact +
            0.30 * precip_impact +
            0.20 * humidity_impact +
            0.15 * wind_impact
        )
        
        return {
            'temperature_impact': temp_impact,
            'precipitation_impact': precip_impact,
            'humidity_impact': humidity_impact,
            'wind_impact': wind_impact,
            'total_impact': total_impact,
            'weather_conditions': self.classify_weather_conditions(weather_data),
            'extreme_weather_alert': self.detect_extreme_weather(weather_data)
        }
    
    def classify_weather_conditions(self, weather_data: Dict) -> str:
        """Classify overall weather conditions."""
        temp_c = weather_data.get('temperature_c', 25)
        precipitation_mm = weather_data.get('precipitation_mm', 0)
        
        if precipitation_mm >= 10:
            return "Heavy Rain"
        elif precipitation_mm >= 5:
            return "Moderate Rain"
        elif precipitation_mm >= 1:
            return "Light Rain"
        elif temp_c >= 35:
            return "Extreme Heat"
        elif temp_c <= 15:
            return "Cold"
        else:
            return "Normal"
    
    def detect_extreme_weather(self, weather_data: Dict) -> bool:
        """Detect extreme weather conditions."""
        temp_c = weather_data.get('temperature_c', 25)
        precipitation_mm = weather_data.get('precipitation_mm', 0)
        wind_speed_kmh = weather_data.get('wind_speed_kmh', 10)
        
        return (
            temp_c >= 35 or
            temp_c <= 10 or
            precipitation_mm >= 15 or
            wind_speed_kmh >= 30
        )

# =========================================================
# WEATHER DATA MANAGER
# =========================================================

class WeatherDataManager:
    """Manage weather data collection and storage."""
    
    def __init__(self):
        self.open_meteo = OpenMeteoWeatherAPI()
        self.openweathermap = OpenWeatherMapAPI()
        self.impact_analyzer = WeatherImpactAnalyzer()
        self.cache_file = CACHE_DIR / "weather_cache.json"
    
    def get_current_weather_with_fallback(self, lat: float, lon: float) -> Dict:
        """Get current weather with API fallback."""
        # Try Open-Meteo first (free, no API key)
        weather_data = self.open_meteo.get_current_weather(lat, lon)
        
        if weather_data is None:
            # Fallback to OpenWeatherMap if API key is available
            weather_data = self.openweathermap.get_current_weather(lat, lon)
        
        return weather_data
    
    def get_forecast_with_fallback(self, lat: float, lon: float, days: int = 7) -> List[Dict]:
        """Get weather forecast with API fallback."""
        # Try Open-Meteo first
        forecast_data = self.open_meteo.get_forecast(lat, lon, days)
        
        if not forecast_data:
            # Fallback to OpenWeatherMap
            forecast_data = self.openweathermap.get_forecast(lat, lon, min(days, 5))
        
        return forecast_data
    
    def cache_weather_data(self, weather_data: Dict, forecast_data: List[Dict]) -> None:
        """Cache weather data for future use."""
        cache = {
            'current_weather': weather_data,
            'forecast': forecast_data,
            'cached_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(hours=1)).isoformat()
        }
        
        with open(self.cache_file, 'w') as f:
            json.dump(cache, f, indent=2, default=str)
    
    def load_cached_weather(self) -> Optional[Dict]:
        """Load cached weather data if still valid."""
        if not self.cache_file.exists():
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            
            expires_at = datetime.fromisoformat(cache['expires_at'])
            if datetime.now() < expires_at:
                return cache
            else:
                return None
        except Exception as e:
            print(f"Error loading cached weather: {e}")
            return None
    
    def get_weather_impact_for_grid(self, grid_data: Dict, forecast_day: int = 0) -> Dict:
        """Get weather impact for a specific grid."""
        lat = grid_data.get('Latitude', BENGALURU_COORDS['lat'])
        lon = grid_data.get('Longitude', BENGALURU_COORDS['lon'])
        
        # Get weather data
        if forecast_day == 0:
            weather_data = self.get_current_weather_with_fallback(lat, lon)
        else:
            forecast = self.get_forecast_with_fallback(lat, lon, forecast_day + 1)
            if forecast and forecast_day < len(forecast):
                weather_data = forecast[forecast_day]
            else:
                weather_data = None
        
        if weather_data is None:
            # Return default impact if weather data unavailable
            return {
                'temperature_impact': 1.0,
                'precipitation_impact': 1.0,
                'humidity_impact': 1.0,
                'wind_impact': 1.0,
                'total_impact': 1.0,
                'weather_conditions': 'Unknown',
                'extreme_weather_alert': False
            }
        
        # Calculate impact
        impact = self.impact_analyzer.calculate_total_impact(weather_data)
        
        return impact
    
    def collect_city_weather_data(self) -> Dict:
        """Collect comprehensive weather data for the city."""
        print("Collecting weather data for Bengaluru...")
        
        # Try to load from cache first
        cached_data = self.load_cached_weather()
        if cached_data:
            print("Using cached weather data")
            return cached_data
        
        # Collect fresh data
        current_weather = self.get_current_weather_with_fallback(
            BENGALURU_COORDS['lat'], 
            BENGALURU_COORDS['lon']
        )
        
        forecast = self.get_forecast_with_fallback(
            BENGALURU_COORDS['lat'], 
            BENGALURU_COORDS['lon'],
            days=7
        )
        
        # Cache the data
        self.cache_weather_data(current_weather, forecast)
        
        return {
            'current_weather': current_weather,
            'forecast': forecast,
            'collected_at': datetime.now().isoformat()
        }

# =========================================================
# WEATHER-AWARE WASTE PREDICTION INTEGRATION
# =========================================================

def integrate_weather_with_predictions(predictions_df: pd.DataFrame, weather_manager: WeatherDataManager) -> pd.DataFrame:
    """Integrate weather impacts into waste predictions."""
    print("Integrating weather impacts with waste predictions...")
    
    # Collect weather data
    weather_data = weather_manager.collect_city_weather_data()
    
    # Add weather impacts to predictions
    weather_impacts = []
    
    for idx, row in predictions_df.iterrows():
        grid_info = {
            'Latitude': row['Latitude'],
            'Longitude': row['Longitude']
        }
        
        forecast_day = row.get('forecast_day', 0) - 1
        impact = weather_manager.get_weather_impact_for_grid(grid_info, forecast_day)
        weather_impacts.append(impact)
    
    # Add weather impact columns
    weather_impact_df = pd.DataFrame(weather_impacts)
    
    for col in weather_impact_df.columns:
        predictions_df[f'weather_{col}'] = weather_impact_df[col]
    
    # Adjust predictions based on weather impact
    predictions_df['weather_adjusted_prediction'] = (
        predictions_df['ensemble_prediction'] * predictions_df['weather_total_impact']
    )
    
    # Recalculate risk with weather consideration
    predictions_df['weather_adjusted_risk_percentile'] = predictions_df.groupby('forecast_day')['weather_adjusted_prediction'].transform(
        lambda x: x.rank(pct=True) * 100
    )
    
    def weather_aware_risk(row):
        base_risk = row['advanced_risk']
        weather_alert = row['weather_extreme_weather_alert']
        
        if weather_alert and base_risk in ['MEDIUM', 'LOW']:
            return 'HIGH'
        elif weather_alert and base_risk == 'HIGH':
            return 'CRITICAL'
        else:
            return base_risk
    
    predictions_df['weather_aware_risk'] = predictions_df.apply(weather_aware_risk, axis=1)
    
    return predictions_df

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("REAL-TIME WEATHER INTEGRATION MODULE")
    print("=" * 70)
    
    # Initialize weather manager
    weather_manager = WeatherDataManager()
    
    # Collect weather data
    weather_data = weather_manager.collect_city_weather_data()
    
    print("\nCurrent Weather:")
    if weather_data['current_weather']:
        current = weather_data['current_weather']
        print(f"  Temperature: {current.get('temperature_c', 'N/A')}°C")
        print(f"  Humidity: {current.get('humidity_percent', 'N/A')}%")
        print(f"  Precipitation: {current.get('precipitation_mm', 'N/A')} mm")
        print(f"  Wind Speed: {current.get('wind_speed_kmh', 'N/A')} km/h")
        print(f"  Source: {current.get('source', 'Unknown')}")
    else:
        print("  Unable to fetch current weather data")
    
    print("\nWeather Forecast (next 7 days):")
    if weather_data['forecast']:
        for day in weather_data['forecast'][:7]:
            date_str = day.get('date', 'Unknown')
            temp_max = day.get('temperature_max_c', 'N/A')
            temp_min = day.get('temperature_min_c', 'N/A')
            precip = day.get('precipitation_mm', 'N/A')
            print(f"  {date_str}: {temp_max}°C/{temp_min}°C, Precip: {precip}mm")
    else:
        print("  Unable to fetch forecast data")
    
    # Calculate weather impact
    if weather_data['current_weather']:
        impact = weather_manager.impact_analyzer.calculate_total_impact(weather_data['current_weather'])
        print("\nWeather Impact Analysis:")
        print(f"  Temperature Impact: {impact['temperature_impact']:.2f}")
        print(f"  Precipitation Impact: {impact['precipitation_impact']:.2f}")
        print(f"  Humidity Impact: {impact['humidity_impact']:.2f}")
        print(f"  Wind Impact: {impact['wind_impact']:.2f}")
        print(f"  Total Impact: {impact['total_impact']:.2f}")
        print(f"  Weather Conditions: {impact['weather_conditions']}")
        print(f"  Extreme Weather Alert: {impact['extreme_weather_alert']}")
    
    # Save weather data
    weather_file = DATA_DIR / "bengaluru_weather_data.json"
    with open(weather_file, 'w') as f:
        json.dump(weather_data, f, indent=2, default=str)
    
    print(f"\nWeather data saved to: {weather_file}")
    
    print("\n" + "=" * 70)
    print("WEATHER INTEGRATION COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()