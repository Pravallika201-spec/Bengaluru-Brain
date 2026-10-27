import os
from datetime import datetime


WEATHER_CODES = {
    "clear": 0,
    "light_rain": 1,
    "heavy_rain": 2,
    "storm": 3,
    "fog": 4,
}


def predict_route(source: str, destination: str, weather: str = "clear"):
    from app import get_route_details, get_weather_for_route, TomTomTrafficProvider, build_model_prediction, _build_traffic_points, classify_congestion_ratio, MODEL_CACHE

    route = get_route_details(source, destination)
    source_coords = route["source_coords"]
    destination_coords = route["destination_coords"]
    route_coords = route["route_coords"]
    distance_km = float(route["distance_km"])
    base_time_min = max(1.0, float(route["duration_min"]))
    weather_info = get_weather_for_route((source_coords[0] + destination_coords[0]) / 2.0, (source_coords[1] + destination_coords[1]) / 2.0)

    traffic_data = TomTomTrafficProvider().get_live_traffic({"route_coords": route_coords}) if os.getenv("TOMTOM_API_KEY") else None
    traffic_source = "LIVE" if traffic_data else "MODEL/HISTORICAL"
    if traffic_data:
        current_speed = float(traffic_data["current_speed_kmh"])
        free_flow_speed = float(traffic_data["free_flow_speed_kmh"]) if traffic_data.get("free_flow_speed_kmh") else max(current_speed, 40.0)
        current_time = max(1.0, (distance_km / max(current_speed, 1.0)) * 60.0)
        congestion_ratio = max(0.0, min(1.0, 1.0 - current_speed / max(free_flow_speed, 1.0)))
        traffic_status = classify_congestion_ratio(congestion_ratio)
        predicted_speed, model_score = build_model_prediction(distance_km, current_speed, weather_info)
        predicted_time = max(1.0, (distance_km / max(predicted_speed, 1.0)) * 60.0)
    else:
        current_speed = max(15.0, min(65.0, (distance_km / max(base_time_min, 1.0)) * 60.0))
        predicted_speed, model_score = build_model_prediction(distance_km, current_speed, weather_info)
        current_time = max(1.0, (distance_km / max(current_speed, 1.0)) * 60.0)
        predicted_time = max(1.0, (distance_km / max(predicted_speed, 1.0)) * 60.0)
        congestion_ratio = max(0.0, min(1.0, 1.0 - current_speed / 50.0))
        traffic_status = classify_congestion_ratio(congestion_ratio)
        traffic_source = "MODEL/HISTORICAL"

    if traffic_source == "LIVE":
        traffic_points = traffic_data.get("traffic_points", [])
    else:
        traffic_points = _build_traffic_points(route_coords, traffic_data={"traffic_points": []}, traffic_source=traffic_source)

    delay_min = max(0.0, predicted_time - base_time_min)
    confidence = 0.92 if traffic_source == "LIVE" else 0.62 if MODEL_CACHE else 0.51
    if MODEL_CACHE is not None:
        confidence = max(0.35, min(0.9, float(model_score)))

    result = {
        "source": source,
        "destination": destination,
        "distance_km": round(distance_km, 2),
        "predicted_travel_time_min": round(predicted_time, 1),
        "base_travel_time_min": round(base_time_min, 1),
        "current_travel_time_min": round(current_time, 1),
        "delay_min": round(delay_min, 1),
        "current_speed": round(current_speed, 1),
        "predicted_speed": round(predicted_speed, 1),
        "confidence": round(confidence, 3),
        "traffic": traffic_status,
        "traffic_source": traffic_source,
        "weather": {
            "condition": weather_info["condition"],
            "temperature_c": weather_info["temperature_c"],
            "humidity": weather_info["humidity"],
            "rain": weather_info["rain"],
            "wind_speed": weather_info["wind_speed"],
        },
        "source_coords": source_coords,
        "destination_coords": destination_coords,
        "route_coords": route_coords,
        "traffic_points": traffic_points,
        "road_names": route.get("road_names", []),
        "forecast_2hr": {
            "predicted_travel_time_min": round(predicted_time * 1.08, 1),
            "delay_min": round(max(0.0, predicted_time * 1.08 - base_time_min), 1),
            "status": traffic_status,
        },
        "model_info": "traffic_model_v2.pth loaded" if MODEL_CACHE else "GNN unavailable; using historical model fallback",
        "predicted_at": datetime.now().isoformat(),
        "status": traffic_status,
        "avg_speed_kmh": round(current_speed, 1),
    }
    return result
