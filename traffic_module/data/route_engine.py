import os
import math
import pickle
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\latest_graph_traffic.csv"


# ============================================================
# LOAD BENGALURU ROAD GRAPH
# ============================================================

print("Loading Bengaluru road graph...")

with open(GRAPH_FILE, "rb") as f:
    graph = pickle.load(f)

print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# LOAD LATEST LIVE TRAFFIC
# ============================================================

def load_latest_traffic():

    if not os.path.exists(TRAFFIC_FILE):
        print()
        print("WARNING: Live traffic file not found:")
        print(TRAFFIC_FILE)
        print("Using normal road speeds.")
        return pd.DataFrame()

    traffic = pd.read_csv(TRAFFIC_FILE)

    if traffic.empty:
        print("WARNING: Traffic file is empty.")
        return pd.DataFrame()

    # Keep successful observations
    if "status" in traffic.columns:
        traffic = traffic[
            traffic["status"]
            .astype(str)
            .str.upper()
            == "OK"
        ].copy()

    if traffic.empty:
        print("WARNING: No successful traffic observations.")
        return pd.DataFrame()

    # Latest snapshot only
    latest_timestamp = traffic["timestamp"].max()

    traffic = traffic[
        traffic["timestamp"] == latest_timestamp
    ].copy()

    print()
    print("Live traffic timestamp:", latest_timestamp)
    print("Live traffic observations:", len(traffic))

    return traffic


# ============================================================
# BUILD OSM EDGE → TRAFFIC LOOKUP
# ============================================================

def build_traffic_lookup(traffic):

    lookup = {}

    if traffic.empty:
        return lookup

    for _, row in traffic.iterrows():

        try:
            u = int(row["osm_u"])
            v = int(row["osm_v"])
            key = int(row["osm_key"])

            lookup[(u, v, key)] = row

        except Exception:
            continue

    return lookup


# ============================================================
# APPLY LIVE TRAFFIC TO GRAPH
# ============================================================

def apply_live_traffic():

    traffic = load_latest_traffic()

    lookup = build_traffic_lookup(
        traffic
    )

    live_edges = 0
    closed_edges = 0

    for u, v, key, data in graph.edges(
        keys=True,
        data=True
    ):

        # ----------------------------------------------------
        # Calculate normal/base travel time
        # ----------------------------------------------------

        length = float(
            data.get("length", 0)
        )

        speed = float(
            data.get("speed_kph", 0)
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

            base_time = 1.0

        data["base_weight_sec"] = base_time

        # Default: no live traffic
        data["traffic_weight_sec"] = base_time
        data["traffic_observed"] = False

        traffic_row = lookup.get(
            (u, v, key)
        )

        if traffic_row is None:
            continue

        # ----------------------------------------------------
        # Road closure
        # ----------------------------------------------------

        closure = traffic_row.get(
            "road_closure",
            False
        )

        closure_text = str(
            closure
        ).lower()

        if closure_text in [
            "true",
            "1",
            "yes"
        ]:

            data["traffic_weight_sec"] = float(
                "inf"
            )

            data["traffic_observed"] = True
            data["live_road_closure"] = True

            closed_edges += 1
            live_edges += 1

            continue

        # ----------------------------------------------------
        # Current TomTom travel time
        # ----------------------------------------------------

        live_time = traffic_row.get(
            "current_travel_time_sec"
        )

        if pd.notna(live_time):

            live_time = float(
                live_time
            )

            if live_time > 0:

                data[
                    "traffic_weight_sec"
                ] = live_time

                data[
                    "traffic_observed"
                ] = True

        else:

            # ------------------------------------------------
            # Fallback to current speed
            # ------------------------------------------------

            current_speed = traffic_row.get(
                "current_speed_kmh"
            )

            if (
                pd.notna(current_speed)
                and float(current_speed) > 0
                and length > 0
            ):

                speed_mps = (
                    float(current_speed)
                    * 1000
                    / 3600
                )

                data[
                    "traffic_weight_sec"
                ] = (
                    length
                    /
                    speed_mps
                )

                data[
                    "traffic_observed"
                ] = True

        # ----------------------------------------------------
        # Store live information
        # ----------------------------------------------------

        data[
            "live_current_speed_kmh"
        ] = traffic_row.get(
            "current_speed_kmh"
        )

        data[
            "live_free_flow_speed_kmh"
        ] = traffic_row.get(
            "free_flow_speed_kmh"
        )

        data[
            "live_delay_percent"
        ] = traffic_row.get(
            "delay_percent"
        )

        data[
            "live_confidence"
        ] = traffic_row.get(
            "confidence"
        )

        data[
            "live_road_closure"
        ] = traffic_row.get(
            "road_closure"
        )

        if data["traffic_observed"]:
            live_edges += 1

    return live_edges, closed_edges


# ============================================================
# NEAREST NODE
# ============================================================

def nearest_node(
    latitude,
    longitude
):

    best_node = None
    best_distance = float("inf")

    for node, data in graph.nodes(
        data=True
    ):

        lat = data.get("y")
        lon = data.get("x")

        if lat is None or lon is None:
            continue

        dlat = (
            float(lat)
            -
            float(latitude)
        )

        dlon = (
            float(lon)
            -
            float(longitude)
        )

        distance = (
            dlat * dlat
            +
            dlon * dlon
        )

        if distance < best_distance:

            best_distance = distance
            best_node = node

    if best_node is None:
        raise ValueError(
            "Could not find nearest graph node."
        )

    return best_node


# ============================================================
# GET BEST EDGE BETWEEN TWO NODES
# ============================================================

def get_best_edge(
    u,
    v
):

    options = graph[u][v]

    best_key = None
    best_edge = None
    best_weight = float("inf")

    for key, data in options.items():

        weight = data.get(
            "traffic_weight_sec",
            data.get(
                "base_weight_sec",
                float("inf")
            )
        )

        if weight < best_weight:

            best_weight = weight
            best_key = key
            best_edge = data

    return best_key, best_edge


# ============================================================
# CALCULATE TRAFFIC-AWARE ROUTE
# ============================================================

def calculate_traffic_route(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon
):

    live_edges, closed_edges = (
        apply_live_traffic()
    )

    source_node = nearest_node(
        source_lat,
        source_lon
    )

    destination_node = nearest_node(
        destination_lat,
        destination_lon
    )

    print()
    print("=" * 60)
    print("CALCULATING BENGALURU TRAFFIC-AWARE ROUTE")
    print("=" * 60)

    print(
        "Source node:",
        source_node
    )

    print(
        "Destination node:",
        destination_node
    )

    print(
        "Live traffic edges:",
        live_edges
    )

    print(
        "Closed traffic edges:",
        closed_edges
    )

    # --------------------------------------------------------
    # Traffic-aware shortest path
    # --------------------------------------------------------

    route_nodes = nx.shortest_path(
        graph,
        source=source_node,
        target=destination_node,
        weight="traffic_weight_sec"
    )

    distance_m = 0.0
    base_time_sec = 0.0
    current_time_sec = 0.0

    route_edges = []

    for i in range(
        len(route_nodes) - 1
    ):

        u = route_nodes[i]
        v = route_nodes[i + 1]

        key, edge = get_best_edge(
            u,
            v
        )

        if edge is None:
            continue

        distance_m += float(
            edge.get(
                "length",
                0
            )
        )

        base_time_sec += float(
            edge.get(
                "base_weight_sec",
                0
            )
        )

        current_time_sec += float(
            edge.get(
                "traffic_weight_sec",
                edge.get(
                    "base_weight_sec",
                    0
                )
            )
        )

        route_edges.append(
            (
                u,
                v,
                key,
                edge
            )
        )

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    distance_km = (
        distance_m / 1000
    )

    base_time_min = (
        base_time_sec / 60
    )

    current_time_min = (
        current_time_sec / 60
    )

    delay_min = max(
        0,
        current_time_min
        -
        base_time_min
    )

    if current_time_min > 0:

        current_speed = (
            distance_km
            /
            (
                current_time_min
                /
                60
            )
        )

    else:

        current_speed = 0

    if base_time_min > 0:

        base_speed = (
            distance_km
            /
            (
                base_time_min
                /
                60
            )
        )

    else:

        base_speed = 0

    # --------------------------------------------------------
    # Road names
    # --------------------------------------------------------

    road_names = []

    for _, _, _, edge in route_edges:

        name = edge.get("name")

        if isinstance(name, list):

            names = name

        else:

            names = [name]

        for name_item in names:

            if name_item is None:
                continue

            name_text = str(
                name_item
            ).strip()

            if (
                name_text
                and name_text
                not in road_names
            ):

                road_names.append(
                    name_text
                )

    # --------------------------------------------------------
    # Traffic observations actually used
    # --------------------------------------------------------

    traffic_points = []

    for u, v, key, edge in route_edges:

        if not edge.get(
            "traffic_observed",
            False
        ):

            continue

        traffic_points.append({

            "osm_u": u,

            "osm_v": v,

            "osm_key": key,

            "road_name":
                edge.get("name"),

            "current_speed_kmh":
                edge.get(
                    "live_current_speed_kmh"
                ),

            "free_flow_speed_kmh":
                edge.get(
                    "live_free_flow_speed_kmh"
                ),

            "delay_percent":
                edge.get(
                    "live_delay_percent"
                ),

            "confidence":
                edge.get(
                    "live_confidence"
                ),

            "road_closure":
                edge.get(
                    "live_road_closure"
                )
        })

    # --------------------------------------------------------
    # Traffic status
    # --------------------------------------------------------

    if current_time_min <= base_time_min * 1.05:

        traffic_status = "FREE FLOW"

    elif current_time_min <= base_time_min * 1.20:

        traffic_status = "MODERATE"

    elif current_time_min <= base_time_min * 1.50:

        traffic_status = "HEAVY"

    else:

        traffic_status = "CRITICAL"

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence_values = []

    for point in traffic_points:

        value = point.get(
            "confidence"
        )

        if value is None:
            continue

        try:

            confidence_values.append(
                float(value)
            )

        except Exception:

            pass

    if confidence_values:

        confidence = (
            sum(confidence_values)
            /
            len(confidence_values)
        )

    else:

        confidence = 0.0

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = {

        "source_node":
            source_node,

        "destination_node":
            destination_node,

        "route_nodes":
            route_nodes,

        "distance_km":
            round(
                distance_km,
                2
            ),

        "base_travel_time_min":
            round(
                base_time_min,
                2
            ),

        "current_travel_time_min":
            round(
                current_time_min,
                2
            ),

        "predicted_travel_time_min":
            round(
                current_time_min,
                2
            ),

        "delay_min":
            round(
                delay_min,
                2
            ),

        "base_speed_kmh":
            round(
                base_speed,
                2
            ),

        "current_speed_kmh":
            round(
                current_speed,
                2
            ),

        "predicted_speed_kmh":
            round(
                current_speed,
                2
            ),

        "traffic_status":
            traffic_status,

        "confidence":
            round(
                confidence,
                3
            ),

        "road_names":
            road_names,

        "traffic_points":
            traffic_points
    }

    return result


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("CALCULATING BENGALURU ROUTE")
    print("=" * 60)

    # Hebbal → Marathahalli

    result = calculate_traffic_route(

        source_lat=13.0358,

        source_lon=77.5970,

        destination_lat=12.9591,

        destination_lon=77.6974
    )

    print()
    print("=" * 60)
    print("TRAFFIC-AWARE ROUTE RESULT")
    print("=" * 60)

    print(
        "Distance:",
        result["distance_km"],
        "km"
    )

    print(
        "Base travel time:",
        result["base_travel_time_min"],
        "min"
    )

    print(
        "Current travel time:",
        result["current_travel_time_min"],
        "min"
    )

    print(
        "Delay:",
        result["delay_min"],
        "min"
    )

    print(
        "Base speed:",
        result["base_speed_kmh"],
        "km/h"
    )

    print(
        "Current speed:",
        result["current_speed_kmh"],
        "km/h"
    )

    print(
        "Traffic:",
        result["traffic_status"]
    )

    print(
        "Confidence:",
        result["confidence"]
    )

    print()
    print("Roads:")

    for road in result["road_names"]:

        print(
            " -",
            road
        )

    print()
    print(
        "Traffic observations used:",
        len(
            result[
                "traffic_points"
            ]
        )
    )

    print()
    print("=" * 60)
    print("ROUTE ENGINE TEST COMPLETE")
    print("=" * 60)