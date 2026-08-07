import osmnx as ox
import pickle
import os
from geopy.geocoders import Nominatim

GRAPH_PATH = "data/bengaluru_graph.pkl"

def build_bengaluru_graph():
    if os.path.exists(GRAPH_PATH):
        print("Loading saved Bengaluru graph...")
        with open(GRAPH_PATH, "rb") as f:
            return pickle.load(f)

    print("Downloading Bengaluru road network (one time only)...")
    os.makedirs("data", exist_ok=True)

    G = ox.graph_from_place(
        "Bengaluru, Karnataka, India",
        network_type="drive",
        simplify=True
    )
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    with open(GRAPH_PATH, "wb") as f:
        pickle.dump(G, f)

    print(f"Graph saved: {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G


def geocode_place(place_name):
    geolocator = Nominatim(user_agent="bengaluru_brain_v1")
    location = geolocator.geocode(
        f"{place_name}, Bengaluru, Karnataka, India"
    )
    if not location:
        raise ValueError(f"Place not found: {place_name}")
    return location.latitude, location.longitude


def get_nearest_node(G, place_name):
    lat, lon = geocode_place(place_name)
    node = ox.distance.nearest_nodes(G, lon, lat)
    return node, lat, lon
