import os
import pickle
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\latest_graph_traffic.csv"

SOURCE_NODE = 10118500634
DESTINATION_NODE = 6528219586


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("ROUTE TRAFFIC EDGE VALIDATION")
print("=" * 70)


# ============================================================
# LOAD GRAPH
# ============================================================

print()
print("Loading graph...")

with open(GRAPH_FILE, "rb") as f:
    graph = pickle.load(f)

print("Graph:", type(graph).__name__)
print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# CREATE BASE WEIGHTS
# ============================================================

print()
print("Creating base weights...")

for u, v, key, data in graph.edges(
    keys=True,
    data=True
):

    length = float(
        data.get(
            "length",
            0
        )
    )

    speed = float(
        data.get(
            "speed_kph",
            0
        )
    )

    if length > 0 and speed > 0:

        base_time = (
            length
            /
            (
                speed
                * 1000
                / 3600
            )
        )

    else:

        base_time = float("inf")


    data["base_weight_sec"] = base_time
    data["traffic_weight_sec"] = base_time
    data["traffic_observed"] = False


# ============================================================
# LOAD LIVE TRAFFIC
# ============================================================

print()
print("Loading live traffic...")

traffic = pd.read_csv(
    TRAFFIC_FILE
)

print(
    "Traffic records:",
    len(traffic)
)


# ============================================================
# APPLY LIVE TRAFFIC
# ============================================================

print()
print("Applying live traffic...")

applied = 0


for _, row in traffic.iterrows():

    try:

        u = int(float(row["osm_u"]))
        v = int(float(row["osm_v"]))
        key = int(float(row["osm_key"]))

    except Exception:

        continue


    if not graph.has_edge(u, v):
        continue


    if key not in graph[u][v]:
        continue


    edge = graph[u][v][key]


    base_time = float(
        edge.get(
            "base_weight_sec",
            float("inf")
        )
    )


    try:

        current_speed = float(
            row["current_speed_kmh"]
        )

        free_speed = float(
            row["free_flow_speed_kmh"]
        )

    except Exception:

        continue


    road_closed = str(
        row["road_closure"]
    ).strip().lower() in [
        "true",
        "1",
        "yes"
    ]


    if road_closed:

        edge["traffic_weight_sec"] = float("inf")

    elif current_speed > 0 and free_speed > 0:

        speed_ratio = (
            current_speed
            /
            free_speed
        )

        speed_ratio = max(
            0.05,
            min(
                speed_ratio,
                1.0
            )
        )

        traffic_time = (
            base_time
            /
            speed_ratio
        )

        traffic_time = max(
            base_time,
            min(
                traffic_time,
                base_time * 20
            )
        )

        edge["traffic_weight_sec"] = traffic_time

    else:

        edge["traffic_weight_sec"] = base_time


    edge["traffic_observed"] = True

    edge["live_current_speed_kmh"] = current_speed
    edge["live_free_flow_speed_kmh"] = free_speed
    edge["live_delay_percent"] = row["delay_percent"]
    edge["live_confidence"] = row["confidence"]

    applied += 1


print(
    "Traffic edges applied:",
    applied
)


# ============================================================
# CALCULATE ROUTE
# ============================================================

print()
print("Calculating traffic-aware route...")

route = nx.shortest_path(
    graph,
    source=SOURCE_NODE,
    target=DESTINATION_NODE,
    weight="traffic_weight_sec"
)


print(
    "Route nodes:",
    len(route)
)


# ============================================================
# INSPECT ROUTE EDGES
# ============================================================

print()
print("=" * 70)
print("TRAFFIC ON SELECTED ROUTE")
print("=" * 70)


traffic_edges = 0
total_extra_sec = 0.0


for i in range(
    len(route) - 1
):

    u = route[i]
    v = route[i + 1]


    options = graph[u][v]


    best_key = None
    best_edge = None
    best_weight = float("inf")


    for key, data in options.items():

        weight = float(
            data.get(
                "traffic_weight_sec",
                float("inf")
            )
        )

        if weight < best_weight:

            best_weight = weight
            best_key = key
            best_edge = data


    if best_edge is None:
        continue


    if not best_edge.get(
        "traffic_observed",
        False
    ):

        continue


    traffic_edges += 1


    base_time = float(
        best_edge.get(
            "base_weight_sec",
            0
        )
    )


    traffic_time = float(
        best_edge.get(
            "traffic_weight_sec",
            0
        )
    )


    extra = max(
        0,
        traffic_time - base_time
    )


    total_extra_sec += extra


    road_name = best_edge.get(
        "name",
        "Unnamed road"
    )


    if isinstance(
        road_name,
        list
    ):

        road_name = ", ".join(
            map(str, road_name)
        )


    current_speed = best_edge.get(
        "live_current_speed_kmh"
    )


    free_speed = best_edge.get(
        "live_free_flow_speed_kmh"
    )


    delay = best_edge.get(
        "live_delay_percent"
    )


    confidence = best_edge.get(
        "live_confidence"
    )


    print()
    print("-" * 70)

    print(
        "Road:",
        road_name
    )

    print(
        "Edge:",
        u,
        "->",
        v,
        "key:",
        best_key
    )

    print(
        "Current speed:",
        current_speed,
        "km/h"
    )

    print(
        "Free-flow speed:",
        free_speed,
        "km/h"
    )

    print(
        "Speed ratio:",
        f"{current_speed / free_speed:.3f}"
        if current_speed and free_speed
        else "N/A"
    )

    print(
        "TomTom delay:",
        delay,
        "%"
    )

    print(
        "Confidence:",
        confidence
    )

    print(
        "Base time:",
        f"{base_time:.2f}",
        "sec"
    )

    print(
        "Traffic time:",
        f"{traffic_time:.2f}",
        "sec"
    )

    print(
        "Extra time:",
        f"{extra:.2f}",
        "sec"
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("TRAFFIC VALIDATION SUMMARY")
print("=" * 70)

print(
    "Route traffic edges:",
    traffic_edges
)

print(
    "Total additional time from observed edges:",
    f"{total_extra_sec:.2f} sec"
)

print(
    "Total additional time:",
    f"{total_extra_sec / 60:.2f} min"
)


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)