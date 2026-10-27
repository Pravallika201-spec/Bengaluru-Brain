import os
import pickle
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_DIR = r"D:\major project"

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
print("FINAL BENGALURU TRAFFIC ROUTING PROJECT VALIDATION")
print("=" * 70)


# ============================================================
# CHECK GRAPH FILE
# ============================================================

print()
print("=" * 70)
print("1. GRAPH VALIDATION")
print("=" * 70)

if not os.path.exists(GRAPH_FILE):

    print("FAIL: Graph file not found.")
    raise SystemExit(1)

print("Graph file: OK")

with open(GRAPH_FILE, "rb") as f:
    graph = pickle.load(f)

print("Graph type:", type(graph).__name__)
print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))

if not isinstance(graph, nx.MultiDiGraph):

    print("FAIL: Graph is not a MultiDiGraph.")
    raise SystemExit(1)

print("MultiDiGraph: PASS")


# ============================================================
# CHECK SOURCE / DESTINATION
# ============================================================

print()
print("=" * 70)
print("2. SOURCE / DESTINATION VALIDATION")
print("=" * 70)

print("Source:", SOURCE_NODE)
print("Destination:", DESTINATION_NODE)

if SOURCE_NODE not in graph:

    print("FAIL: Source node not found.")
    raise SystemExit(1)

if DESTINATION_NODE not in graph:

    print("FAIL: Destination node not found.")
    raise SystemExit(1)

print("Source node: PASS")
print("Destination node: PASS")


# ============================================================
# PREPARE BASE WEIGHTS
# ============================================================

print()
print("=" * 70)
print("3. BASE EDGE WEIGHTS")
print("=" * 70)

base_weight_count = 0

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

        data[
            "base_weight_sec"
        ] = base_time

        data[
            "traffic_weight_sec"
        ] = base_time

        base_weight_count += 1


print(
    "Base weights created:",
    base_weight_count
)

if base_weight_count == 0:

    print("FAIL: No valid base weights.")
    raise SystemExit(1)

print("Base weights: PASS")


# ============================================================
# LOAD TRAFFIC
# ============================================================

print()
print("=" * 70)
print("4. CITY-WIDE TRAFFIC VALIDATION")
print("=" * 70)

if not os.path.exists(TRAFFIC_FILE):

    print("FAIL: Traffic file not found.")
    raise SystemExit(1)

traffic = pd.read_csv(
    TRAFFIC_FILE
)

print(
    "Traffic observations:",
    len(traffic)
)

if len(traffic) == 0:

    print("FAIL: Traffic dataset is empty.")
    raise SystemExit(1)


# ============================================================
# SUCCESSFUL OBSERVATIONS
# ============================================================

successful = traffic[
    traffic[
        "status"
    ]
    .astype(str)
    .str.upper()
    == "OK"
].copy()

print(
    "Successful observations:",
    len(successful)
)

if len(successful) == 0:

    print("FAIL: No successful traffic observations.")
    raise SystemExit(1)

print("Traffic data: PASS")


# ============================================================
# APPLY TRAFFIC
# ============================================================

print()
print("=" * 70)
print("5. APPLYING TRAFFIC TO GRAPH")
print("=" * 70)

traffic_edges = 0
closed_edges = 0
not_found = 0

for _, row in successful.iterrows():

    try:

        u = int(row["osm_u"])
        v = int(row["osm_v"])
        key = int(row["osm_key"])

    except Exception:

        not_found += 1
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
            1.0
        )
    )


    road_closure = str(
        row.get(
            "road_closure",
            False
        )
    ).lower() in [
        "true",
        "1",
        "yes"
    ]


    if road_closure:

        edge[
            "traffic_weight_sec"
        ] = float("inf")

        edge[
            "live_road_closure"
        ] = True

        closed_edges += 1

        continue


    current_speed = float(
        row.get(
            "current_speed_kmh",
            0
        )
    )

    free_flow_speed = float(
        row.get(
            "free_flow_speed_kmh",
            0
        )
    )


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
            "live_current_speed_kmh"
        ] = current_speed

        edge[
            "live_free_flow_speed_kmh"
        ] = free_flow_speed

        edge[
            "live_delay_percent"
        ] = row.get(
            "delay_percent",
            0
        )

        edge[
            "live_confidence"
        ] = row.get(
            "confidence",
            0
        )

        edge[
            "traffic_observed"
        ] = True

        edge[
            "live_road_closure"
        ] = False

        traffic_edges += 1


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

if not_found != 0:

    print(
        "WARNING: Some traffic observations "
        "could not be mapped."
    )

else:

    print("Traffic mapping: PASS")


# ============================================================
# BASE ROUTE
# ============================================================

print()
print("=" * 70)
print("6. BASE ROUTE VALIDATION")
print("=" * 70)

try:

    base_route = nx.shortest_path(
        graph,
        SOURCE_NODE,
        DESTINATION_NODE,
        weight="base_weight_sec"
    )

except nx.NetworkXNoPath:

    print("FAIL: No base route exists.")
    raise SystemExit(1)


print(
    "Base route nodes:",
    len(base_route)
)

print("Base route: PASS")


# ============================================================
# TRAFFIC ROUTE
# ============================================================

print()
print("=" * 70)
print("7. TRAFFIC-AWARE ROUTE VALIDATION")
print("=" * 70)

try:

    traffic_route = nx.shortest_path(
        graph,
        SOURCE_NODE,
        DESTINATION_NODE,
        weight="traffic_weight_sec"
    )

except nx.NetworkXNoPath:

    print(
        "FAIL: No traffic-aware route exists."
    )

    raise SystemExit(1)


print(
    "Traffic-aware route nodes:",
    len(traffic_route)
)

print("Traffic-aware routing: PASS")


# ============================================================
# ROUTE METRICS
# ============================================================

def route_distance(route):

    total = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        best = float("inf")

        for key, data in graph[
            u
        ][
            v
        ].items():

            length = float(
                data.get(
                    "length",
                    0
                )
            )

            if length > 0:

                best = min(
                    best,
                    length
                )

        if best != float("inf"):

            total += best

    return total / 1000


def route_time(
    route,
    weight_name
):

    total = 0.0

    for i in range(
        len(route) - 1
    ):

        u = route[i]
        v = route[i + 1]

        best = float("inf")

        for key, data in graph[
            u
        ][
            v
        ].items():

            weight = float(
                data.get(
                    weight_name,
                    float("inf")
                )
            )

            best = min(
                best,
                weight
            )

        total += best

    return total / 60


base_distance = route_distance(
    base_route
)

traffic_distance = route_distance(
    traffic_route
)

base_time = route_time(
    base_route,
    "base_weight_sec"
)

traffic_time = route_time(
    traffic_route,
    "traffic_weight_sec"
)


# ============================================================
# ROUTE COMPARISON
# ============================================================

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

    delay_percent = 0


base_edges = set(
    zip(
        base_route[:-1],
        base_route[1:]
    )
)

traffic_edges_set = set(
    zip(
        traffic_route[:-1],
        traffic_route[1:]
    )
)

removed_edges = (
    base_edges
    -
    traffic_edges_set
)

added_edges = (
    traffic_edges_set
    -
    base_edges
)


# ============================================================
# FINAL RESULT
# ============================================================

print()
print("=" * 70)
print("FINAL PROJECT VALIDATION RESULT")
print("=" * 70)

print()
print("GRAPH")
print("-" * 70)
print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))

print()
print("TRAFFIC")
print("-" * 70)
print(
    "Observations:",
    len(successful)
)
print(
    "Applied:",
    traffic_edges
)
print(
    "Closed:",
    closed_edges
)
print(
    "Not found:",
    not_found
)

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
    f"Additional time: "
    f"{additional_time:.2f} min"
)

print(
    f"Traffic delay: "
    f"{delay_percent:.2f} %"
)

print()
print("ROUTE CHANGE")
print("-" * 70)

if base_route == traffic_route:

    print(
        "Traffic-aware route is the SAME "
        "as the base route."
    )

else:

    print(
        "Traffic-aware route CHANGED."
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
# TRAFFIC OBSERVATIONS ON FINAL ROUTE
# ============================================================

route_traffic_count = 0

for i in range(
    len(traffic_route) - 1
):

    u = traffic_route[i]
    v = traffic_route[i + 1]

    for key, data in graph[
        u
    ][
        v
    ].items():

        if data.get(
            "traffic_observed",
            False
        ):

            route_traffic_count += 1

            break


print()
print("=" * 70)
print("FINAL TRAFFIC COVERAGE")
print("=" * 70)

print(
    "Traffic observations on final route:",
    route_traffic_count
)


# ============================================================
# OVERALL STATUS
# ============================================================

print()
print("=" * 70)
print("OVERALL PROJECT STATUS")
print("=" * 70)

checks = [
    ("Graph loaded", True),
    ("Source node valid", SOURCE_NODE in graph),
    ("Destination node valid", DESTINATION_NODE in graph),
    ("Base weights created", base_weight_count > 0),
    ("Traffic data available", len(successful) > 0),
    ("Traffic routing successful", True),
]

all_pass = True

for name, result in checks:

    if result:

        print(
            "[PASS]",
            name
        )

    else:

        print(
            "[FAIL]",
            name
        )

        all_pass = False


print()

if all_pass:

    print(
        "FINAL STATUS: PROJECT VALIDATION PASSED"
    )

else:

    print(
        "FINAL STATUS: PROJECT VALIDATION FAILED"
    )

print()
print("=" * 70)
print("FINAL PROJECT VALIDATION COMPLETE")
print("=" * 70)