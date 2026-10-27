import pickle
import pandas as pd
import osmnx as ox
from geopy.geocoders import Nominatim
from time import sleep

# ---------------------------------
# FILE PATHS
# ---------------------------------

GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"C:\Users\ravip\OneDrive\Desktop\Banglore_traffic_Dataset.csv"


# ---------------------------------
# LOAD ROAD GRAPH
# ---------------------------------

print("Loading Bengaluru road graph...")

with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

print("Graph loaded.")
print("Nodes:", len(G.nodes))
print("Edges:", len(G.edges))


# ---------------------------------
# LOAD TRAFFIC DATA
# ---------------------------------

df = pd.read_csv(TRAFFIC_FILE)

road_column = "Road/Intersection Name"

locations = (
    df[road_column]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)

print("\nLocations:", len(locations))


# ---------------------------------
# GEOCODER
# ---------------------------------

geolocator = Nominatim(
    user_agent="bengaluru_traffic_project"
)


# ---------------------------------
# MAP LOCATIONS
# ---------------------------------

results = []

for location in locations:

    print(f"\nSearching: {location}")

    query = f"{location}, Bengaluru, Karnataka, India"

    try:
        result = geolocator.geocode(query)

    except Exception as e:
        print("Geocoding error:", e)
        result = None

    if result is None:
        print("NOT FOUND")

        results.append({
            "traffic_location": location,
            "latitude": None,
            "longitude": None,
            "nearest_node": None,
            "distance_m": None,
            "status": "NOT_FOUND"
        })

        continue

    latitude = result.latitude
    longitude = result.longitude

    print("Latitude:", latitude)
    print("Longitude:", longitude)

    # ---------------------------------
    # FIND NEAREST OSM NODE
    # ---------------------------------

    try:

        nearest_node = ox.distance.nearest_nodes(
            G,
            X=longitude,
            Y=latitude
        )

        node_data = G.nodes[nearest_node]

        node_lat = node_data["y"]
        node_lon = node_data["x"]

        # Approximate distance in metres
        from math import radians, sin, cos, sqrt, atan2

        R = 6371000

        lat1 = radians(latitude)
        lat2 = radians(node_lat)

        dlat = radians(node_lat - latitude)
        dlon = radians(node_lon - longitude)

        a = (
            sin(dlat / 2) ** 2
            + cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance_m = R * c

        print("Nearest node:", nearest_node)
        print(f"Distance: {distance_m:.2f} metres")

        # Conservative validation
        if distance_m <= 300:
            status = "MATCHED"
        else:
            status = "CHECK_MANUALLY"

    except Exception as e:

        print("OSM mapping error:", e)

        nearest_node = None
        distance_m = None
        status = "OSM_ERROR"

    results.append({
        "traffic_location": location,
        "latitude": latitude,
        "longitude": longitude,
        "nearest_node": nearest_node,
        "distance_m": distance_m,
        "status": status
    })

    sleep(1)


# ---------------------------------
# SAVE RESULTS
# ---------------------------------

output_file = "traffic_location_mapping.csv"

mapping_df = pd.DataFrame(results)

mapping_df.to_csv(
    output_file,
    index=False
)

print("\n===================================")
print("MAPPING COMPLETE")
print("===================================")

print(mapping_df.to_string(index=False))

print(f"\nSaved to: {output_file}")