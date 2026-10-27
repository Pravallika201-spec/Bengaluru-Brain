import os
import pickle
import pandas as pd
import networkx as nx
import math


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\traffic_module\data\live_traffic_history.csv"

OUTPUT_FILE = r"D:\major project\latest_graph_traffic.csv"


# ============================================================
# LOAD GRAPH
# ============================================================

print("=" * 70)
print("MAPPING LIVE TRAFFIC TO BENGALURU ROAD GRAPH")
print("=" * 70)

print()
print("Loading graph...")

with open(GRAPH_FILE, "rb") as f:
    graph = pickle.load(f)

print("Graph nodes:", len(graph.nodes))
print("Graph edges:", len(graph.edges))


# ============================================================
# LOAD LIVE TRAFFIC
# ============================================================

print()
print("Loading traffic data...")

traffic = pd.read_csv(TRAFFIC_FILE)

print("Traffic rows:", len(traffic))

# Keep successful API observations only
traffic = traffic[
    traffic["status"].astype(str).str.upper() == "OK"
].copy()

if len(traffic) == 0:
    raise SystemExit("ERROR: No successful traffic observations found.")


# ============================================================
# LATEST SNAPSHOT
# ============================================================

latest_timestamp = traffic["timestamp"].max()

latest = traffic[
    traffic["timestamp"] == latest_timestamp
].copy()

print("Latest timestamp:", latest_timestamp)
print("Latest observations:", len(latest))


# ============================================================
# DEDUPLICATE LOCATIONS
# ============================================================

latest = (
    latest
    .sort_values("confidence", ascending=False)
    .drop_duplicates("traffic_location")
    .copy()
)

print("Unique traffic locations:", len(latest))


# ============================================================
# BUILD NODE LOOKUP
# ============================================================

print()
print("Preparing graph node lookup...")

node_lookup = {}

for node in graph.nodes:

    try:
        lat = graph.nodes[node].get("y")
        lon = graph.nodes[node].get("x")

        if lat is None or lon is None:
            continue

        node_lookup[int(node)] = (
            float(lat),
            float(lon)
        )

    except Exception:
        continue

print("Graph nodes with coordinates:", len(node_lookup))


# ============================================================
# FIND NEARBY GRAPH NODES
# ============================================================

def haversine_distance(lat1, lon1, lat2, lon2):

    R = 6371000.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c


def find_nearest_node(lat, lon):

    best_node = None
    best_distance = float("inf")

    for node, coords in node_lookup.items():

        node_lat, node_lon = coords

        distance = haversine_distance(
            lat,
            lon,
            node_lat,
            node_lon
        )

        if distance < best_distance:

            best_distance = distance
            best_node = node

    return best_node, best_distance


# ============================================================
# MAP TRAFFIC LOCATIONS TO GRAPH
# ============================================================

print()
print("Mapping live traffic locations to graph...")

mapped_rows = []

for _, row in latest.iterrows():

    location = str(row["traffic_location"])

    latitude = float(row["latitude"])
    longitude = float(row["longitude"])

    # Collector already provides nearest_node.
    try:
        nearest_node = int(float(row["nearest_node"]))
    except Exception:
        nearest_node = None

    # Verify that node exists in graph.
    if nearest_node not in graph.nodes:

        nearest_node, distance = find_nearest_node(
            latitude,
            longitude
        )

    else:

        node_lat, node_lon = node_lookup.get(
            nearest_node,
            (latitude, longitude)
        )

        distance = haversine_distance(
            latitude,
            longitude,
            node_lat,
            node_lon
        )

    if nearest_node is None:

        print(
            "WARNING: Could not map:",
            location
        )

        continue

    print(
        f"{location:25s} -> "
        f"node {nearest_node} "
        f"({distance:.1f} m)"
    )


    # --------------------------------------------------------
    # Traffic values
    # --------------------------------------------------------

    current_speed = float(
        row["current_speed_kmh"]
    )

    free_flow_speed = float(
        row["free_flow_speed_kmh"]
    )

    delay_percent = float(
        row["delay_percent"]
    )

    confidence = float(
        row["confidence"]
    )

    road_closure = str(
        row["road_closure"]
    ).lower() in [
        "true",
        "1",
        "yes"
    ]


    # ========================================================
    # FIND EDGES CONNECTED TO THIS NODE
    # ========================================================

    try:

        edges = list(
            graph.edges(
                nearest_node,
                keys=True,
                data=True
            )
        )

    except TypeError:

        # Handle normal Graph instead of MultiDiGraph
        edges = []

        for u, v, data in graph.edges(
            nearest_node,
            data=True
        ):

            edges.append(
                (
                    u,
                    v,
                    0,
                    data
                )
            )


    # --------------------------------------------------------
    # Also check incoming edges
    # --------------------------------------------------------

    try:

        incoming = list(
            graph.in_edges(
                nearest_node,
                keys=True,
                data=True
            )
        )

        edges.extend(incoming)

    except Exception:

        pass


    # Remove duplicate edge tuples
    seen_edges = set()


    for edge in edges:

        if len(edge) == 4:

            u, v, key, edge_data = edge

        else:

            continue


        edge_id = (
            int(u),
            int(v),
            int(key)
        )

        if edge_id in seen_edges:
            continue

        seen_edges.add(edge_id)


        # ----------------------------------------------------
        # Edge length
        # ----------------------------------------------------

        length = float(
            edge_data.get(
                "length",
                0
            )
        )


        if length <= 0:
            continue


        # ----------------------------------------------------
        # Traffic travel time
        # ----------------------------------------------------

        if road_closure:

            traffic_weight = float("inf")

        elif current_speed > 0:

            speed_mps = (
                current_speed
                * 1000
                / 3600
            )

            traffic_weight = (
                length / speed_mps
            )

        else:

            traffic_weight = float("inf")


        # ----------------------------------------------------
        # Road information
        # ----------------------------------------------------

        road_name = edge_data.get(
            "name",
            ""
        )

        highway = edge_data.get(
            "highway",
            ""
        )

        if isinstance(
            road_name,
            list
        ):

            road_name = ", ".join(
                map(str, road_name)
            )

        if isinstance(
            highway,
            list
        ):

            highway = ", ".join(
                map(str, highway)
            )


        # ----------------------------------------------------
        # Save mapped edge
        # ----------------------------------------------------

        mapped_rows.append({

            "timestamp":
                latest_timestamp,

            "osm_u":
                u,

            "osm_v":
                v,

            "osm_key":
                key,

            "osm_road_name":
                road_name,

            "osm_highway":
                highway,

            "sample_latitude":
                latitude,

            "sample_longitude":
                longitude,

            "nearest_node":
                nearest_node,

            "traffic_location":
                location,

            "current_speed_kmh":
                current_speed,

            "free_flow_speed_kmh":
                free_flow_speed,

            "current_travel_time_sec":
                row[
                    "current_travel_time_sec"
                ],

            "free_flow_travel_time_sec":
                row[
                    "free_flow_travel_time_sec"
                ],

            "delay_percent":
                delay_percent,

            "confidence":
                confidence,

            "road_closure":
                road_closure,

            "traffic_weight_sec":
                traffic_weight
        })


# ============================================================
# CREATE DATAFRAME
# ============================================================

mapped = pd.DataFrame(
    mapped_rows
)


if len(mapped) == 0:

    raise SystemExit(
        "ERROR: No graph edges were mapped."
    )


# ============================================================
# REMOVE DUPLICATE EDGES
# ============================================================

mapped = (
    mapped
    .sort_values(
        "confidence",
        ascending=False
    )
    .drop_duplicates(
        subset=[
            "osm_u",
            "osm_v",
            "osm_key"
        ]
    )
    .copy()
)


# ============================================================
# SPEED RATIO
# ============================================================

mapped["speed_ratio"] = (
    mapped["current_speed_kmh"]
    /
    mapped["free_flow_speed_kmh"]
)


# ============================================================
# SAVE
# ============================================================

mapped.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("TRAFFIC MAPPING COMPLETE")
print("=" * 70)

print(
    "Latest timestamp:",
    latest_timestamp
)

print(
    "Traffic observations:",
    len(latest)
)

print(
    "Traffic locations mapped:",
    latest["traffic_location"].nunique()
)

print(
    "Mapped OSM edges:",
    len(mapped)
)

print(
    "Road closures:",
    int(
        mapped["road_closure"]
        .fillna(False)
        .astype(bool)
        .sum()
    )
)

print(
    "Average current speed:",
    round(
        mapped["current_speed_kmh"].mean(),
        2
    ),
    "km/h"
)

print(
    "Average free-flow speed:",
    round(
        mapped["free_flow_speed_kmh"].mean(),
        2
    ),
    "km/h"
)

print(
    "Average delay:",
    round(
        mapped["delay_percent"].mean(),
        2
    ),
    "%"
)

print(
    "Output:",
    OUTPUT_FILE
)

print("=" * 70)