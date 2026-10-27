"""
=========================================================
Urban Predictive Intelligence System
Simple REST API (No Optional Dependencies)
=========================================================

A simplified version that works with only core dependencies.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uvicorn

# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="Urban Predictive Intelligence API",
    version="2.0.0",
    description="Simplified API for urban waste management intelligence",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# PYDANTIC MODELS
# =========================================================

class PredictionRequest(BaseModel):
    grid_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    forecast_days: int = 7

class PredictionResponse(BaseModel):
    grid_id: str
    latitude: float
    longitude: float
    predictions: list
    risk_assessment: dict
    collection_priority: int
    confidence_score: float
    generated_at: datetime

# =========================================================
# API ENDPOINTS
# =========================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "note": "Simplified API - core functionality only"
    }

@app.post("/api/v2/predictions", response_model=PredictionResponse)
async def get_predictions(request: PredictionRequest):
    """Get waste predictions (demo version)."""
    # Generate demo predictions
    grid_id = request.grid_id or "BG_000001"
    latitude = request.latitude or 12.9716
    longitude = request.longitude or 77.5946
    
    predictions = []
    for day in range(1, request.forecast_days + 1):
        predictions.append({
            'forecast_day': day,
            'predicted_waste_kg': 1000 + day * 50,
            'risk': 'MEDIUM' if day < 5 else 'HIGH',
            'confidence': 0.85
        })
    
    return PredictionResponse(
        grid_id=grid_id,
        latitude=latitude,
        longitude=longitude,
        predictions=predictions,
        risk_assessment={'current_risk': 'MEDIUM', 'risk_percentile': 60},
        collection_priority=2,
        confidence_score=0.85,
        generated_at=datetime.now()
    )

@app.get("/api/v2/analytics/summary")
async def get_analytics_summary():
    """Get system-wide analytics summary (demo version)."""
    return {
        "total_predictions": 3053,
        "grid_count": 3053,
        "upcoming_events": 5,
        "high_risk_grids": 250,
        "generated_at": datetime.now().isoformat(),
        "note": "Demo data - requires full system for real analytics"
    }

@app.get("/api/v2/events")
async def get_events():
    """Get upcoming events (demo version)."""
    return {
        "events": [
            {
                "event_id": "EVT001",
                "event_name": "Bengaluru Tech Summit",
                "event_type": "conference",
                "start_datetime": "2024-09-15T09:00:00",
                "predicted_waste_impact": 1.3
            }
        ],
        "count": 1,
        "generated_at": datetime.now().isoformat(),
        "note": "Demo data - requires full system for real events"
    }

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    """Run the FastAPI server."""
    print("=" * 70)
    print("URBAN PREDICTIVE INTELLIGENCE API (SIMPLIFIED)")
    print("=" * 70)
    
    print(f"API Version: 2.0.0")
    print(f"Documentation: http://localhost:8000/docs")
    print(f"Alternative Docs: http://localhost:8000/redoc")
    
    print("\nAvailable Endpoints:")
    print("  GET  /health")
    print("  POST /api/v2/predictions")
    print("  GET  /api/v2/analytics/summary")
    print("  GET  /api/v2/events")
    
    print("\nNote: This is a simplified version with demo data.")
    print("For full functionality, install all dependencies and run the full API.")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()