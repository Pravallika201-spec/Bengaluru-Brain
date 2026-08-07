import networkx as nx
from datetime import datetime
from graph_builder import build_bengaluru_graph, get_nearest_node
from gnn_model import run_gnn

WEATHER_CODES = {
    "clear": 0,
    "light_rain": 1,
    "heavy_rain": 2,
    "storm": 3,
    "fog": 4
}

def predict_route(source: str, destination: str,
                  weather: str = "clear"):

    # 1. Load Bengaluru OSMnx graph
    G = build_bengaluru_graph()

    # 2. Geocode source and destination to graph nodes
    src_node, src_lat, src_lon = get_nearest_node(G, source)
    dst_node, dst_lat, dst_lon = get_nearest_node(G, destination)

    # 3. Current time context
    now = datetime.now()
    hour = now.hour
    is_weekday = now.weekday() < 5
    weather_code = WEATHER_CODES.get(weather, 0)

    # 4. Run GNN — get congestion score per node
    congestion = run_gnn(G, hour, is_weekday, weather_code)

    # 5. Apply congestion weights to edges
    import copy
    G_weighted = copy.deepcopy(G)
    for u, v, key, data in G_weighted.edges(keys=True, data=True):
        base_time = data.get("travel_time", 60)
        score = (congestion.get(u, 0.3) + congestion.get(v, 0.3)) / 2
        multiplier = 1.0 + (score * 2.5)
        G_weighted[u][v][key]["congested_time"] = base_time * multiplier

    # 6. Shortest path using congestion weights
    try:
        path = nx.shortest_path(
            G_weighted, src_node, dst_node,
            weight="congested_time"
        )
    except nx.NetworkXNoPath:
        raise Exception(
            f"No route found from {source} to {destination}"
        )

    # 7. Compute totals along path
    total_congested = 0
    total_free = 0
    total_distance = 0
    road_names = []

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edges = G_weighted[u][v]
        best = min(edges.values(),
                   key=lambda d: d.get("congested_time", 9999))

        total_congested += best.get("congested_time", 60)
        total_free += best.get("travel_time", 60)
        total_distance += best.get("length", 100)

        name = best.get("name", "")
        if isinstance(name, list):
            name = name[0]
        if name and name not in road_names:
            road_names.append(str(name))

    congested_mins = max(1, round(total_congested / 60))
    free_mins = max(1, round(total_free / 60))
    delay_mins = max(0, congested_mins - free_mins)
    distance_km = round(total_distance / 1000, 1)

    # 8. Average congestion score on route
    path_scores = [congestion.get(n, 0.3) for n in path]
    avg_score = sum(path_scores) / len(path_scores)

    # 9. Speed
    avg_speed = round((distance_km / congested_mins) * 60, 1)

    # 10. Status
    status = score_to_status(avg_score)

    # 11. Via text
    via = " → ".join(road_names[:3]) if road_names else "Bengaluru roads"

    # 12. 2-hour forecast
    future_hour = (hour + 2) % 24
    future_congestion = run_gnn(G, future_hour, is_weekday, weather_code)
    future_scores = [future_congestion.get(n, 0.3) for n in path]
    future_avg = sum(future_scores) / len(future_scores)
    future_multiplier = 1.0 + (future_avg * 2.5)
    future_mins = max(1, round(free_mins * future_multiplier))

    # 13. Path coordinates for map
    path_coords = [
        {"lat": G.nodes[n]["y"], "lon": G.nodes[n]["x"]}
        for n in path[::max(1, len(path)//50)]  # sample 50 points
    ]

    return {
        "source": source,
        "destination": destination,
        "distance_km": distance_km,
        "free_flow_mins": free_mins,
        "predicted_mins": congested_mins,
        "delay_mins": delay_mins,
        "avg_speed_kmh": avg_speed,
        "congestion_score": round(avg_score, 2),
        "status": status,
        "via": via,
        "path_coords": path_coords,
        "src_coords": {"lat": src_lat, "lon": src_lon},
        "dst_coords": {"lat": dst_lat, "lon": dst_lon},
        "forecast_2hr": {
            "predicted_mins": future_mins,
            "delay_mins": max(0, future_mins - free_mins),
            "status": score_to_status(future_avg)
        },
        "kannada_alert": make_kannada_alert(
            source, destination,
            congested_mins, delay_mins, status
        ),
        "model_info": f"GNN (GAT) on OSMnx Bengaluru graph | "
                      f"{len(G.nodes):,} nodes | "
                      f"{len(G.edges):,} edges",
        "predicted_at": now.strftime("%I:%M %p, %d %b %Y")
    }


def score_to_status(score):
    if score >= 0.75:   return "CRITICAL"
    elif score >= 0.60: return "HIGH"
    elif score >= 0.40: return "MODERATE"
    elif score >= 0.25: return "LOW"
    else:               return "CLEAR"


def make_kannada_alert(src, dst, mins, delay, status):
    label = {
        "CRITICAL": "ತೀವ್ರ ದಟ್ಟಣೆ ⚠️",
        "HIGH":     "ಹೆಚ್ಚಿನ ದಟ್ಟಣೆ 🟠",
        "MODERATE": "ಮಧ್ಯಮ ದಟ್ಟಣೆ 🟡",
        "LOW":      "ಕಡಿಮೆ ದಟ್ಟಣೆ 🟢",
        "CLEAR":    "ರಸ್ತೆ ಸ್ಪಷ್ಟ ✅"
    }.get(status, status)
    return (
        f"ಬೆಂಗಳೂರು ಮೆದುಳು | {src} → {dst} | "
        f"{label} | {mins} ನಿಮಿಷ | +{delay} ನಿಮಿಷ ವಿಳಂಬ"
    )
