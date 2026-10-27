import pickle
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\bengaluru_traffic_segments.csv"

SOURCE_NODE = 10118500634
DESTINATION_NODE = 6528219586


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("CITY-WIDE TRAFFIC ROUTING VALIDATION")
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
            (speed * 1000 / 3600)
        )

    else:

        base_time = float(
            data.get(
                "travel_time",
                1.0
            )
        )

    data["base_weight_sec"] = base_time

    data["traffic_weight_sec"] = base_time

    data["traffic_observed"] = False

    data["live_current_speed_kmh"] = None

    data["live_free_flow_speed_kmh"] = None

    data["live_delay_percent"] = None

    data["live_confidence"] = None

    data["live_road_closure"] = False


# ============================================================
# LOAD TRAFFIC
# ============================================================

print()
print("Loading city-wide traffic...")

traffic = pd.read_csv(
    TRAFFIC_FILE
)

print(
    "Traffic rows:",
    len(traffic)
)


# ============================================================
# SUCCESSFUL OBSERVATIONS
# ============================================================

traffic = traffic[
    traffic["status"]
    .astype(str)
    .str.upper()
    == "OK"
].copy()

print(
    "Successful traffic observations:",
    len(traffic)
)


# ============================================================
# APPLY TRAFFIC
# ============================================================

print()
print("Applying city-wide traffic to graph...")

traffic_edges_applied = 0
closed_edges = 0
traffic_edges_not_found = 0


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

        traffic_edges_not_found += 1

        continue


    if not graph.has_edge(
        u,
        v,
        key
    ):

        traffic_edges_not_found += 1

        continue


    edge = graph[
        u
    ][
        v
    ][
        key
    ]


    base_time = float(
        edge.get(
            "base_weight_sec",
            1.0
        )
    )


    try:

        current_speed = float(
            row["current_speed_kmh"]
        )

    except Exception:

        current_speed = 0.0


    try:

        free_flow_speed = float(
            row["free_flow_speed_kmh"]
        )

    except Exception:

        free_flow_speed = 0.0


    try:

        delay_percent = float(
            row["delay_percent"]
        )

    except Exception:

        delay_percent = 0.0


    try:

        confidence = float(
            row["confidence"]
        )

    except Exception:

        confidence = 0.0


    closure_text = str(
        row.get(
            "road_closure",
            False
        )
    ).lower()


    road_closed = closure_text in [
        "true",
        "1",
        "yes"
    ]


    # --------------------------------------------------------
    # ROAD CLOSURE
    # --------------------------------------------------------

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

        edge[
            "live_current_speed_kmh"
        ] = current_speed

        edge[
            "live_free_flow_speed_kmh"
        ] = free_flow_speed

        edge[
            "live_delay_percent"
        ] = delay_percent

        edge[
            "live_confidence"
        ] = confidence

        closed_edges += 1
        traffic_edges_applied += 1

        continue


    # --------------------------------------------------------
    # SPEED RATIO
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

    else:

        traffic_time = base_time


    # --------------------------------------------------------
    # LIMIT EXTREME VALUES
    # --------------------------------------------------------

    traffic_time = max(
        base_time,
        min(
            traffic_time,
            base_time * 20
        )
    )


    # --------------------------------------------------------
    # STORE TRAFFIC
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
    ] = delay_percent

    edge[
        "live_confidence"
    ] = confidence

    edge[
        "live_road_closure"
    ] = False

    traffic_edges_applied += 1


# ============================================================
# TRAFFIC SUMMARY
# ============================================================

print()
print(
    "Traffic edges applied:",
    traffic_edges_applied
)

print(
    "Closed edges:",
    closed_edges
)

print(
    "Traffic edges not found:",
    traffic_edges_not_found
)


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


# ============================================================
# TRAFFIC ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING CITY-WIDE TRAFFIC ROUTE")
print("=" * 70)

traffic_route = nx.shortest_path(
    graph,
    source=SOURCE_NODE,
    target=DESTINATION_NODE,
    weight="traffic_weight_sec"
)


# ============================================================
# ROUTE METRICS
# ============================================================

def get_best_edge(
    u,
    v,
    weight_name
):

    options = graph[
        u
    ][
        v
    ]

    best_edge = None
    best_key = None
    best_weight = float(
        "inf"
    )

    for key, data in options.items():

        weight = float(
            data.get(
                weight_name,
                float("inf")
            )
        )

        if weight < best_weight:

            best_weight = weight
            best_key = key
            best_edge = data

    return (
        best_key,
        best_edge,
        best_weight
    )


def calculate_route_metrics(
    route,
    weight_name
):

    distance_m = 0.0
    travel_time_sec = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        key, edge, weight = get_best_edge(
            u,
            v,
            weight_name
        )

        if edge is None:
            continue

        distance_m += float(
            edge.get(
                "length",
                0
            )
        )

        travel_time_sec += weight

    return (
        distance_m / 1000,
        travel_time_sec / 60
    )


# ============================================================
# CALCULATE METRICS
# ============================================================

base_distance, base_time = (
    calculate_route_metrics(
        base_route,
        "base_weight_sec"
    )
)


traffic_distance, traffic_time = (
    calculate_route_metrics(
        traffic_route,
        "traffic_weight_sec"
    )
)


additional_time = (
    traffic_time
    -
    base_time
)


if base_time > 0:

    delay_percent = (
        additional_time
        /
        base_time
    ) * 100

else:

    delay_percent = 0.0


# ============================================================
# RESULT
# ============================================================

print()
print("=" * 70)
print("CITY-WIDE TRAFFIC ROUTING RESULT")
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
    f"Additional travel time: "
    f"{additional_time:.2f} min"
)

print(
    f"Traffic delay: "
    f"{delay_percent:.2f} %"
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
        "SUCCESS: Traffic-aware route changed!"
    )


# ============================================================
# EDGE SET COMPARISON
# ============================================================

base_edges = set(
    zip(
        base_route[:-1],
        base_route[1:]
    )
)

traffic_route_edges = set(
    zip(
        traffic_route[:-1],
        traffic_route[1:]
    )
)


removed_edges = (
    base_edges
    -
    traffic_route_edges
)

added_edges = (
    traffic_route_edges
    -
    base_edges
)


print()
print(
    "Base route edges:",
    len(base_edges)
)

print(
    "Traffic route edges:",
    len(traffic_route_edges)
)

print(
    "Edges removed:",
    len(removed_edges)
)

print(
    "Edges added:",
    len(added_edges)
)


# ============================================================
# EXACT TRAFFIC EDGES USED BY TRAFFIC ROUTE
# ============================================================

print()
print("=" * 70)
print("TRAFFIC OBSERVATIONS USED BY TRAFFIC-AWARE ROUTE")
print("=" * 70)


route_traffic_edges = []


for i in range(
    len(traffic_route) - 1
):

    u = traffic_route[i]
    v = traffic_route[i + 1]


    options = graph[
        u
    ][
        v
    ]


    # --------------------------------------------------------
    # Find the edge actually selected by traffic weight
    # --------------------------------------------------------

    best_key = None
    best_edge = None
    best_weight = float(
        "inf"
    )


    for key, edge in options.items():

        weight = float(
            edge.get(
                "traffic_weight_sec",
                float("inf")
            )
        )

        if weight < best_weight:

            best_weight = weight
            best_key = key
            best_edge = edge


    if best_edge is None:
        continue


    if not best_edge.get(
        "traffic_observed",
        False
    ):
        continue


    base_weight = float(
        best_edge.get(
            "base_weight_sec",
            0
        )
    )


    traffic_weight = float(
        best_edge.get(
            "traffic_weight_sec",
            0
        )
    )


    extra_time = (
        traffic_weight
        -
        base_weight
    )


    route_traffic_edges.append(
        (
            u,
            v,
            best_key,
            best_edge,
            extra_time
        )
    )


# ============================================================
# PRINT TRAFFIC EDGES
# ============================================================

if route_traffic_edges:

    for (
        u,
        v,
        key,
        edge,
        extra_time
    ) in route_traffic_edges:

        road_name = edge.get(
            "name",
            "Unnamed road"
        )


        current_speed = edge.get(
            "live_current_speed_kmh"
        )


        free_flow_speed = edge.get(
            "live_free_flow_speed_kmh"
        )


        delay = edge.get(
            "live_delay_percent"
        )


        confidence = edge.get(
            "live_confidence"
        )


        base_weight = float(
            edge.get(
                "base_weight_sec",
                0
            )
        )


        traffic_weight = float(
            edge.get(
                "traffic_weight_sec",
                0
            )
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
            key
        )

        print(
            "Current speed:",
            current_speed,
            "km/h"
        )

        print(
            "Free-flow speed:",
            free_flow_speed,
            "km/h"
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
            f"Base time: {base_weight:.2f} sec"
        )

        print(
            f"Traffic time: {traffic_weight:.2f} sec"
        )

        print(
            f"Extra time: {extra_time:.2f} sec"
        )


else:

    print()
    print(
        "No directly observed traffic edges "
        "were used by the final traffic-aware route."
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 70)
print("FINAL SUMMARY")
print("=" * 70)

print(
    "City-wide traffic observations:",
    len(traffic)
)

print(
    "Traffic edges successfully applied:",
    traffic_edges_applied
)

print(
    "Traffic observations on final route:",
    len(route_traffic_edges)
)

print(
    f"Base travel time: {base_time:.2f} min"
)

print(
    f"Traffic travel time: {traffic_time:.2f} min"
)

print(
    f"Additional time: {additional_time:.2f} min"
)

print(
    f"Traffic delay: {delay_percent:.2f} %"
)


print()
print("=" * 70)
print("CITY-WIDE TRAFFIC ROUTING VALIDATION COMPLETE")
print("=" * 70)