import os
import pickle
import math
import requests
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\latest_graph_traffic.csv"

OSM_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

USER_AGENT = "Bengaluru-Traffic-Route-Engine/1.0"


# ============================================================
# GLOBAL GRAPH
# ============================================================

graph = None


# ============================================================
# PRINT SECTION
# ============================================================

def print_section(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# ============================================================
# LOAD GRAPH
# ============================================================

def load_graph():

    global graph

    print_section("LOADING BENGALURU ROAD GRAPH")

    if not os.path.exists(GRAPH_FILE):

        print("ERROR: Graph file not found:")
        print(GRAPH_FILE)

        return False

    try:

        with open(
            GRAPH_FILE,
            "rb"
        ) as file:

            graph = pickle.load(file)

    except Exception as error:

        print("ERROR loading graph:")
        print(error)

        return False

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

    return True


# ============================================================
# LOAD LATEST TRAFFIC
# ============================================================

def load_latest_traffic():

    print_section("LOADING LIVE TRAFFIC")

    if not os.path.exists(TRAFFIC_FILE):

        print("WARNING: Traffic file not found:")
        print(TRAFFIC_FILE)

        return pd.DataFrame()

    try:

        traffic = pd.read_csv(
            TRAFFIC_FILE
        )

    except Exception as error:

        print("ERROR reading traffic CSV:")
        print(error)

        return pd.DataFrame()

    if traffic.empty:

        print("WARNING: Traffic file is empty.")

        return pd.DataFrame()

    # --------------------------------------------------------
    # Keep successful observations
    # --------------------------------------------------------

    if "status" in traffic.columns:

        traffic = traffic[
            traffic["status"]
            .astype(str)
            .str.upper()
            == "OK"
        ].copy()

    if traffic.empty:

        print(
            "WARNING: No successful traffic observations."
        )

        return pd.DataFrame()

    # --------------------------------------------------------
    # Select latest timestamp
    # --------------------------------------------------------

    if "timestamp" in traffic.columns:

        traffic["timestamp"] = (
            traffic["timestamp"]
            .astype(str)
        )

        latest_timestamp = (
            traffic["timestamp"]
            .max()
        )

        traffic = traffic[
            traffic["timestamp"]
            ==
            latest_timestamp
        ].copy()

    else:

        latest_timestamp = "UNKNOWN"

    print(
        "Live traffic timestamp:",
        latest_timestamp
    )

    print(
        "Traffic records:",
        len(traffic)
    )

    return traffic


# ============================================================
# RESET GRAPH TRAFFIC
# ============================================================

def reset_graph_traffic():

    live_edges = 0

    for u, v, key, data in graph.edges(
        keys=True,
        data=True
    ):

        # ----------------------------------------------------
        # Road length
        # ----------------------------------------------------

        try:

            length = float(
                data.get(
                    "length",
                    0
                )
                or 0
            )

        except Exception:

            length = 0.0

        # ----------------------------------------------------
        # Road speed
        # ----------------------------------------------------

        try:

            speed = float(
                data.get(
                    "speed_kph",
                    0
                )
                or 0
            )

        except Exception:

            speed = 0.0

        # ----------------------------------------------------
        # Calculate normal travel time
        # ----------------------------------------------------

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

            base_time = 1.0

        # ----------------------------------------------------
        # Store base values
        # ----------------------------------------------------

        data[
            "base_weight_sec"
        ] = base_time

        data[
            "traffic_weight_sec"
        ] = base_time

        # ----------------------------------------------------
        # Live traffic fields
        # ----------------------------------------------------

        data[
            "traffic_observed"
        ] = False

        data[
            "live_current_speed_kmh"
        ] = None

        data[
            "live_free_flow_speed_kmh"
        ] = None

        data[
            "live_delay_percent"
        ] = None

        data[
            "live_confidence"
        ] = None

        data[
            "live_road_closure"
        ] = False

    return live_edges


# ============================================================
# CONVERT VALUE TO INTEGER
# ============================================================

def to_int(value):

    try:

        return int(
            float(value)
        )

    except Exception:

        return None


# ============================================================
# APPLY LIVE TRAFFIC
# ============================================================

def apply_live_traffic():

    traffic = load_latest_traffic()

    reset_graph_traffic()

    live_edges = 0

    closed_edges = 0

    if traffic.empty:

        print()
        print(
            "No live traffic applied."
        )

        return

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

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

    missing_columns = []

    for column in required_columns:

        if column not in traffic.columns:

            missing_columns.append(
                column
            )

    if missing_columns:

        print()
        print(
            "WARNING: Required traffic columns missing:"
        )

        for column in missing_columns:

            print(
                " -",
                column
            )

        return

    # --------------------------------------------------------
    # Apply traffic to EXACT graph edges
    # --------------------------------------------------------

    for _, row in traffic.iterrows():

        u = to_int(
            row["osm_u"]
        )

        v = to_int(
            row["osm_v"]
        )

        key = to_int(
            row["osm_key"]
        )

        if (
            u is None
            or
            v is None
            or
            key is None
        ):

            continue

        # ----------------------------------------------------
        # Check exact edge
        # ----------------------------------------------------

        if not graph.has_edge(
            u,
            v,
            key
        ):

            continue

        try:

            edge = graph[
                u
            ][
                v
            ][
                key
            ]

        except Exception:

            continue

        # ----------------------------------------------------
        # Read traffic values
        # ----------------------------------------------------

        try:

            current_speed = float(
                row[
                    "current_speed_kmh"
                ]
            )

        except Exception:

            current_speed = None

        try:

            free_flow_speed = float(
                row[
                    "free_flow_speed_kmh"
                ]
            )

        except Exception:

            free_flow_speed = None

        try:

            delay_percent = float(
                row[
                    "delay_percent"
                ]
            )

        except Exception:

            delay_percent = 0.0

        try:

            confidence = float(
                row[
                    "confidence"
                ]
            )

        except Exception:

            confidence = 0.0

        # ----------------------------------------------------
        # Road closure
        # ----------------------------------------------------

        closure_value = str(
            row[
                "road_closure"
            ]
        ).strip().lower()

        road_closed = (
            closure_value
            in
            [
                "true",
                "1",
                "yes"
            ]
        )

        # ----------------------------------------------------
        # Base travel time
        # ----------------------------------------------------

        try:

            base_time = float(
                edge.get(
                    "base_weight_sec",
                    1.0
                )
            )

        except Exception:

            base_time = 1.0

        # ----------------------------------------------------
        # CLOSED ROAD
        # ----------------------------------------------------

        if road_closed:

            edge[
                "traffic_weight_sec"
            ] = float("inf")

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
            ] = True

            live_edges += 1

            closed_edges += 1

            continue

        # ----------------------------------------------------
        # SPEED RATIO
        # ----------------------------------------------------

        if (
            current_speed is not None
            and
            free_flow_speed is not None
            and
            current_speed > 0
            and
            free_flow_speed > 0
        ):

            speed_ratio = (
                current_speed
                /
                free_flow_speed
            )

        else:

            speed_ratio = 1.0

        # ----------------------------------------------------
        # Prevent unrealistic values
        # ----------------------------------------------------

        speed_ratio = max(
            0.05,
            min(
                speed_ratio,
                1.0
            )
        )

        # ----------------------------------------------------
        # Traffic travel time
        # ----------------------------------------------------

        traffic_time = (
            base_time
            /
            speed_ratio
        )

        # Maximum 20x normal travel time
        traffic_time = max(
            base_time,
            min(
                traffic_time,
                base_time * 20
            )
        )

        # ----------------------------------------------------
        # Store live traffic
        # ----------------------------------------------------

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

        live_edges += 1

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print(
        "Traffic-adjusted graph edges:",
        live_edges
    )

    print(
        "Closed edges:",
        closed_edges
    )


# ============================================================
# GEOCODE USING OPENSTREETMAP
# ============================================================

def geocode_place(place):

    print()
    print(
        "Searching location:",
        place
    )

    params = {
        "q": (
            place
            +
            ", Bengaluru, Karnataka, India"
        ),
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": USER_AGENT
    }

    try:

        response = requests.get(
            OSM_GEOCODE_URL,
            params=params,
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:

            print(
                "OpenStreetMap HTTP:",
                response.status_code
            )

            return None

        results = response.json()

        if not results:

            print(
                "Location not found."
            )

            return None

        result = results[0]

        latitude = float(
            result["lat"]
        )

        longitude = float(
            result["lon"]
        )

        display_name = result.get(
            "display_name",
            place
        )

        print(
            "Found using OpenStreetMap:",
            display_name
        )

        return (
            latitude,
            longitude
        )

    except Exception as error:

        print(
            "Geocoding error:",
            error
        )

        return None


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371000.0

    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(
            dlat / 2
        ) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(
            dlon / 2
        ) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return (
        earth_radius
        *
        c
    )


# ============================================================
# GET NODE COORDINATES
# ============================================================

def get_node_coordinates(node):

    data = graph.nodes[
        node
    ]

    # OSMnx graph:
    # x = longitude
    # y = latitude

    longitude = data.get(
        "x"
    )

    latitude = data.get(
        "y"
    )

    # Fallback
    if (
        latitude is None
        or
        longitude is None
    ):

        latitude = data.get(
            "lat"
        )

        longitude = data.get(
            "lon"
        )

    if (
        latitude is None
        or
        longitude is None
    ):

        return None

    try:

        return (
            float(latitude),
            float(longitude)
        )

    except Exception:

        return None


# ============================================================
# FIND NEAREST NODE
# ============================================================

def find_nearest_node(
    latitude,
    longitude
):

    nearest_node = None

    nearest_distance = float(
        "inf"
    )

    for node in graph.nodes:

        coordinates = get_node_coordinates(
            node
        )

        if coordinates is None:

            continue

        node_latitude, node_longitude = (
            coordinates
        )

        distance = haversine_distance(
            latitude,
            longitude,
            node_latitude,
            node_longitude
        )

        if distance < nearest_distance:

            nearest_distance = distance

            nearest_node = node

    return (
        nearest_node,
        nearest_distance
    )


# ============================================================
# GET BEST EDGE
# ============================================================

def get_best_edge(
    u,
    v
):

    if not graph.has_edge(
        u,
        v
    ):

        return (
            None,
            None
        )

    edges = graph[
        u
    ][
        v
    ]

    best_key = None

    best_edge = None

    best_weight = float(
        "inf"
    )

    for key, data in edges.items():

        try:

            weight = float(
                data.get(
                    "traffic_weight_sec",
                    data.get(
                        "base_weight_sec",
                        float("inf")
                    )
                )
            )

        except Exception:

            continue

        if weight < best_weight:

            best_weight = weight

            best_key = key

            best_edge = data

    return (
        best_key,
        best_edge
    )


# ============================================================
# GET ROAD NAME
# ============================================================

def add_road_name(
    road_names,
    name
):

    if name is None:

        return

    if isinstance(
        name,
        list
    ):

        names = name

    else:

        names = [
            name
        ]

    for item in names:

        if item is None:

            continue

        text = str(
            item
        ).strip()

        if (
            text
            and
            text not in road_names
        ):

            road_names.append(
                text
            )


# ============================================================
# CALCULATE ROUTE
# ============================================================

def calculate_route(
    source_node,
    destination_node
):

    print_section(
        "CALCULATING TRAFFIC-AWARE ROUTE"
    )

    print(
        "Source graph node:",
        source_node
    )

    print(
        "Destination graph node:",
        destination_node
    )

    # --------------------------------------------------------
    # Shortest path using traffic weight
    # --------------------------------------------------------

    try:

        route_nodes = nx.shortest_path(
            graph,
            source=source_node,
            target=destination_node,
            weight="traffic_weight_sec"
        )

    except nx.NetworkXNoPath:

        print()
        print(
            "ERROR: No route found."
        )

        return None

    except Exception as error:

        print()
        print(
            "ERROR calculating route:"
        )

        print(error)

        return None

    # --------------------------------------------------------
    # Route metrics
    # --------------------------------------------------------

    distance_m = 0.0

    base_time_sec = 0.0

    current_time_sec = 0.0

    route_edges = []

    # --------------------------------------------------------
    # Process every route edge
    # --------------------------------------------------------

    for index in range(
        len(route_nodes) - 1
    ):

        u = route_nodes[
            index
        ]

        v = route_nodes[
            index + 1
        ]

        key, edge = get_best_edge(
            u,
            v
        )

        if edge is None:

            continue

        try:

            length = float(
                edge.get(
                    "length",
                    0
                )
                or 0
            )

        except Exception:

            length = 0.0

        try:

            base_weight = float(
                edge.get(
                    "base_weight_sec",
                    1.0
                )
            )

        except Exception:

            base_weight = 1.0

        try:

            traffic_weight = float(
                edge.get(
                    "traffic_weight_sec",
                    base_weight
                )
            )

        except Exception:

            traffic_weight = base_weight

        # ----------------------------------------------------
        # Closed edges should not normally appear in route
        # ----------------------------------------------------

        if math.isinf(
            traffic_weight
        ):

            continue

        distance_m += length

        base_time_sec += base_weight

        current_time_sec += traffic_weight

        route_edges.append(
            (
                u,
                v,
                key,
                edge
            )
        )

    # --------------------------------------------------------
    # Distance
    # --------------------------------------------------------

    distance_km = (
        distance_m
        /
        1000.0
    )

    # --------------------------------------------------------
    # Travel time
    # --------------------------------------------------------

    base_time_min = (
        base_time_sec
        /
        60.0
    )

    current_time_min = (
        current_time_sec
        /
        60.0
    )

    # --------------------------------------------------------
    # Delay
    # --------------------------------------------------------

    delay_min = max(
        0.0,
        current_time_min
        -
        base_time_min
    )

    if base_time_min > 0:

        delay_percent = (
            delay_min
            /
            base_time_min
        ) * 100.0

    else:

        delay_percent = 0.0

    # --------------------------------------------------------
    # Speeds
    # --------------------------------------------------------

    if base_time_min > 0:

        base_speed = (
            distance_km
            /
            (
                base_time_min
                /
                60.0
            )
        )

    else:

        base_speed = 0.0

    if current_time_min > 0:

        current_speed = (
            distance_km
            /
            (
                current_time_min
                /
                60.0
            )
        )

    else:

        current_speed = 0.0

    # --------------------------------------------------------
    # Traffic status
    #
    # Based on actual route delay
    # --------------------------------------------------------

    if delay_percent <= 5:

        traffic_status = "FREE FLOW"

    elif delay_percent <= 20:

        traffic_status = "MODERATE"

    elif delay_percent <= 50:

        traffic_status = "HEAVY"

    else:

        traffic_status = "CRITICAL"

    # --------------------------------------------------------
    # Roads and live traffic
    # --------------------------------------------------------

    road_names = []

    traffic_points = []

    for u, v, key, edge in route_edges:

        # ----------------------------------------------------
        # Road name
        # ----------------------------------------------------

        add_road_name(
            road_names,
            edge.get(
                "name"
            )
        )

        # ----------------------------------------------------
        # Live traffic
        # ----------------------------------------------------

        if edge.get(
            "traffic_observed",
            False
        ):

            traffic_points.append({

                "osm_u":
                    u,

                "osm_v":
                    v,

                "osm_key":
                    key,

                "road_name":
                    edge.get(
                        "name"
                    ),

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
                        "live_road_closure",
                        False
                    )
            })

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

            continue

    if confidence_values:

        confidence = (
            sum(
                confidence_values
            )
            /
            len(
                confidence_values
            )
        )

    else:

        confidence = 0.0

    # ========================================================
    # RESULT
    # ========================================================

    print_section(
        "TRAFFIC-AWARE ROUTE RESULT"
    )

    print(
        f"Distance: {distance_km:.2f} km"
    )

    print(
        f"Base travel time: {base_time_min:.2f} min"
    )

    print(
        f"Current travel time: {current_time_min:.2f} min"
    )

    print(
        f"Delay: {delay_min:.2f} min"
    )

    print(
        f"Delay percentage: {delay_percent:.2f} %"
    )

    print(
        f"Base speed: {base_speed:.2f} km/h"
    )

    print(
        f"Current speed: {current_speed:.2f} km/h"
    )

    print(
        "Traffic:",
        traffic_status
    )

    print(
        f"Confidence: {confidence:.2f}"
    )

    # --------------------------------------------------------
    # Roads
    # --------------------------------------------------------

    print()
    print("Roads:")

    if road_names:

        for road in road_names:

            print(
                " -",
                road
            )

    else:

        print(
            " - Road names unavailable"
        )

    # --------------------------------------------------------
    # Live traffic observations
    # --------------------------------------------------------

    print()
    print(
        "Live traffic observations used:",
        len(traffic_points)
    )

    if traffic_points:

        print()
        print(
            "Live traffic on route:"
        )

        for point in traffic_points:

            road_name = point[
                "road_name"
            ]

            current_speed_value = point[
                "current_speed_kmh"
            ]

            delay_value = point[
                "delay_percent"
            ]

            print(
                " -",
                road_name,
                "| speed:",
                current_speed_value,
                "km/h",
                "| delay:",
                delay_value,
                "%"
            )

    else:

        print()
        print(
            "No live traffic observations "
            "were present on the selected route."
        )

    print_section(
        "ROUTE CALCULATION COMPLETE"
    )

    return {
        "route_nodes":
            route_nodes,

        "distance_km":
            distance_km,

        "base_time_min":
            base_time_min,

        "current_time_min":
            current_time_min,

        "delay_min":
            delay_min,

        "delay_percent":
            delay_percent,

        "base_speed_kmh":
            base_speed,

        "current_speed_kmh":
            current_speed,

        "traffic_status":
            traffic_status,

        "confidence":
            confidence,

        "road_names":
            road_names,

        "traffic_points":
            traffic_points
    }


# ============================================================
# GET LOCATION FROM USER
# ============================================================

def get_location(
    title
):

    print_section(
        title
    )

    print(
        "1 = Enter place name"
    )

    print(
        "2 = Enter latitude/longitude"
    )

    while True:

        choice = input(
            "Choose 1 or 2: "
        ).strip()

        # ----------------------------------------------------
        # Place name
        # ----------------------------------------------------

        if choice == "1":

            place = input(
                "Enter place name: "
            ).strip()

            if not place:

                print(
                    "Please enter a place name."
                )

                continue

            coordinates = geocode_place(
                place
            )

            if coordinates is None:

                print(
                    "Could not find this location."
                )

                continue

            return coordinates

        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        if choice == "2":

            try:

                latitude = float(
                    input(
                        "Enter latitude: "
                    )
                )

                longitude = float(
                    input(
                        "Enter longitude: "
                    )
                )

                return (
                    latitude,
                    longitude
                )

            except ValueError:

                print(
                    "Invalid coordinates."
                )

                continue

        print(
            "Please choose 1 or 2."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print_section(
        "BENGALURU REAL-TIME TRAFFIC ROUTE ENGINE"
    )

    print()
    print(
        "You can route from ANY location to ANY location"
    )

    print(
        "inside the coverage of the loaded Bengaluru road graph."
    )

    # --------------------------------------------------------
    # Load graph
    # --------------------------------------------------------

    if not load_graph():

        return

    # --------------------------------------------------------
    # Apply live traffic
    # --------------------------------------------------------

    apply_live_traffic()

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source_latitude, source_longitude = (
        get_location(
            "SOURCE LOCATION"
        )
    )

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    destination_latitude, destination_longitude = (
        get_location(
            "DESTINATION LOCATION"
        )
    )

    # --------------------------------------------------------
    # Find nearest graph node
    # --------------------------------------------------------

    source_node, source_distance = (
        find_nearest_node(
            source_latitude,
            source_longitude
        )
    )

    destination_node, destination_distance = (
        find_nearest_node(
            destination_latitude,
            destination_longitude
        )
    )

    if source_node is None:

        print()
        print(
            "ERROR: Source graph node not found."
        )

        return

    if destination_node is None:

        print()
        print(
            "ERROR: Destination graph node not found."
        )

        return

    # --------------------------------------------------------
    # Print location information
    # --------------------------------------------------------

    print()
    print(
        "Source coordinates:",
        source_latitude,
        source_longitude
    )

    print(
        "Destination coordinates:",
        destination_latitude,
        destination_longitude
    )

    print(
        "Source graph node:",
        source_node
    )

    print(
        "Destination graph node:",
        destination_node
    )

    print(
        f"Source → graph distance: "
        f"{source_distance:.2f} m"
    )

    print(
        f"Destination → graph distance: "
        f"{destination_distance:.2f} m"
    )

    # --------------------------------------------------------
    # Calculate route
    # --------------------------------------------------------

    calculate_route(
        source_node,
        destination_node
    )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    main()