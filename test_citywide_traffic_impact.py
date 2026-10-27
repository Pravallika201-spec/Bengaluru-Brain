import os
import pickle
import math
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = (
    r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"
)

TRAFFIC_FILE = (
    r"D:\major project\bengaluru_traffic_segments.csv"
)

SOURCE_NODE = 10118500634
DESTINATION_NODE = 6528219586


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("CITY-WIDE TRAFFIC IMPACT VALIDATION")
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

        base_time = float("inf")

    data["base_weight_sec"] = base_time
    data["traffic_weight_sec"] = base_time

    data["traffic_observed"] = False
    data["live_road_closure"] = False

    data["live_current_speed_kmh"] = None
    data["live_free_flow_speed_kmh"] = None
    data["live_delay_percent"] = None
    data["live_confidence"] = None


# ============================================================
# LOAD CITY-WIDE TRAFFIC
# ============================================================

print()
print("Loading city-wide traffic...")

if not os.path.exists(TRAFFIC_FILE):

    raise SystemExit(
        "ERROR: Traffic file not found:\n"
        + TRAFFIC_FILE
    )

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
    .eq("OK")
].copy()

print(
    "Successful traffic observations:",
    len(traffic)
)


if traffic.empty:

    raise SystemExit(
        "ERROR: No successful traffic observations."
    )


# ============================================================
# APPLY TRAFFIC DIRECTLY TO GRAPH EDGES
# ============================================================

print()
print("Applying city-wide traffic to graph...")

traffic_edges = 0
closed_edges = 0
not_found = 0


for _, row in traffic.iterrows():

    try:

        u = int(row["osm_u"])
        v = int(row["osm_v"])
        key = int(row["osm_key"])

    except Exception:

        continue


    if not graph.has_edge(
        u,
        v,
        key
    ):

        not_found += 1
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
            float("inf")
        )
    )


    road_closure = str(
        row.get(
            "road_closure",
            ""
        )
    ).lower() in [
        "true",
        "1",
        "yes"
    ]


    # --------------------------------------------------------
    # ROAD CLOSURE
    # --------------------------------------------------------

    if road_closure:

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
        ] = row.get(
            "current_speed_kmh"
        )

        edge[
            "live_free_flow_speed_kmh"
        ] = row.get(
            "free_flow_speed_kmh"
        )

        edge[
            "live_delay_percent"
        ] = row.get(
            "delay_percent"
        )

        edge[
            "live_confidence"
        ] = row.get(
            "confidence"
        )

        closed_edges += 1
        traffic_edges += 1

        continue


    # --------------------------------------------------------
    # SPEED RATIO
    # --------------------------------------------------------

    try:

        current_speed = float(
            row["current_speed_kmh"]
        )

        free_speed = float(
            row["free_flow_speed_kmh"]
        )

    except Exception:

        continue


    if (
        current_speed > 0
        and
        free_speed > 0
    ):

        speed_ratio = (
            current_speed
            /
            free_speed
        )

    else:

        speed_ratio = 1.0


    speed_ratio = max(
        0.05,
        min(
            speed_ratio,
            1.0
        )
    )


    # --------------------------------------------------------
    # TRAFFIC TRAVEL TIME
    # --------------------------------------------------------

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


    edge[
        "traffic_weight_sec"
    ] = traffic_time

    edge[
        "traffic_observed"
    ] = True

    edge[
        "live_road_closure"
    ] = False

    edge[
        "live_current_speed_kmh"
    ] = current_speed

    edge[
        "live_free_flow_speed_kmh"
    ] = free_speed

    edge[
        "live_delay_percent"
    ] = row.get(
        "delay_percent"
    )

    edge[
        "live_confidence"
    ] = row.get(
        "confidence"
    )

    traffic_edges += 1


print()
print(
    "Traffic edges applied:",
    traffic_edges
)

print(
    "Closed edges:",
    closed_edges
)

print(
    "Traffic edges not found:",
    not_found
)


# ============================================================
# CALCULATE BASE ROUTE
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
# CALCULATE TRAFFIC ROUTE
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


# ============================================================
# ROUTE EDGE SETS
# ============================================================

def route_edges(
    route
):

    result = []

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        best_key = None
        best_edge = None
        best_weight = float("inf")

        for key, data in graph[
            u
        ][
            v
        ].items():

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

        if best_edge is not None:

            result.append(
                (
                    u,
                    v,
                    best_key
                )
            )

    return result


base_edges = route_edges(
    base_route
)

traffic_edges_route = route_edges(
    traffic_route
)


base_edge_set = set(
    base_edges
)

traffic_edge_set = set(
    traffic_edges_route
)


removed_edges = (
    base_edge_set
    -
    traffic_edge_set
)

added_edges = (
    traffic_edge_set
    -
    base_edge_set
)


# ============================================================
# ROUTE METRICS
# ============================================================

def route_metrics(
    route
):

    distance_m = 0.0
    base_time = 0.0
    traffic_time = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        key = None
        edge = None

        best_weight = float("inf")

        for k, data in graph[
            u
        ][
            v
        ].items():

            weight = float(
                data.get(
                    "traffic_weight_sec",
                    float("inf")
                )
            )

            if weight < best_weight:

                best_weight = weight
                key = k
                edge = data

        if edge is None:
            continue

        distance_m += float(
            edge.get(
                "length",
                0
            )
        )

        base_time += float(
            edge.get(
                "base_weight_sec",
                0
            )
        )

        traffic_time += float(
            edge.get(
                "traffic_weight_sec",
                0
            )
        )

    return (
        distance_m / 1000,
        base_time / 60,
        traffic_time / 60
    )


base_distance, base_time, _ = route_metrics(
    base_route
)

traffic_distance, _, traffic_time = route_metrics(
    traffic_route
)


additional_time = max(
    0,
    traffic_time - base_time
)


if base_time > 0:

    delay_percent = (
        additional_time
        /
        base_time
    ) * 100

else:

    delay_percent = 0


# ============================================================
# FIND TRAFFIC EDGES ON BASE ROUTE
# ============================================================

base_traffic_edges = []

for u, v, key in base_edges:

    edge = graph[
        u
    ][
        v
    ][
        key
    ]

    if edge.get(
        "traffic_observed",
        False
    ):

        base_traffic_edges.append(
            (
                u,
                v,
                key,
                edge
            )
        )


# ============================================================
# FIND TRAFFIC EDGES REMOVED
# ============================================================

congested_removed = []

for u, v, key in removed_edges:

    if not graph.has_edge(
        u,
        v,
        key
    ):

        continue

    edge = graph[
        u
    ][
        v
    ][
        key
    ]

    if edge.get(
        "traffic_observed",
        False
    ):

        congested_removed.append(
            (
                u,
                v,
                key,
                edge
            )
        )


# ============================================================
# RESULT
# ============================================================

print()
print("=" * 70)
print("CITY-WIDE TRAFFIC IMPACT RESULT")
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
print("TRAFFIC IMPACT")
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

    print(
        "Edges removed:",
        len(removed_edges)
    )

    print(
        "Edges added:",
        len(added_edges)
    )


# ============================================================
# TRAFFIC ON BASE ROUTE
# ============================================================

print()
print("=" * 70)
print("TRAFFIC EDGES ON BASE ROUTE")
print("=" * 70)

if base_traffic_edges:

    for u, v, key, edge in base_traffic_edges:

        print()
        print(
            "Road:",
            edge.get(
                "name",
                "Unnamed road"
            )
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
            edge.get(
                "live_current_speed_kmh"
            ),
            "km/h"
        )

        print(
            "Free-flow speed:",
            edge.get(
                "live_free_flow_speed_kmh"
            ),
            "km/h"
        )

        print(
            "Delay:",
            edge.get(
                "live_delay_percent"
            ),
            "%"
        )

        print(
            "Traffic weight:",
            edge.get(
                "traffic_weight_sec"
            ),
            "sec"
        )

else:

    print(
        "No directly observed traffic edges "
        "were present on the base route."
    )


# ============================================================
# CONGESTED EDGES REMOVED
# ============================================================

print()
print("=" * 70)
print("CONGESTED TRAFFIC EDGES REMOVED")
print("=" * 70)

if congested_removed:

    for u, v, key, edge in congested_removed:

        print()
        print(
            "Road:",
            edge.get(
                "name",
                "Unnamed road"
            )
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
            "Delay:",
            edge.get(
                "live_delay_percent"
            ),
            "%"
        )

        print(
            "Current speed:",
            edge.get(
                "live_current_speed_kmh"
            ),
            "km/h"
        )

else:

    print(
        "No directly observed congested edge "
        "was removed from the base route."
    )


# ============================================================
# FINAL VALIDATION
# ============================================================

print()
print("=" * 70)
print("FINAL VALIDATION")
print("=" * 70)

print(
    "City-wide traffic observations:",
    len(traffic)
)

print(
    "Traffic edges applied:",
    traffic_edges
)

print(
    "Closed edges:",
    closed_edges
)

print(
    "Base route:",
    f"{base_distance:.2f} km / "
    f"{base_time:.2f} min"
)

print(
    "Traffic route:",
    f"{traffic_distance:.2f} km / "
    f"{traffic_time:.2f} min"
)

print(
    "Route changed:",
    "YES"
    if base_route != traffic_route
    else "NO"
)

print(
    "Traffic edges on base route:",
    len(base_traffic_edges)
)

print(
    "Congested traffic edges removed:",
    len(congested_removed)
)

print()
print("=" * 70)
print("CITY-WIDE TRAFFIC IMPACT VALIDATION COMPLETE")
print("=" * 70)