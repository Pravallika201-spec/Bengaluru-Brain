BENGALURU_LOCATIONS = {
    "hebbal": [13.0358, 77.5970],
    "marathahalli": [12.9591, 77.6974],
    "new horizon college": [12.9676, 77.7150],
    "electronic city": [12.8440, 77.6757],
    "whitefield": [12.9698, 77.7500],
    "mg road": [12.9747, 77.6093],
    "indiranagar": [12.9742, 77.6414],
    "koramangala": [12.9352, 77.6245],
    "hsr layout": [12.9106, 77.6385],
    "bellandur": [12.9259, 77.6676],
    "sarjapur": [12.9236, 77.6762],
    "kr puram": [13.0167, 77.5537],
    "yelahanka": [13.0996, 77.5866],
    "silk board": [12.9177, 77.6238],
    "manyata tech park": [13.0450, 77.6200],
}
def get_location_coordinates(location):

    if not isinstance(location, str):
        raise HTTPException(
            status_code=400,
            detail="Location must be a text value"
        )

    # Normalize user input
    location = location.strip().casefold()

    for name, coords in BENGALURU_LOCATIONS.items():

        normalized_name = name.strip().casefold()

        if (
            location == normalized_name
            or location in normalized_name
            or normalized_name in location
        ):
            return coords

    raise HTTPException(
        status_code=400,
        detail=f"Unknown Bengaluru location: {location}"
    )

def predict_route(request: dict):

    source = request.get("source")
    destination = request.get("destination")

    if not source or not destination:

        raise HTTPException(
            status_code=400,
            detail="source and destination are required"
        )

    source_coords = get_location_coordinates(
        source
    )

    destination_coords = get_location_coordinates(
        destination
    )

    result = calculate_traffic_route(

        source_lat=source_coords[0],
        source_lon=source_coords[1],

        destination_lat=destination_coords[0],
        destination_lon=destination_coords[1]

    )

    # Keep the response compatible with
    # the existing frontend.

    return {
        "source": source,
        "destination": destination,

        "source_coords":
            source_coords,

        "destination_coords":
            destination_coords,

        "distance_km":
            result["distance_km"],

        "base_travel_time_min":
            result["base_travel_time_min"],

        "current_travel_time_min":
            result["current_travel_time_min"],

        "predicted_travel_time_min":
            result["predicted_travel_time_min"],

        "delay_min":
            result["delay_min"],

        "avg_speed":
            result["predicted_speed_kmh"],

        "traffic":
            result["traffic_status"],

        "confidence":
            result["confidence"],

        "road_names":
            result["road_names"],

        "traffic_points":
            result["traffic_points"]
    }