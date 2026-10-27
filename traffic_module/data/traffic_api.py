from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
import os

from traffic_route_integration import calculate_traffic_route


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Bengaluru Brain Traffic API",
    description="Full Bengaluru traffic prediction and route API",
    version="1.0.0"
)


# ============================================================
# CORS CONFIGURATION
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ============================================================
# FILE CONFIGURATION
# ============================================================

LIVE_FILE = "live_traffic_history.csv"

PREDICTIONS_FILE = "latest_traffic_predictions.csv"


# ============================================================
# BENGALURU LOCATIONS
# ============================================================

BENGALURU_LOCATIONS = {

    "hebbal":
        [13.0358, 77.5970],

    "marathahalli":
        [12.9591, 77.6974],
    "marathalli":
        [12.9591, 77.6974],

    "new horizon college":
        [12.9676, 77.7150],

    "electronic city":
        [12.8440, 77.6757],

    "whitefield":
        [12.9698, 77.7500],

    "mg road":
        [12.9747, 77.6093],

    "indiranagar":
        [12.9742, 77.6414],

    "koramangala":
        [12.9352, 77.6245],

    "hsr layout":
        [12.9106, 77.6385],

    "bellandur":
        [12.9259, 77.6676],

    "sarjapur":
        [12.9236, 77.6762],

    "kr puram":
        [13.0167, 77.5537],

    "yelahanka":
        [13.0996, 77.5866],

    "silk board":
        [12.9177, 77.6238],

    "manyata tech park":
        [13.0450, 77.6200],

}


# ============================================================
# REQUEST MODEL
# ============================================================

class RouteRequest(BaseModel):

    source_lat: float

    source_lon: float

    destination_lat: float

    destination_lon: float


# ============================================================
# LOCATION LOOKUP
# ============================================================

def get_location_coordinates(location):

    if not location:

        raise HTTPException(
            status_code=400,
            detail="Location cannot be empty."
        )

    location = str(
        location
    ).lower().strip()

    for name, coordinates in BENGALURU_LOCATIONS.items():

        if (
            location == name
            or location in name
            or name in location
        ):

            return coordinates

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unknown Bengaluru location: "
            f"{location}"
        )
    )


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():

    return {

        "application":
            "Bengaluru Brain",

        "service":
            "Bengaluru Traffic Prediction API",

        "version":
            "1.0.0",

        "status":
            "running",

        "endpoints": [

            "/",

            "/health",

            "/live-traffic",

            "/predictions",

            "/traffic-route",

            "/predict-route"

        ]

    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {

        "status":
            "healthy",

        "service":
            "Bengaluru Brain Traffic API",

        "timestamp":
            datetime.now().isoformat()

    }


# ============================================================
# LIVE TRAFFIC ENDPOINT
# ============================================================

@app.get("/live-traffic")
def live_traffic():

    if not os.path.exists(
        LIVE_FILE
    ):

        raise HTTPException(
            status_code=404,
            detail="Live traffic data not found."
        )

    try:

        df = pd.read_csv(
            LIVE_FILE
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not read live traffic data: "
                f"{error}"
            )
        )

    if df.empty:

        raise HTTPException(
            status_code=404,
            detail="No live traffic data available."
        )

    # --------------------------------------------------------
    # Convert timestamp
    # --------------------------------------------------------

    if "timestamp" in df.columns:

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Keep successful observations
    # --------------------------------------------------------

    if "status" in df.columns:

        df = df[
            df["status"]
            .astype(str)
            .str.upper()
            .eq("OK")
        ].copy()

    if df.empty:

        raise HTTPException(
            status_code=404,
            detail=(
                "No successful live traffic "
                "observations available."
            )
        )

    # --------------------------------------------------------
    # Latest observation per location
    # --------------------------------------------------------

    latest = (
        df
        .sort_values("timestamp")
        .groupby(
            "traffic_location"
        )
        .tail(1)
        .copy()
    )

    latest["timestamp"] = (
        latest["timestamp"]
        .astype(str)
    )

    # Convert NaN to None

    latest = latest.where(
        pd.notna(latest),
        None
    )

    return {

        "count":
            len(latest),

        "locations":
            latest.to_dict(
                orient="records"
            )

    }


# ============================================================
# PREDICTIONS ENDPOINT
# ============================================================

@app.get("/predictions")
def predictions():

    if not os.path.exists(
        PREDICTIONS_FILE
    ):

        raise HTTPException(
            status_code=404,
            detail=(
                "Prediction file not found."
            )
        )

    try:

        df = pd.read_csv(
            PREDICTIONS_FILE
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not read prediction data: "
                f"{error}"
            )
        )

    if df.empty:

        raise HTTPException(
            status_code=404,
            detail="No predictions available."
        )

    df = df.where(
        pd.notna(df),
        None
    )

    return {

        "count":
            len(df),

        "predictions":
            df.to_dict(
                orient="records"
            )

    }


# ============================================================
# TRAFFIC-AWARE ROUTE ENDPOINT
# ============================================================

@app.post("/traffic-route")
def traffic_route(
    request: RouteRequest
):

    try:

        result = calculate_traffic_route(

            source_lat=
                request.source_lat,

            source_lon=
                request.source_lon,

            destination_lat=
                request.destination_lat,

            destination_lon=
                request.destination_lon

        )

        return {

            "distance_km":
                round(
                    result["distance_km"],
                    2
                ),

            "base_travel_time_min":
                round(
                    result[
                        "base_travel_time_min"
                    ],
                    2
                ),

            "current_travel_time_min":
                round(
                    result[
                        "current_travel_time_min"
                    ],
                    2
                ),

            "predicted_travel_time_min":
                round(
                    result[
                        "predicted_travel_time_min"
                    ],
                    2
                ),

            "delay_min":
                round(
                    result["delay_min"],
                    2
                ),

            "base_speed_kmh":
                round(
                    result[
                        "base_speed_kmh"
                    ],
                    2
                ),

            "current_speed_kmh":
                round(
                    result[
                        "current_speed_kmh"
                    ],
                    2
                ),

            "predicted_speed_kmh":
                round(
                    result[
                        "predicted_speed_kmh"
                    ],
                    2
                ),

            "delay_percent":
                round(
                    result[
                        "delay_percent"
                    ],
                    2
                ),

            "traffic_status":
                result[
                    "traffic_status"
                ],

            "confidence":
                round(
                    result[
                        "confidence"
                    ],
                    3
                ),

            "road_names":
                result[
                    "road_names"
                ],

            "traffic_points":
                result[
                    "traffic_points"
                ]

        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# FRONTEND PREDICT-ROUTE ENDPOINT
# ============================================================

@app.post("/predict-route")
def predict_route(
    request: dict
):

    # --------------------------------------------------------
    # Read source and destination
    # --------------------------------------------------------

    source = request.get(
        "source"
    )

    destination = request.get(
        "destination"
    )

    if not source:

        raise HTTPException(
            status_code=400,
            detail="source is required."
        )

    if not destination:

        raise HTTPException(
            status_code=400,
            detail="destination is required."
        )

    # --------------------------------------------------------
    # Convert location names to coordinates
    # --------------------------------------------------------

    source_coords = (
        get_location_coordinates(
            source
        )
    )

    destination_coords = (
        get_location_coordinates(
            destination
        )
    )

    # --------------------------------------------------------
    # Calculate traffic-aware route
    # --------------------------------------------------------

    try:

        result = calculate_traffic_route(

            source_lat=
                source_coords[0],

            source_lon=
                source_coords[1],

            destination_lat=
                destination_coords[0],

            destination_lon=
                destination_coords[1]

        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    # --------------------------------------------------------
    # Return result to React frontend
    # --------------------------------------------------------

    return {

        "source":
            source,

        "destination":
            destination,

        "source_coords":
            source_coords,

        "destination_coords":
            destination_coords,

        "distance_km":
            round(
                result[
                    "distance_km"
                ],
                2
            ),

        "base_travel_time_min":
            round(
                result[
                    "base_travel_time_min"
                ],
                2
            ),

        "current_travel_time_min":
            round(
                result[
                    "current_travel_time_min"
                ],
                2
            ),

        "predicted_travel_time_min":
            round(
                result[
                    "predicted_travel_time_min"
                ],
                2
            ),

        "delay_min":
            round(
                result[
                    "delay_min"
                ],
                2
            ),

        "avg_speed":
            round(
                result[
                    "predicted_speed_kmh"
                ],
                2
            ),

        "current_speed":
            round(
                result[
                    "current_speed_kmh"
                ],
                2
            ),

        "predicted_speed":
            round(
                result[
                    "predicted_speed_kmh"
                ],
                2
            ),

        "traffic":
            result[
                "traffic_status"
            ],

        "confidence":
            round(
                result[
                    "confidence"
                ],
                3
            ),

        "road_names":
            result[
                "road_names"
            ],

        "traffic_points":
            result[
                "traffic_points"
            ]

    }