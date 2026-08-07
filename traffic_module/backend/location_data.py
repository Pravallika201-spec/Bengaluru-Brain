"""
Bengaluru Locations Database
Contains all major Bengaluru locations with coordinates and ward IDs
"""

BENGALURU_LOCATIONS = {
    "Hebbal": {"lat": 13.035, "lon": 77.597, "ward": 6, "it_zone": False},
    "Silk Board": {"lat": 12.917, "lon": 77.623, "ward": 174, "it_zone": False},
    "Manyata Tech Park": {"lat": 13.043, "lon": 77.620, "ward": 7, "it_zone": True},
    "Electronic City": {"lat": 12.839, "lon": 77.677, "ward": 195, "it_zone": True},
    "Whitefield": {"lat": 12.969, "lon": 77.750, "ward": 84, "it_zone": True},
    "Koramangala": {"lat": 12.935, "lon": 77.627, "ward": 68, "it_zone": False},
    "Indiranagar": {"lat": 12.979, "lon": 77.638, "ward": 81, "it_zone": False},
    "Marathahalli": {"lat": 12.956, "lon": 77.701, "ward": 85, "it_zone": False},
    "HSR Layout": {"lat": 12.913, "lon": 77.644, "ward": 174, "it_zone": False},
    "BTM Layout": {"lat": 12.916, "lon": 77.610, "ward": 168, "it_zone": False},
    "Jayanagar": {"lat": 12.931, "lon": 77.583, "ward": 155, "it_zone": False},
    "JP Nagar": {"lat": 12.901, "lon": 77.585, "ward": 161, "it_zone": False},
    "Banashankari": {"lat": 12.925, "lon": 77.547, "ward": 148, "it_zone": False},
    "Rajajinagar": {"lat": 12.989, "lon": 77.552, "ward": 99, "it_zone": False},
    "Yeshwanthpur": {"lat": 13.021, "lon": 77.545, "ward": 98, "it_zone": False},
    "Yelahanka": {"lat": 13.100, "lon": 77.596, "ward": 3, "it_zone": False},
    "KR Puram": {"lat": 13.008, "lon": 77.696, "ward": 24, "it_zone": False},
    "Bannerghatta Road": {"lat": 12.872, "lon": 77.597, "ward": 191, "it_zone": False},
    "MG Road": {"lat": 12.975, "lon": 77.609, "ward": 76, "it_zone": False},
    "Shivajinagar": {"lat": 12.985, "lon": 77.600, "ward": 74, "it_zone": False},
    "Malleswaram": {"lat": 13.003, "lon": 77.568, "ward": 96, "it_zone": False},
    "Sarjapur Road": {"lat": 12.906, "lon": 77.685, "ward": 175, "it_zone": False},
    "Outer Ring Road": {"lat": 12.956, "lon": 77.696, "ward": 85, "it_zone": False},
    "Tumkur Road": {"lat": 13.030, "lon": 77.520, "ward": 104, "it_zone": False},
    "Bellary Road": {"lat": 13.050, "lon": 77.595, "ward": 5, "it_zone": False},
}

# Ward names mapping (for display purposes)
WARD_NAMES = {
    3: "Yelahanka",
    5: "Bellary Road",
    6: "Hebbal",
    7: "Manyata Tech Park",
    24: "KR Puram",
    68: "Koramangala",
    74: "Shivajinagar",
    75: "Frazer Town",
    76: "MG Road",
    77: "Richmond Town",
    80: "Cox Town",
    81: "Indiranagar",
    84: "Whitefield",
    85: "Marathahalli",
    96: "Malleswaram",
    98: "Yeshwanthpur",
    99: "Rajajinagar",
    104: "Tumkur Road",
    148: "Banashankari",
    155: "Jayanagar",
    161: "JP Nagar",
    168: "BTM Layout",
    174: "Silk Board",
    175: "Sarjapur Road",
    191: "Bannerghatta Road",
    195: "Electronic City",
}

def get_location_info(location_name):
    """Get location information by name"""
    return BENGALURU_LOCATIONS.get(location_name)

def get_ward_name(ward_id):
    """Get ward name by ID"""
    return WARD_NAMES.get(ward_id, f"Ward {ward_id}")

def get_all_locations():
    """Get all available locations"""
    return list(BENGALURU_LOCATIONS.keys())

def get_it_zones():
    """Get all IT zone locations"""
    return [name for name, info in BENGALURU_LOCATIONS.items() if info["it_zone"]]

def get_wards_for_route(source_ward, dest_ward):
    """Get affected wards for a route (simplified - returns wards along the path)"""
    # Simplified logic - returns wards that might be affected
    affected_wards = [source_ward, dest_ward]
    
    # Add some intermediate wards based on common routes
    if source_ward == 6 and dest_ward == 174:  # Hebbal to Silk Board
        affected_wards.extend([7, 24, 85, 175])
    elif source_ward == 7 and dest_ward == 195:  # Manyata to Electronic City
        affected_wards.extend([6, 24, 68, 174])
    elif source_ward == 84 and dest_ward == 76:  # Whitefield to MG Road
        affected_wards.extend([85, 175, 174, 68, 81])
    
    return list(set(affected_wards))
