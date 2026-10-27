import os
import math
import pickle

import osmnx as ox
from geopy.geocoders import Nominatim

GRAPH_PATH = os.path.join("data", "bengaluru_graph.pkl")
GRAPHML_CANDIDATES = [
    os.path.join("data", "bangalore.graphml"),
    os.path.join("data", "bangalore_road_graph.graphml"),
]


def build_bengaluru_graph():
    if os.path.exists(GRAPH_PATH):
        print("Loading saved Bengaluru graph...")
        with open(GRAPH_PATH, "rb") as handle:
            return pickle.load(handle)

    os.makedirs("data", exist_ok=True)

    for candidate in GRAPHML_CANDIDATES:
        if os.path.exists(candidate):
            print(f"Loading Bengaluru graph from {candidate}...")
            G = ox.load_graphml(candidate)
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
            with open(GRAPH_PATH, "wb") as handle:
                pickle.dump(G, handle)
            print(f"Graph loaded: {len(G.nodes)} nodes, {len(G.edges)} edges")
            return G

    print("Downloading Bengaluru road network (one time only)...")
    G = ox.graph_from_place(
        "Bengaluru, Karnataka, India",
        network_type="drive",
        simplify=True,
    )
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    with open(GRAPH_PATH, "wb") as handle:
        pickle.dump(G, handle)

    print(f"Graph saved: {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G


def geocode_place(place_name):
    geolocator = Nominatim(user_agent="bengaluru_brain_v1")
    location = geolocator.geocode(f"{place_name}, Bengaluru, Karnataka, India")
    if not location:
        raise ValueError(f"Place not found: {place_name}")
    return location.latitude, location.longitude


def get_nearest_node(G, place_name):
    lat, lon = geocode_place(place_name)
    try:
        node = ox.distance.nearest_nodes(G, lon, lat)
        return node, lat, lon
    except Exception as exc:
        print(f"Nearest-node fallback triggered: {exc}")
        best_node = None
        best_distance = float("inf")
        for node_id, data in G.nodes(data=True):
            if "x" in data and "y" in data:
                node_lat = float(data["y"])
                node_lon = float(data["x"])
                lat1, lon1 = math.radians(lat), math.radians(lon)
                lat2, lon2 = math.radians(node_lat), math.radians(node_lon)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                distance = 6371 * 2 * math.asin(math.sqrt(a))
                if distance < best_distance:
                    best_distance = distance
                    best_node = node_id
        if best_node is None:
            raise ValueError(f"Unable to map {place_name} to a graph node")
        return best_node, lat, lon


def get_route_geometry(G, path_nodes, edge_speed_map=None):
    if not path_nodes or len(path_nodes) < 2:
        return []

    coords = []
    for idx in range(len(path_nodes) - 1):
        u, v = path_nodes[idx], path_nodes[idx + 1]
        edge_candidates = G[u][v]
        chosen = None
        chosen_key = None

        for key, data in edge_candidates.items():
            if edge_speed_map is not None:
                pred_speed = edge_speed_map.get((u, v, key)) or edge_speed_map.get((v, u, key))
                if pred_speed is not None and (chosen is None or pred_speed > chosen[0]):
                    chosen = (pred_speed, data)
                    chosen_key = key
            else:
                chosen = (1.0, edge_candidates[key])
                chosen_key = key
                break

        if chosen is None:
            continue

        data = chosen[1]
        geometry = data.get("geometry")
        if geometry is not None:
            try:
                for lon, lat in geometry.coords:
                    coords.append([lat, lon])
            except Exception:
                pass
        else:
            coords.append([G.nodes[u]["y"], G.nodes[u]["x"]])
            coords.append([G.nodes[v]["y"], G.nodes[v]["x"]])

    if coords:
        unique = []
        for point in coords:
            if not unique or unique[-1] != point:
                unique.append(point)
        return unique

    return [
        [G.nodes[path_nodes[0]]["y"], G.nodes[path_nodes[0]]["x"]],
        [G.nodes[path_nodes[-1]]["y"], G.nodes[path_nodes[-1]]["x"]],
    ]
