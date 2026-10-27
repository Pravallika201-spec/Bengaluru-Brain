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

TRAFFIC_FILE = r"D:\major project\bengaluru_traffic_segments.csv"

USER_AGENT = "BengaluruTrafficRoutingProject/1.0"

OSM_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"


# ============================================================
# PRINT HELPERS
# ============================================================

def print_section(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_m(lat1, lon1, lat2, lon2):

    R = 6371000

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 2 * R * math.asin(
        math.sqrt(a)
    )


# ============================================================
# LOAD GRAPH
# ============================================================

def load_graph():

    print_section(
        "LOADING BENGALURU ROAD GRAPH"
    )

    print(
        "Loading graph..."
    )

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

    return graph


# ============================================================
# PREPARE BASE WEIGHTS
# ============================================================

def prepare_base_weights(graph):

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

        data[
            "live_road_closure"
        ] = False


# ============================================================
# LOAD CITY-WIDE TRAFFIC
# ============================================================

def load_traffic():

    print_section(
        "LOADING CITY-WIDE TRAFFIC"
    )

    if not os.path.exists(
        TRAFFIC_FILE
    ):

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

    if "status" in traffic.columns:

        traffic = traffic[
            traffic[
                "status"
            ]
            .astype(str)
            .str.upper()
            == "OK"
        ].copy()

    print(
        "Successful traffic observations:",
        len(traffic)
    )

    return traffic


# ============================================================
# APPLY TRAFFIC TO GRAPH
# ============================================================

def apply_traffic(
    graph,
    traffic
):

    print_section(
        "APPLYING CITY-WIDE TRAFFIC"
    )

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


        # ----------------------------------------------------
        # Base values
        # ----------------------------------------------------

        base_time = float(
            edge.get(
                "base_weight_sec",
                0
            )
        )


        current_speed = pd.to_numeric(
            row.get(
                "current_speed_kmh"
            ),
            errors="coerce"
        )

        free_flow_speed = pd.to_numeric(
            row.get(
                "free_flow_speed_kmh"
            ),
            errors="coerce"
        )


        # ----------------------------------------------------
        # Road closure
        # ----------------------------------------------------

        closure_value = str(
            row.get(
                "road_closure",
                ""
            )
        ).strip().lower()

        road_closed = (
            closure_value
            in [
                "true",
                "1",
                "yes"
            ]
        )


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
            ] = row.get(
                "delay_percent"
            )

            edge[
                "live_confidence"
            ] = row.get(
                "confidence"
            )

            closed += 1
            applied += 1

            continue


        # ----------------------------------------------------
        # Traffic speed adjustment
        # ----------------------------------------------------

        if (
            pd.notna(current_speed)
            and
            pd.notna(free_flow_speed)
            and
            current_speed > 0
            and
            free_flow_speed > 0
        ):

            speed_ratio = (
                float(current_speed)
                /
                float(free_flow_speed)
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


        # ----------------------------------------------------
        # Store traffic information
        # ----------------------------------------------------

        edge[
            "traffic_weight_sec"
        ] = traffic_time

        edge[
            "traffic_observed"
        ] = True

        edge[
            "live_current_speed_kmh"
        ] = (
            float(current_speed)
            if pd.notna(current_speed)
            else None
        )

        edge[
            "live_free_flow_speed_kmh"
        ] = (
            float(free_flow_speed)
            if pd.notna(free_flow_speed)
            else None
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

        edge[
            "live_road_closure"
        ] = False

        applied += 1


    print(
        "Traffic edges applied:",
        applied
    )

    print(
        "Closed edges:",
        closed
    )

    print(
        "Traffic edges not found:",
        not_found
    )

    return applied, closed, not_found


# ============================================================
# GEOCODE PLACE
# ============================================================

def geocode_place(place):

    print()
    print(
        "Searching location:",
        place
    )

    params = {
        "q":
            place
            +
            ", Bengaluru, Karnataka, India",

        "format":
            "json",

        "limit":
            1
    }

    headers = {
        "User-Agent":
            USER_AGENT
    }

    try:

        response = requests.get(
            OSM_GEOCODE_URL,
            params=params,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        results = response.json()

        if not results:

            print(
                "Location not found."
            )

            return None


        result = results[0]

        lat = float(
            result["lat"]
        )

        lon = float(
            result["lon"]
        )

        print(
            "Found using OpenStreetMap:",
            result.get(
                "display_name",
                place
            )
        )

        return lat, lon


    except Exception as e:

        print(
            "Geocoding error:",
            e
        )

        return None


# ============================================================
# FIND NEAREST GRAPH NODE
# ============================================================

def nearest_node(
    graph,
    latitude,
    longitude
):

    best_node = None
    best_distance = float("inf")

    for node, data in graph.nodes(
        data=True
    ):

        lat = data.get(
            "y",
            data.get(
                "lat"
            )
        )

        lon = data.get(
            "x",
            data.get(
                "lon"
            )
        )

        if lat is None or lon is None:

            continue

        try:

            distance = haversine_m(
                latitude,
                longitude,
                float(lat),
                float(lon)
            )

        except Exception:

            continue


        if distance < best_distance:

            best_distance = distance
            best_node = node


    return best_node, best_distance


# ============================================================
# GET LOCATION
# ============================================================

def get_location(
    title,
    graph
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

                continue


            latitude, longitude = coordinates


        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        elif choice == "2":

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

            except ValueError:

                print(
                    "Invalid coordinates."
                )

                continue


        else:

            print(
                "Please choose 1 or 2."
            )

            continue


        node, distance = nearest_node(
            graph,
            latitude,
            longitude
        )


        if node is None:

            print(
                "Could not find a graph node."
            )

            continue


        print()
        print(
            "Coordinates:",
            latitude,
            longitude
        )

        print(
            "Nearest graph node:",
            node
        )

        print(
            "Distance to graph node:",
            f"{distance:.2f} m"
        )

        return (
            node,
            latitude,
            longitude,
            distance
        )


# ============================================================
# ROUTE DISTANCE
# ============================================================

def route_distance(
    graph,
    route
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

        best = float("inf")

        for _, data in options.items():

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


# ============================================================
# ROUTE TIME
# ============================================================

def route_time(
    graph,
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

        best = float("inf")

        for _, data in options.items():

            value = float(
                data.get(
                    weight_name,
                    float("inf")
                )
            )

            if value < best:

                best = value


        total += best


    return total / 60


# ============================================================
# GET ROUTE EDGES
# ============================================================

def get_route_edges(
    graph,
    route
):

    edges = []

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

        best_key = None
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


        if best_key is not None:

            edges.append(
                (
                    u,
                    v,
                    best_key,
                    options[best_key]
                )
            )


    return edges


# ============================================================
# ROAD NAMES
# ============================================================

def get_road_names(
    route_edges
):

    names = []

    for _, _, _, data in route_edges:

        name = data.get(
            "name"
        )

        if isinstance(
            name,
            list
        ):

            name = ", ".join(
                map(
                    str,
                    name
                )
            )


        if name is None:

            name = "Unnamed road"


        name = str(
            name
        ).strip()


        if not name:

            name = "Unnamed road"


        if name not in names:

            names.append(
                name
            )


    return names


# ============================================================
# TRAFFIC OBSERVATIONS ON ROUTE
# ============================================================

def get_traffic_points(
    route_edges
):

    points = []

    for u, v, key, data in route_edges:

        if not data.get(
            "traffic_observed",
            False
        ):

            continue


        points.append({

            "u":
                u,

            "v":
                v,

            "key":
                key,

            "road":
                data.get(
                    "name",
                    "Unnamed road"
                ),

            "current_speed":
                data.get(
                    "live_current_speed_kmh"
                ),

            "free_flow_speed":
                data.get(
                    "live_free_flow_speed_kmh"
                ),

            "delay":
                data.get(
                    "live_delay_percent"
                ),

            "confidence":
                data.get(
                    "live_confidence"
                ),

            "closed":
                data.get(
                    "live_road_closure",
                    False
                )
        })


    return points


# ============================================================
# MAIN
# ============================================================

def main():

    print_section(
        "BENGALURU FINAL TRAFFIC ROUTING DEMO"
    )

    print(
        "Real-time traffic-aware routing"
    )

    print(
        "City-wide traffic + congestion + road closure support"
    )


    # --------------------------------------------------------
    # Graph
    # --------------------------------------------------------

    graph = load_graph()

    prepare_base_weights(
        graph
    )


    # --------------------------------------------------------
    # Traffic
    # --------------------------------------------------------

    traffic = load_traffic()

    applied, closed, not_found = apply_traffic(
        graph,
        traffic
    )


    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source_node, source_lat, source_lon, source_distance = get_location(
        "SOURCE LOCATION",
        graph
    )


    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    destination_node, destination_lat, destination_lon, destination_distance = get_location(
        "DESTINATION LOCATION",
        graph
    )


    # --------------------------------------------------------
    # Same node check
    # --------------------------------------------------------

    if source_node == destination_node:

        print()
        print(
            "Source and destination are mapped to the same graph node."
        )

        return


    # --------------------------------------------------------
    # Base route
    # --------------------------------------------------------

    print_section(
        "CALCULATING BASE ROUTE"
    )

    try:

        base_route = nx.shortest_path(
            graph,
            source_node,
            destination_node,
            weight="base_weight_sec"
        )

    except nx.NetworkXNoPath:

        print(
            "ERROR: No base route exists."
        )

        return


    # --------------------------------------------------------
    # Traffic route
    # --------------------------------------------------------

    print_section(
        "CALCULATING TRAFFIC-AWARE ROUTE"
    )

    try:

        traffic_route = nx.shortest_path(
            graph,
            source_node,
            destination_node,
            weight="traffic_weight_sec"
        )

    except nx.NetworkXNoPath:

        print(
            "ERROR: No traffic-aware route exists."
        )

        return


    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    base_distance = route_distance(
        graph,
        base_route
    )

    traffic_distance = route_distance(
        graph,
        traffic_route
    )


    base_time = route_time(
        graph,
        base_route,
        "base_weight_sec"
    )

    traffic_time = route_time(
        graph,
        traffic_route,
        "traffic_weight_sec"
    )


    delay = (
        traffic_time
        -
        base_time
    )


    if base_time > 0:

        delay_percent = (
            delay
            /
            base_time
            *
            100
        )

    else:

        delay_percent = 0.0


    # --------------------------------------------------------
    # Route change
    # --------------------------------------------------------

    base_edges = set(
        zip(
            base_route[:-1],
            base_route[1:]
        )
    )

    traffic_edges = set(
        zip(
            traffic_route[:-1],
            traffic_route[1:]
        )
    )


    removed = (
        base_edges
        -
        traffic_edges
    )

    added = (
        traffic_edges
        -
        base_edges
    )
    route_changed = (
        base_route
        !=
        traffic_route
    )
    traffic_route_edges = get_route_edges(
        graph,
        traffic_route
    )

    traffic_points = get_traffic_points(
        traffic_route_edges
    )


    road_names = get_road_names(
        traffic_route_edges
    )


    # --------------------------------------------------------
    # Traffic status
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
    # Final result
    # --------------------------------------------------------

    print_section(
        "FINAL ROUTING RESULT"
    )


    print()
    print(
        "SOURCE"
    )

    print(
        "Coordinates:",
        source_lat,
        source_lon
    )

    print(
        "Graph node:",
        source_node
    )

    print(
        "Graph distance:",
        f"{source_distance:.2f} m"
    )


    print()
    print(
        "DESTINATION"
    )

    print(
        "Coordinates:",
        destination_lat,
        destination_lon
    )

    print(
        "Graph node:",
        destination_node
    )

    print(
        "Graph distance:",
        f"{destination_distance:.2f} m"
    )


    print()
    print(
        "BASE ROUTE"
    )

    print(
        "-" * 70
    )

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
    print(
        "TRAFFIC-AWARE ROUTE"
    )

    print(
        "-" * 70
    )

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
    print(
        "TRAFFIC IMPACT"
    )

    print(
        "-" * 70
    )

    print(
        f"Additional travel time: {delay:.2f} min"
    )

    print(
        f"Traffic delay: {delay_percent:.2f} %"
    )

    print(
        "Traffic status:",
        traffic_status
    )


    print()
    print(
        "ROUTE CHANGE"
    )

    print(
        "-" * 70
    )


    if route_changed:

        print(
            "SUCCESS: Traffic-aware route changed."
        )

        print(
            "Edges removed:",
            len(removed)
        )

        print(
            "Edges added:",
            len(added)
        )

    else:

        print(
            "Traffic-aware route is the same as the base route."
        )


    # --------------------------------------------------------
    # Roads
    # --------------------------------------------------------

    print()
    print(
        "ROADS ON TRAFFIC-AWARE ROUTE"
    )

    print(
        "-" * 70
    )


    for road in road_names:

        print(
            " -",
            road
        )


    # --------------------------------------------------------
    # Traffic observations
    # --------------------------------------------------------

    print()
    print(
        "TRAFFIC OBSERVATIONS ON FINAL ROUTE"
    )

    print(
        "-" * 70
    )


    if traffic_points:

        for point in traffic_points:

            road = point[
                "road"
            ]

            if road is None:

                road = "Unnamed road"


            print()
            print(
                "Road:",
                road
            )

            print(
                "Edge:",
                point["u"],
                "->",
                point["v"],
                "key:",
                point["key"]
            )

            print(
                "Current speed:",
                point["current_speed"],
                "km/h"
            )

            print(
                "Free-flow speed:",
                point["free_flow_speed"],
                "km/h"
            )

            print(
                "Delay:",
                point["delay"],
                "%"
            )

            print(
                "Confidence:",
                point["confidence"]
            )

            print(
                "Road closure:",
                point["closed"]
            )

    else:

        print(
            "No directly observed traffic edges "
            "were used by the final route."
        )


    # --------------------------------------------------------
    # Overall confidence
    # --------------------------------------------------------

    confidence_values = []

    for point in traffic_points:

        value = point.get(
            "confidence"
        )

        try:

            if value is not None:

                confidence_values.append(
                    float(value)
                )

        except Exception:

            pass


    if confidence_values:

        average_confidence = (
            sum(confidence_values)
            /
            len(confidence_values)
        )

    else:

        average_confidence = 0.0


    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print_section(
        "FINAL SUMMARY"
    )

    print(
        "City-wide traffic observations:",
        len(traffic)
    )

    print(
        "Traffic edges applied:",
        applied
    )

    print(
        "Closed edges:",
        closed
    )

    print(
        "Traffic edges not found:",
        not_found
    )

    print(
        "Base route:",
        f"{base_distance:.2f} km / {base_time:.2f} min"
    )

    print(
        "Traffic route:",
        f"{traffic_distance:.2f} km / {traffic_time:.2f} min"
    )

    print(
        "Additional time:",
        f"{delay:.2f} min"
    )

    print(
        "Traffic delay:",
        f"{delay_percent:.2f} %"
    )

    print(
        "Route changed:",
        "YES" if route_changed else "NO"
    )

    print(
        "Traffic observations on final route:",
        len(traffic_points)
    )

    print(
        "Average confidence:",
        f"{average_confidence:.2f}"
    )


    print_section(
        "BENGALURU FINAL TRAFFIC ROUTING DEMO COMPLETE"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()