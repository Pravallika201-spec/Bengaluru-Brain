"""
Bengaluru Brain - NAMMA FLOW Traffic Prediction API
Main FastAPI application with all endpoints

*** DEPRECATED — DO NOT RUN THIS FILE ***
app.py is now the single canonical backend. This file's /api/ward-stress,
/api/incidents and /api/shift-timers endpoints reference an undefined
`predictor` object and would 500 if ever started — that bug predates this
notice (verified during the Phase 1 audit); it's left unfixed here because
the working replacements now live in app.py:
  - /api/locations, /api/ward-stress, /api/shift-timers, /api/weather,
    /api/city-summary, /api/health  -> ported into app.py (fixed).
  - /api/incidents                  -> use app.py's /api/incident/list
    instead (backed by incident_service.py, not the broken `predictor`).
Kept in the repo for reference only, per the project rule against deleting
existing code without cause.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from traffic_predictor import predict_route
from location_data import BENGALURU_LOCATIONS, get_all_locations
from ward_stress import generate_ward_stress_data, get_citywide_stress_summary
from it_shift_logic import get_next_shift_change
from weather_logic import get_live_weather

# Initialize FastAPI app
app = FastAPI(
    title="Bengaluru Brain - NAMMA FLOW API",
    description="Traffic Intelligence System for Bengaluru Urban Predictive Intelligence Platform",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class RouteRequest(BaseModel):
    source: str
    destination: str
    datetime: Optional[str] = None
    weather: Optional[str] = None

class RouteResponse(BaseModel):
    route: str
    current_status: str
    congestion_score: float
    estimated_delay_minutes: int
    estimated_travel_time_minutes: int
    normal_travel_time_minutes: int
    factors: dict
    forecast_2hr: dict
    affected_wards: List[int]
    cascade_risk: str
    alert_message: str
    alternative_route: Optional[str]

class LocationInfo(BaseModel):
    name: str
    lat: float
    lon: float
    ward: int
    it_zone: bool

class WardStress(BaseModel):
    ward_id: int
    ward_name: str
    traffic_score: int
    status: str
    color: str

class Incident(BaseModel):
    id: int
    type: str
    location: str
    ward: int
    severity: str
    reported_at: str
    lat: float
    lon: float


@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "message": "BENGALURU BRAIN - NAMMA FLOW API",
        "status": "ACTIVE",
        "version": "2.0.0",
        "description": "Traffic Intelligence System for Bengaluru",
        "endpoints": [
            "/api/predict",
            "/api/locations",
            "/api/ward-stress",
            "/api/incidents",
            "/api/shift-timers",
            "/api/weather",
            "/api/city-summary"
        ],
        "timestamp": datetime.now().isoformat()
    }

class PredictRequest(BaseModel):
    source: str
    destination: str
    weather: str = "clear"

@app.post("/api/predict")
async def predict(req: PredictRequest):
    try:
        result = predict_route(
            req.source,
            req.destination,
            req.weather
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/locations", response_model=List[LocationInfo])
async def get_locations():
    """
    Get all available Bengaluru locations
    
    Returns:
        List of all locations with coordinates and ward information
    """
    try:
        locations = []
        for name, info in BENGALURU_LOCATIONS.items():
            locations.append(LocationInfo(
                name=name,
                lat=info["lat"],
                lon=info["lon"],
                ward=info["ward"],
                it_zone=info["it_zone"]
            ))
        return locations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get locations: {str(e)}")

@app.get("/api/ward-stress", response_model=List[WardStress])
async def get_ward_stress():
    """
    Get stress data for all Bengaluru wards
    
    Returns:
        List of all wards with traffic stress scores and status
    """
    try:
        ward_data = predictor.get_ward_stress_data()
        return [WardStress(**ward) for ward in ward_data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ward stress data: {str(e)}")

@app.get("/api/incidents", response_model=List[Incident])
async def get_incidents():
    """
    Get active traffic incidents
    
    Returns:
        List of current traffic incidents with location and severity
    """
    try:
        incidents = predictor.get_incidents()
        return [Incident(**incident) for incident in incidents]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get incidents: {str(e)}")

@app.get("/api/shift-timers")
async def get_shift_timers():
    """
    Get IT park shift countdown timers
    
    Returns:
        List of upcoming IT shift changes with countdown
    """
    try:
        timers = predictor.get_shift_timers()
        return {
            "shift_timers": timers,
            "next_shift_change": get_next_shift_change(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get shift timers: {str(e)}")

@app.get("/api/weather")
async def get_weather():
    """
    Get current weather information
    
    Returns:
        Current weather data with traffic impact
    """
    try:
        weather_data = get_live_weather()
        return {
            "weather": weather_data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get weather data: {str(e)}")

@app.get("/api/city-summary")
async def get_city_summary():
    """
    Get citywide traffic summary
    
    Returns:
        Overall traffic status and statistics for Bengaluru
    """
    try:
        summary = get_citywide_stress_summary()
        return {
            "city_summary": summary,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get city summary: {str(e)}")

@app.get("/api/health")
async def health_check():
    """
    Health check endpoint
    
    Returns:
        API health status and system information
    """
    try:
        return {
            "status": "HEALTHY",
            "api_version": "2.0.0",
            "services": {
                "traffic_predictor": "ACTIVE",
                "ward_stress": "ACTIVE",
                "weather_api": "ACTIVE",
                "shift_logic": "ACTIVE"
            },
            "locations_count": len(BENGALURU_LOCATIONS),
            "wards_count": 369,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

# Legacy endpoints for backward compatibility
@app.post("/predict-route")
async def legacy_predict_route(req: PredictRequest):
    """
    Frontend-compatible route prediction endpoint.
    Accepts JSON:
    {
        "source": "Hebbal",
        "destination": "Marathahalli"
    }
    """

    try:
        result = predict_route(
            req.source,
            req.destination,
            req.weather
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )
@app.get("/locations")
async def legacy_get_locations():
    """
    Legacy locations endpoint (backward compatibility)
    """
    try:
        return get_all_locations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get locations: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting Bengaluru Brain - NAMMA FLOW API...")
    print("📍 Available endpoints:")
    print("   • POST /api/predict - Main prediction endpoint")
    print("   • GET /api/locations - All locations")
    print("   • GET /api/ward-stress - Ward stress data")
    print("   • GET /api/incidents - Active incidents")
    print("   • GET /api/shift-timers - IT shift timers")
    print("   • GET /api/weather - Current weather")
    print("   • GET /api/city-summary - Citywide summary")
    print("   • GET /api/health - Health check")
    print("\n🚀 Server starting on http://localhost:8000")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
