import pickle
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\traffic_module\data\live_traffic_history.csv"

SOURCE_NODE = 10118500634
DESTINATION_NODE = 6528219586


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("DYNAMIC TRAFFIC REROUTING VALIDATION")
print("=" * 70)


# ============================================================
# LOAD GRAPH
# ============================================================

print()
print("Loading Bengaluru road graph...")

with open(GRAPH_FILE, "rb") as f:
    graph = pickle.load(f)

print("Graph type:", type(graph).__name__)
print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# CHECK NODES
# ============================================================

print()
print("Checking source and destination...")

if SOURCE_NODE not in graph:
    raise SystemExit(
        f"ERROR: Source node {SOURCE_NODE} not found."
    )

if DESTINATION_NODE not in graph:
    raise SystemExit(
        f"ERROR: Destination node {DESTINATION_NODE} not found."
    )

print("Source:", SOURCE_NODE)
print("Destination:", DESTINATION_NODE)


# ============================================================
# CREATE BASE WEIGHTS
# ============================================================

print()
print("Preparing base travel-time weights...")

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

        base_time = float(
            data.get(
                "travel_time",
                1.0
            )
        )

    data["base_weight_sec"] = base_time

    # Initially traffic = normal
    data["traffic_weight_sec"] = base_time


# ============================================================
# BASE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING BASE ROUTE")
print("=" * 70)

base_route = nx.shortest_path(
    graph,
    source=SOURCE_NODE,
    target=DESTINATION_NODE,
    weight="base_weight_sec"
)

print()
print("Base route nodes:", len(base_route))


# ============================================================
# FIND BASE ROUTE EDGES
# ============================================================

def get_route_edges(
    G,
    route
):

    edges = []

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        options = G[
            u
        ][
            v
        ]

        best_key = None
        best_data = None
        best_weight = float("inf")

        for key, data in options.items():

            weight = float(
                data.get(
                    "base_weight_sec",
                    float("inf")
                )
            )

            if weight < best_weight:

                best_weight = weight
                best_key = key
                best_data = data

        if best_data is not None:

            edges.append(
                (
                    u,
                    v,
                    best_key,
                    best_data
                )
            )

    return edges


base_edges = get_route_edges(
    graph,
    base_route
)


# ============================================================
# SELECT AN EDGE TO SIMULATE HEAVY TRAFFIC
# ============================================================

print()
print("=" * 70)
print("SIMULATING HEAVY TRAFFIC")
print("=" * 70)

if len(base_edges) < 5:

    raise SystemExit(
        "ERROR: Base route is too short for dynamic rerouting test."
    )


# Choose an edge around the middle of the route.
test_index = len(base_edges) // 2

u, v, key, test_edge = base_edges[
    test_index
]

base_time = float(
    test_edge.get(
        "base_weight_sec",
        0
    )
)


print()
print("Selected traffic edge:")
print("From:", u)
print("To:", v)
print("Key:", key)

print(
    "Base travel time:",
    round(base_time, 2),
    "sec"
)


# ============================================================
# APPLY VERY HEAVY SIMULATED TRAFFIC
# ============================================================

# Make this edge 20x slower.
test_edge[
    "traffic_weight_sec"
] = base_time * 20


print(
    "Simulated traffic time:",
    round(
        test_edge["traffic_weight_sec"],
        2
    ),
    "sec"
)

print(
    "Traffic multiplier: 20x"
)


# ============================================================
# TRAFFIC-AWARE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING TRAFFIC-AWARE ROUTE")
print("=" * 70)

traffic_route = nx.shortest_path(
    graph,
    source=SOURCE_NODE,
    target=DESTINATION_NODE,
    weight="traffic_weight_sec"
)

print()
print(
    "Traffic route nodes:",
    len(traffic_route)
)


# ============================================================
# ROUTE DISTANCE
# ============================================================

def calculate_distance(
    G,
    route
):

    distance = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        options = G[
            u
        ][
            v
        ]

        best_length = float("inf")

        for key, data in options.items():

            length = float(
                data.get(
                    "length",
                    0
                )
            )

            if length > 0 and length < best_length:

                best_length = length

        if best_length != float("inf"):

            distance += best_length

    return distance / 1000


# ============================================================
# TRAVEL TIME
# ============================================================

def calculate_time(
    G,
    route,
    weight_name
):

    total = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        options = G[
            u
        ][
            v
        ]

        best_weight = float("inf")

        for key, data in options.items():

            weight = float(
                data.get(
                    weight_name,
                    float("inf")
                )
            )

            if weight < best_weight:

                best_weight = weight

        total += best_weight

    return total / 60


# ============================================================
# METRICS
# ============================================================

base_distance = calculate_distance(
    graph,
    base_route
)

traffic_distance = calculate_distance(
    graph,
    traffic_route
)

base_time = calculate_time(
    graph,
    base_route,
    "base_weight_sec"
)

traffic_time = calculate_time(
    graph,
    traffic_route,
    "traffic_weight_sec"
)


# ============================================================
# COMPARE ROUTES
# ============================================================

print()
print("=" * 70)
print("DYNAMIC REROUTING RESULT")
print("=" * 70)

print()

print("BASE ROUTE")
print("-" * 70)

print(
    "Distance:",
    f"{base_distance:.2f}",
    "km"
)

print(
    "Travel time:",
    f"{base_time:.2f}",
    "min"
)

print(
    "Nodes:",
    len(base_route)
)


print()
print("TRAFFIC-AWARE ROUTE")
print("-" * 70)

print(
    "Distance:",
    f"{traffic_distance:.2f}",
    "km"
)

print(
    "Travel time:",
    f"{traffic_time:.2f}",
    "min"
)

print(
    "Nodes:",
    len(traffic_route)
)


# ============================================================
# ROUTE CHANGE
# ============================================================

print()
print("ROUTE CHANGE")
print("-" * 70)

if base_route != traffic_route:

    print(
        "SUCCESS: Traffic-aware route changed!"
    )

    print()
    print(
        "The routing engine avoided the heavily congested edge."
    )

else:

    print(
        "WARNING: Route did not change."
    )

    print()
    print(
        "The selected edge may not provide a better alternative."
    )


# ============================================================
# CHECK SELECTED EDGE
# ============================================================

base_edge_set = set()

for u, v, key, data in base_edges:

    base_edge_set.add(
        (
            u,
            v,
            key
        )
    )


traffic_edges = get_route_edges(
    graph,
    traffic_route
)

traffic_edge_set = set()

for u, v, key, data in traffic_edges:

    traffic_edge_set.add(
        (
            u,
            v,
            key
        )
    )


removed = (
    base_edge_set
    -
    traffic_edge_set
)

added = (
    traffic_edge_set
    -
    base_edge_set
)


print()
print(
    "Base route edges:",
    len(base_edge_set)
)

print(
    "Traffic route edges:",
    len(traffic_edge_set)
)

print(
    "Edges removed:",
    len(removed)
)

print(
    "Edges added:",
    len(added)
)


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 70)
print("DYNAMIC REROUTING VALIDATION COMPLETE")
print("=" * 70)