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
print("TRAFFIC ROUTING VALIDATION")
print("=" * 70)


# ============================================================
# LOAD GRAPH
# ============================================================

print()
print("Loading Bengaluru road graph...")

if not os.path.exists(GRAPH_FILE):

    print("ERROR: Graph file not found.")
    print(GRAPH_FILE)
    raise SystemExit(1)

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

    print("ERROR: Source node not found.")
    raise SystemExit(1)

if DESTINATION_NODE not in graph:

    print("ERROR: Destination node not found.")
    raise SystemExit(1)

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

        base_time = float("inf")

    data[
        "base_weight_sec"
    ] = base_time

    data[
        "traffic_weight_sec"
    ] = base_time

    data[
        "traffic_observed"
    ] = False


# ============================================================
# LOAD LIVE TRAFFIC
# ============================================================

print()
print("Loading live traffic...")

if not os.path.exists(TRAFFIC_FILE):

    print("ERROR: Traffic file not found.")
    print(TRAFFIC_FILE)
    raise SystemExit(1)

traffic = pd.read_csv(
    TRAFFIC_FILE
)

print(
    "Traffic records:",
    len(traffic)
)


# ============================================================
# VALIDATE TRAFFIC COLUMNS
# ============================================================

required_columns = [

    "osm_u",
    "osm_v",
    "osm_key",
    "current_speed_kmh",
    "free_flow_speed_kmh",
    "delay_percent",
    "confidence",
    "road_closure"

]

missing = [

    column
    for column in required_columns
    if column not in traffic.columns

]

if missing:

    print()
    print("ERROR: Missing traffic columns:")

    for column in missing:

        print(" -", column)

    raise SystemExit(1)


# ============================================================
# APPLY LIVE TRAFFIC DIRECTLY TO GRAPH EDGES
# ============================================================

print()
print("Applying live traffic to graph...")

applied = 0
closed = 0
not_found = 0


for _, row in traffic.iterrows():

    try:

        u = int(
            float(
                row["osm_u"]
            )
        )

        v = int(
            float(
                row["osm_v"]
            )
        )

        key = int(
            float(
                row["osm_key"]
            )
        )

    except Exception:

        continue


    if not graph.has_edge(u, v):

        not_found += 1

        continue


    if key not in graph[u][v]:

        not_found += 1

        continue


    edge = graph[u][v][key]


    # --------------------------------------------------------
    # Base travel time
    # --------------------------------------------------------

    base_time = float(
        edge.get(
            "base_weight_sec",
            float("inf")
        )
    )


    # --------------------------------------------------------
    # Road closure
    # --------------------------------------------------------

    road_closed = str(
        row["road_closure"]
    ).strip().lower() in [

        "true",
        "1",
        "yes"

    ]


    if road_closed:

        edge[
            "traffic_weight_sec"
        ] = float("inf")

        edge[
            "traffic_observed"
        ] = True

        edge[
            "live_road_closure"
        ] = True

        closed += 1

        applied += 1

        continue


    # --------------------------------------------------------
    # Current speed
    # --------------------------------------------------------

    try:

        current_speed = float(
            row["current_speed_kmh"]
        )

    except Exception:

        current_speed = 0


    # --------------------------------------------------------
    # Free-flow speed
    # --------------------------------------------------------

    try:

        free_flow_speed = float(
            row["free_flow_speed_kmh"]
        )

    except Exception:

        free_flow_speed = 0


    # --------------------------------------------------------
    # Calculate traffic weight
    # --------------------------------------------------------

    if (
        current_speed > 0
        and
        free_flow_speed > 0
    ):

        speed_ratio = (
            current_speed
            /
            free_flow_speed
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

    else:

        traffic_time = base_time


    # --------------------------------------------------------
    # Store traffic information
    # --------------------------------------------------------

    edge[
        "traffic_weight_sec"
    ] = traffic_time

    edge[
        "traffic_observed"
    ] = True

    edge[
        "live_current_speed_kmh"
    ] = current_speed

    edge[
        "live_free_flow_speed_kmh"
    ] = free_flow_speed

    edge[
        "live_delay_percent"
    ] = row["delay_percent"]

    edge[
        "live_confidence"
    ] = row["confidence"]

    edge[
        "live_road_closure"
    ] = False


    applied += 1


print()
print(
    "Traffic edges applied:",
    applied
)

print(
    "Closed edges:",
    closed
)

print(
    "Traffic edges not found in graph:",
    not_found
)


# ============================================================
# CALCULATE ROUTE METRICS
# ============================================================

def calculate_metrics(
    route,
    weight_name
):

    distance_m = 0.0
    time_sec = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]


        # ----------------------------------------------------
        # MultiDiGraph may contain multiple edges
        # ----------------------------------------------------

        options = graph[u][v]

        best_edge = None
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
                best_edge = data


        if best_edge is None:

            continue


        distance_m += float(
            best_edge.get(
                "length",
                0
            )
        )

        time_sec += best_weight


    return (
        distance_m / 1000,
        time_sec / 60
    )


# ============================================================
# BASE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING BASE ROUTE")
print("=" * 70)


try:

    base_route = nx.shortest_path(
        graph,
        source=SOURCE_NODE,
        target=DESTINATION_NODE,
        weight="base_weight_sec"
    )

except nx.NetworkXNoPath:

    print("ERROR: No base route found.")
    raise SystemExit(1)


# ============================================================
# TRAFFIC-AWARE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING TRAFFIC-AWARE ROUTE")
print("=" * 70)


try:

    traffic_route = nx.shortest_path(
        graph,
        source=SOURCE_NODE,
        target=DESTINATION_NODE,
        weight="traffic_weight_sec"
    )

except nx.NetworkXNoPath:

    print("ERROR: No traffic-aware route found.")
    raise SystemExit(1)


# ============================================================
# METRICS
# ============================================================

base_distance, base_time = calculate_metrics(
    base_route,
    "base_weight_sec"
)

traffic_distance, traffic_time = calculate_metrics(
    traffic_route,
    "traffic_weight_sec"
)


delay = max(
    0,
    traffic_time - base_time
)


if base_time > 0:

    delay_percent = (
        delay
        /
        base_time
    ) * 100

else:

    delay_percent = 0


# ============================================================
# RESULTS
# ============================================================

print()
print("=" * 70)
print("VALIDATION RESULT")
print("=" * 70)


print()
print("BASE ROUTE")
print("-" * 70)

print(
    f"Distance: {base_distance:.2f} km"
)

print(
    f"Travel time: {base_time:.2f} min"
)

print(
    f"Nodes: {len(base_route)}"
)


print()
print("TRAFFIC-AWARE ROUTE")
print("-" * 70)

print(
    f"Distance: {traffic_distance:.2f} km"
)

print(
    f"Travel time: {traffic_time:.2f} min"
)

print(
    f"Nodes: {len(traffic_route)}"
)


print()
print("COMPARISON")
print("-" * 70)

print(
    f"Additional travel time: {delay:.2f} min"
)

print(
    f"Traffic delay: {delay_percent:.2f} %"
)


# ============================================================
# ROUTE CHANGE
# ============================================================

print()
print("ROUTE CHANGE")
print("-" * 70)


if base_route == traffic_route:

    print(
        "Base route and traffic-aware route are the SAME."
    )

else:

    print(
        "Traffic-aware routing selected a DIFFERENT route."
    )


# ============================================================
# SHOW DIFFERENCES
# ============================================================

base_set = set(
    zip(
        base_route[:-1],
        base_route[1:]
    )
)

traffic_set = set(
    zip(
        traffic_route[:-1],
        traffic_route[1:]
    )
)


removed_edges = (
    base_set - traffic_set
)

added_edges = (
    traffic_set - base_set
)


print()
print("Route edges removed from base route:")

print(
    len(removed_edges)
)


print()
print("Route edges added by traffic-aware route:")

print(
    len(added_edges)
)


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 70)
print("TRAFFIC ROUTING VALIDATION COMPLETE")
print("=" * 70)