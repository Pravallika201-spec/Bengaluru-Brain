import pickle
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = (
    r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"
)

SOURCE = 10118500634
DESTINATION = 6528219586


# ============================================================
# HEADER
# ============================================================

print("=" * 70)
print("ROAD CLOSURE REROUTING VALIDATION")
print("=" * 70)


# ============================================================
# LOAD GRAPH
# ============================================================

print()
print("Loading Bengaluru road graph...")

with open(
    GRAPH_FILE,
    "rb"
) as f:

    graph = pickle.load(f)


print(
    "Graph type:",
    type(graph).__name__
)

print(
    "Nodes:",
    len(graph.nodes)
)

print(
    "Edges:",
    len(graph.edges)
)


# ============================================================
# CHECK SOURCE / DESTINATION
# ============================================================

print()
print("Checking source and destination...")

if SOURCE not in graph:

    raise SystemExit(
        "ERROR: Source node not found."
    )


if DESTINATION not in graph:

    raise SystemExit(
        "ERROR: Destination node not found."
    )


print(
    "Source:",
    SOURCE
)

print(
    "Destination:",
    DESTINATION
)


# ============================================================
# PREPARE BASE AND TRAFFIC WEIGHTS
# ============================================================

print()
print("Preparing travel-time weights...")


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


    # --------------------------------------------------------
    # Calculate base travel time
    # --------------------------------------------------------

    if (
        length > 0
        and
        speed > 0
    ):

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


    # --------------------------------------------------------
    # Store base weight
    # --------------------------------------------------------

    data[
        "base_weight_sec"
    ] = base_time


    # --------------------------------------------------------
    # Initially traffic = normal traffic
    # --------------------------------------------------------

    data[
        "traffic_weight_sec"
    ] = base_time


    # --------------------------------------------------------
    # Initially no closure
    # --------------------------------------------------------

    data[
        "live_road_closure"
    ] = False


# ============================================================
# CALCULATE BASE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING BASE ROUTE")
print("=" * 70)


base_route = nx.shortest_path(
    graph,
    SOURCE,
    DESTINATION,
    weight="base_weight_sec"
)


print()
print(
    "Base route nodes:",
    len(base_route)
)


# ============================================================
# CHECK ROUTE LENGTH
# ============================================================

if len(base_route) < 3:

    raise SystemExit(
        "ERROR: Base route is too short for closure testing."
    )


# ============================================================
# SELECT MIDDLE EDGE
# ============================================================

middle_index = (
    len(base_route)
    //
    2
)


closure_u = base_route[
    middle_index
]


closure_v = base_route[
    middle_index + 1
]


# ============================================================
# FIND BEST EDGE BETWEEN ROUTE NODES
# ============================================================

edge_options = graph[
    closure_u
][
    closure_v
]


closure_key = None
closure_data = None
closure_weight = float("inf")


for key, data in edge_options.items():

    weight = float(
        data.get(
            "base_weight_sec",
            float("inf")
        )
    )


    if weight < closure_weight:

        closure_weight = weight

        closure_key = key

        closure_data = data


if closure_data is None:

    raise SystemExit(
        "ERROR: Could not select closure edge."
    )


# ============================================================
# SIMULATE ROAD CLOSURE
# ============================================================

print()
print("=" * 70)
print("SIMULATING ROAD CLOSURE")
print("=" * 70)


print()
print("Closed edge:")

print(
    "From:",
    closure_u
)

print(
    "To:",
    closure_v
)

print(
    "Key:",
    closure_key
)

print(
    "Base travel time:",
    f"{closure_weight:.2f} sec"
)


# ------------------------------------------------------------
# Close selected edge
# ------------------------------------------------------------

closure_data[
    "traffic_weight_sec"
] = float("inf")


closure_data[
    "live_road_closure"
] = True


closure_data[
    "traffic_observed"
] = True


# ============================================================
# CALCULATE TRAFFIC-AWARE ROUTE
# ============================================================

print()
print("=" * 70)
print("CALCULATING ROUTE WITH ROAD CLOSURE")
print("=" * 70)


traffic_route = nx.shortest_path(
    graph,
    SOURCE,
    DESTINATION,
    weight="traffic_weight_sec"
)


print()
print(
    "Traffic route nodes:",
    len(traffic_route)
)


# ============================================================
# CHECK CLOSED EDGE
# ============================================================

closed_edge_used = False


for i in range(
    len(traffic_route) - 1
):

    u = traffic_route[i]

    v = traffic_route[i + 1]


    if (
        u == closure_u
        and
        v == closure_v
    ):

        closed_edge_used = True

        break


# ============================================================
# ROUTE DISTANCE
# ============================================================

def calculate_distance(route):

    total = 0.0


    for i in range(
        len(route) - 1
    ):

        u = route[i]

        v = route[i + 1]


        options = graph[
            u
        ][
            v
        ]


        best_length = float(
            "inf"
        )


        for key, data in options.items():

            length = float(
                data.get(
                    "length",
                    0
                )
            )


            if length > 0:

                best_length = min(
                    best_length,
                    length
                )


        if best_length != float("inf"):

            total += best_length


    return total / 1000


# ============================================================
# ROUTE TRAVEL TIME
# ============================================================

def calculate_time(
    route,
    weight_name
):

    total = 0.0


    for i in range(
        len(route) - 1
    ):

        u = route[i]

        v = route[i + 1]


        options = graph[
            u
        ][
            v
        ]


        best_weight = float(
            "inf"
        )


        for key, data in options.items():

            # ------------------------------------------------
            # Get requested weight
            # ------------------------------------------------

            weight = data.get(
                weight_name
            )


            # ------------------------------------------------
            # If traffic weight doesn't exist,
            # use base weight.
            # ------------------------------------------------

            if weight is None:

                weight = data.get(
                    "base_weight_sec"
                )


            # ------------------------------------------------
            # Convert safely
            # ------------------------------------------------

            try:

                weight = float(
                    weight
                )

            except (
                TypeError,
                ValueError
            ):

                continue


            # ------------------------------------------------
            # Select smallest valid edge weight
            # ------------------------------------------------

            if weight < best_weight:

                best_weight = weight


        # ----------------------------------------------------
        # Make sure a valid weight exists
        # ----------------------------------------------------

        if best_weight == float("inf"):

            raise RuntimeError(
                "No valid travel-time weight "
                f"for edge {u} -> {v}"
            )


        total += best_weight


    return total / 60


# ============================================================
# CALCULATE RESULTS
# ============================================================

base_distance = calculate_distance(
    base_route
)


traffic_distance = calculate_distance(
    traffic_route
)


base_time = calculate_time(
    base_route,
    "base_weight_sec"
)


traffic_time = calculate_time(
    traffic_route,
    "traffic_weight_sec"
)


# ============================================================
# CREATE EDGE SETS
# ============================================================

base_edges = set()


for i in range(
    len(base_route) - 1
):

    base_edges.add(
        (
            base_route[i],
            base_route[i + 1]
        )
    )


traffic_edges = set()


for i in range(
    len(traffic_route) - 1
):

    traffic_edges.add(
        (
            traffic_route[i],
            traffic_route[i + 1]
        )
    )


# ============================================================
# COMPARE ROUTES
# ============================================================

removed_edges = (
    base_edges
    -
    traffic_edges
)


added_edges = (
    traffic_edges
    -
    base_edges
)


# ============================================================
# RESULT
# ============================================================

print()
print("=" * 70)
print("ROAD CLOSURE REROUTING RESULT")
print("=" * 70)


# ============================================================
# BASE ROUTE
# ============================================================

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


# ============================================================
# CLOSURE
# ============================================================

print()
print("ROAD CLOSURE")
print("-" * 70)


print(
    "Closed edge:",
    closure_u,
    "->",
    closure_v,
    "key:",
    closure_key
)


print(
    "Closed edge base time:",
    f"{closure_weight:.2f} sec"
)


# ============================================================
# TRAFFIC ROUTE
# ============================================================

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


# ============================================================
# ROUTE CHANGE
# ============================================================

print()
print("ROUTE CHANGE")
print("-" * 70)


if closed_edge_used:

    print(
        "FAIL: Traffic-aware route "
        "still uses the closed edge."
    )

else:

    print(
        "SUCCESS: Traffic-aware route "
        "avoided the closed edge!"
    )


print()
print(
    "Base route edges:",
    len(base_edges)
)


print(
    "Traffic route edges:",
    len(traffic_edges)
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
# FINAL VALIDATION
# ============================================================

print()
print("=" * 70)
print("FINAL VALIDATION")
print("=" * 70)


if (
    not closed_edge_used
    and
    traffic_time != float("inf")
):

    print(
        "PASS: Road closure successfully "
        "triggered rerouting."
    )

else:

    print(
        "FAIL: Road closure validation failed."
    )


# ============================================================
# COMPLETE
# ============================================================

print()
print("=" * 70)
print("ROAD CLOSURE VALIDATION COMPLETE")
print("=" * 70)