import os
import math
import pickle
import requests
import pandas as pd
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"D:\major project\latest_graph_traffic.csv"

TOMTOM_GEOCODE_URL = (
    "https://api.tomtom.com/"
    "search/2/geocode/"
)

API_KEY = os.environ.get("TOMTOM_API_KEY")


# ============================================================
# LOAD GRAPH
# ============================================================

print()
print("=" * 70)
print("LOADING BENGALURU ROAD GRAPH")
print("=" * 70)

if not os.path.exists(GRAPH_FILE):

    print("ERROR: Graph file not found:")
    print(GRAPH_FILE)
    raise SystemExit(1)


with open(GRAPH_FILE, "rb") as f:

    graph = pickle.load(f)


print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# CHECK API KEY
# ============================================================

if not API_KEY:

    print()
    print("=" * 70)
    print("ERROR: TOMTOM_API_KEY is not set.")
    print("=" * 70)
    print()
    print('Run this in PowerShell:')
    print()
    print('$env:TOMTOM_API_KEY="YOUR_TOMTOM_KEY"')
    print()

    raise SystemExit(1)


# ============================================================
# LOAD LIVE TRAFFIC
# ============================================================

def load_latest_traffic():

    print()
    print("=" * 70)
    print("LOADING LIVE TRAFFIC")
    print("=" * 70)

    if not os.path.exists(TRAFFIC_FILE):

        print("WARNING: Live traffic file not found:")
        print(TRAFFIC_FILE)

        return pd.DataFrame()


    traffic = pd.read_csv(
        TRAFFIC_FILE
    )


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

        print("WARNING: No successful traffic observations.")

        return pd.DataFrame()


    # --------------------------------------------------------
    # Latest timestamp
    # --------------------------------------------------------

    if "timestamp" in traffic.columns:

        latest_timestamp = (
            traffic["timestamp"]
            .astype(str)
            .max()
        )

        traffic = traffic[
            traffic["timestamp"]
            .astype(str)
            == latest_timestamp
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
# BUILD NODE TRAFFIC LOOKUP
# ============================================================

def build_node_traffic_lookup(
    traffic
):

    lookup = {}

    if traffic.empty:

        return lookup


    if "nearest_node" not in traffic.columns:

        print(
            "WARNING: nearest_node column missing "
            "from traffic data."
        )

        return lookup


    # --------------------------------------------------------
    # Group observations by nearest traffic node
    # --------------------------------------------------------

    for node, group in traffic.groupby(
        "nearest_node"
    ):

        try:

            node_id = int(
                float(node)
            )

        except Exception:

            continue


        # ----------------------------------------------------
        # Calculate traffic speed ratio
        # ----------------------------------------------------

        ratios = []


        if (
            "current_speed_kmh" in group.columns
            and
            "free_flow_speed_kmh" in group.columns
        ):

            for _, row in group.iterrows():

                current = row[
                    "current_speed_kmh"
                ]

                free_flow = row[
                    "free_flow_speed_kmh"
                ]

                if (
                    pd.notna(current)
                    and
                    pd.notna(free_flow)
                ):

                    try:

                        current = float(current)
                        free_flow = float(free_flow)

                        if (
                            current > 0
                            and
                            free_flow > 0
                        ):

                            ratio = (
                                current
                                /
                                free_flow
                            )

                            ratios.append(
                                ratio
                            )

                    except Exception:

                        pass


        # ----------------------------------------------------
        # Average speed ratio
        # ----------------------------------------------------

        if ratios:

            speed_ratio = (
                sum(ratios)
                /
                len(ratios)
            )

        else:

            speed_ratio = 1.0


        # ----------------------------------------------------
        # Limit unrealistic values
        # ----------------------------------------------------

        speed_ratio = max(
            0.05,
            min(
                speed_ratio,
                1.0
            )
        )


        # ----------------------------------------------------
        # Closure
        # ----------------------------------------------------

        road_closed = False


        if "road_closure" in group.columns:

            for value in group[
                "road_closure"
            ]:

                text = str(
                    value
                ).lower()

                if text in [
                    "true",
                    "1",
                    "yes"
                ]:

                    road_closed = True

                    break


        # ----------------------------------------------------
        # Store traffic information
        # ----------------------------------------------------

        lookup[node_id] = {

            "speed_ratio":
                speed_ratio,

            "road_closed":
                road_closed,

            "records":
                len(group),

            "current_speed_kmh":
                group[
                    "current_speed_kmh"
                ].mean()
                if "current_speed_kmh"
                in group.columns
                else None,

            "free_flow_speed_kmh":
                group[
                    "free_flow_speed_kmh"
                ].mean()
                if "free_flow_speed_kmh"
                in group.columns
                else None,

            "delay_percent":
                group[
                    "delay_percent"
                ].mean()
                if "delay_percent"
                in group.columns
                else None,

            "confidence":
                group[
                    "confidence"
                ].mean()
                if "confidence"
                in group.columns
                else None
        }


    return lookup


# ============================================================
# APPLY LIVE TRAFFIC TO GRAPH
# ============================================================

def apply_live_traffic():

    traffic = load_latest_traffic()

    traffic_lookup = build_node_traffic_lookup(
        traffic
    )


    live_edges = 0
    closed_edges = 0


    # --------------------------------------------------------
    # Reset all graph edges
    # --------------------------------------------------------

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


        # ----------------------------------------------------
        # Base travel time
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

            base_time = float(
                data.get(
                    "travel_time",
                    1.0
                )
            )


        data[
            "base_weight_sec"
        ] = base_time


        # ----------------------------------------------------
        # Default = normal traffic
        # ----------------------------------------------------

        data[
            "traffic_weight_sec"
        ] = base_time


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


    # --------------------------------------------------------
    # Apply traffic around observed nodes
    # --------------------------------------------------------

    for traffic_node, traffic_data in (
        traffic_lookup.items()
    ):

        if traffic_node not in graph:

            continue


        speed_ratio = traffic_data[
            "speed_ratio"
        ]

        road_closed = traffic_data[
            "road_closed"
        ]


        # ----------------------------------------------------
        # Edges directly connected to traffic observation
        # ----------------------------------------------------

        connected_edges = []


        for neighbor in graph.successors(
            traffic_node
        ):

            if graph.has_edge(
                traffic_node,
                neighbor
            ):

                for key in graph[
                    traffic_node
                ][neighbor]:

                    connected_edges.append(
                        (
                            traffic_node,
                            neighbor,
                            key
                        )
                    )


        for neighbor in graph.predecessors(
            traffic_node
        ):

            if graph.has_edge(
                neighbor,
                traffic_node
            ):

                for key in graph[
                    neighbor
                ][traffic_node]:

                    connected_edges.append(
                        (
                            neighbor,
                            traffic_node,
                            key
                        )
                    )


        # ----------------------------------------------------
        # Apply traffic condition
        # ----------------------------------------------------

        for u, v, key in connected_edges:

            try:

                data = graph[
                    u
                ][
                    v
                ][
                    key
                ]

            except Exception:

                continue


            base_time = float(
                data.get(
                    "base_weight_sec",
                    1.0
                )
            )


            # ------------------------------------------------
            # Road closure
            # ------------------------------------------------

            if road_closed:

                data[
                    "traffic_weight_sec"
                ] = float("inf")

                data[
                    "traffic_observed"
                ] = True

                data[
                    "live_road_closure"
                ] = True

                closed_edges += 1
                live_edges += 1

                continue


            # ------------------------------------------------
            # Traffic-adjusted travel time
            #
            # If speed is 50% of free-flow:
            #
            # normal time = 100 sec
            #
            # traffic time = 200 sec
            # ------------------------------------------------

            if speed_ratio > 0:

                traffic_time = (
                    base_time
                    /
                    speed_ratio
                )

            else:

                traffic_time = base_time


            # ------------------------------------------------
            # Prevent extreme values
            # ------------------------------------------------

            traffic_time = max(
                base_time,
                min(
                    traffic_time,
                    base_time * 20
                )
            )


            data[
                "traffic_weight_sec"
            ] = traffic_time


            data[
                "traffic_observed"
            ] = True


            data[
                "live_current_speed_kmh"
            ] = traffic_data[
                "current_speed_kmh"
            ]


            data[
                "live_free_flow_speed_kmh"
            ] = traffic_data[
                "free_flow_speed_kmh"
            ]


            data[
                "live_delay_percent"
            ] = traffic_data[
                "delay_percent"
            ]


            data[
                "live_confidence"
            ] = traffic_data[
                "confidence"
            ]


            data[
                "live_road_closure"
            ] = False


            live_edges += 1


    print()
    print(
        "Traffic observation nodes:",
        len(traffic_lookup)
    )

    print(
        "Traffic-adjusted graph edges:",
        live_edges
    )

    print(
        "Closed edges:",
        closed_edges
    )


    return (
        live_edges,
        closed_edges
    )


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371000

    lat1 = math.radians(
        float(lat1)
    )

    lat2 = math.radians(
        float(lat2)
    )

    dlat = math.radians(
        float(lat2)
        -
        float(lat1)
    )

    dlon = math.radians(
        float(lon2)
        -
        float(lon1)
    )


    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(dlon / 2) ** 2
    )


    c = (
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


    return R * c


# ============================================================
# NEAREST GRAPH NODE
# ============================================================

def nearest_node(
    latitude,
    longitude
):

    best_node = None

    best_distance = float(
        "inf"
    )


    for node, data in graph.nodes(
        data=True
    ):

        lat = data.get(
            "y"
        )

        lon = data.get(
            "x"
        )


        if (
            lat is None
            or
            lon is None
        ):

            continue


        distance = haversine_distance(
            latitude,
            longitude,
            lat,
            lon
        )


        if distance < best_distance:

            best_distance = distance

            best_node = node


    if best_node is None:

        raise ValueError(
            "Could not find nearest graph node."
        )


    return (
        best_node,
        best_distance
    )


# ============================================================
# GEOCODE PLACE USING TOMTOM
# ============================================================

# ============================================================
# GEOCODE PLACE
# ============================================================

def geocode_place(place):

    print()
    print("Searching location:", place)

    # --------------------------------------------------------
    # 1. Try TomTom
    # --------------------------------------------------------

    try:

        url = (
            TOMTOM_GEOCODE_URL
            +
            requests.utils.quote(place)
            +
            ".json"
        )

        params = {
            "key": API_KEY,
            "limit": 1,
            "countrySet": "IN"
        }

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code == 200:

            data = response.json()

            results = data.get(
                "results",
                []
            )

            if results:

                position = results[0].get(
                    "position",
                    {}
                )

                lat = position.get("lat")
                lon = position.get("lon")

                if lat is not None and lon is not None:

                    address = (
                        results[0]
                        .get("address", {})
                        .get(
                            "freeformAddress",
                            place
                        )
                    )

                    print(
                        "Found using TomTom:",
                        address
                    )

                    return (
                        float(lat),
                        float(lon)
                    )

        print(
            "TomTom geocoding unavailable."
        )

        print(
            "HTTP:",
            response.status_code
        )

    except Exception as e:

        print(
            "TomTom geocoding error:",
            e
        )


    # --------------------------------------------------------
    # 2. OpenStreetMap fallback
    # --------------------------------------------------------

    print()
    print(
        "Trying OpenStreetMap geocoding..."
    )

    try:

        osm_url = (
            "https://nominatim.openstreetmap.org/search"
        )

        params = {

            "q":
                place,

            "format":
                "json",

            "limit":
                1,

            "countrycodes":
                "in"
        }

        headers = {

            "User-Agent":
                "BengaluruTrafficRouteEngine/1.0"
        }

        response = requests.get(
            osm_url,
            params=params,
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:

            print(
                "OpenStreetMap geocoding failed."
            )

            print(
                "HTTP:",
                response.status_code
            )

            return None


        results = response.json()


        if not results:

            print(
                "Location not found:",
                place
            )

            return None


        lat = results[0].get(
            "lat"
        )

        lon = results[0].get(
            "lon"
        )


        if (
            lat is None
            or
            lon is None
        ):

            print(
                "Coordinates not available."
            )

            return None


        print(
            "Found using OpenStreetMap:",
            results[0].get(
                "display_name",
                place
            )
        )


        return (
            float(lat),
            float(lon)
        )


    except Exception as e:

        print(
            "OpenStreetMap geocoding error:",
            e
        )

        return None

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


    options = graph[
        u
    ][
        v
    ]


    best_key = None

    best_edge = None

    best_weight = float(
        "inf"
    )


    for key, data in options.items():

        weight = float(
            data.get(
                "traffic_weight_sec",
                data.get(
                    "base_weight_sec",
                    float("inf")
                )
            )
        )


        if weight < best_weight:

            best_weight = weight

            best_key = key

            best_edge = data


    return (
        best_key,
        best_edge
    )


# ============================================================
# CALCULATE ROUTE
# ============================================================

def calculate_traffic_route(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon
):

    # --------------------------------------------------------
    # Apply current traffic
    # --------------------------------------------------------

    live_edges, closed_edges = (
        apply_live_traffic()
    )


    # --------------------------------------------------------
    # Find nearest graph nodes
    # --------------------------------------------------------

    source_node, source_distance = (
        nearest_node(
            source_lat,
            source_lon
        )
    )


    destination_node, destination_distance = (
        nearest_node(
            destination_lat,
            destination_lon
        )
    )


    print()
    print("=" * 70)
    print("CALCULATING TRAFFIC-AWARE ROUTE")
    print("=" * 70)


    print(
        "Source coordinates:",
        source_lat,
        source_lon
    )


    print(
        "Destination coordinates:",
        destination_lat,
        destination_lon
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
        "Source → graph distance:",
        round(
            source_distance,
            2
        ),
        "m"
    )


    print(
        "Destination → graph distance:",
        round(
            destination_distance,
            2
        ),
        "m"
    )


    print(
        "Live traffic edges:",
        live_edges
    )


    print(
        "Closed edges:",
        closed_edges
    )


    # --------------------------------------------------------
    # Calculate shortest path
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


    # --------------------------------------------------------
    # Route metrics
    # --------------------------------------------------------

    distance_m = 0.0

    base_time_sec = 0.0

    current_time_sec = 0.0

    route_edges = []


    for i in range(
        len(route_nodes) - 1
    ):

        u = route_nodes[i]

        v = route_nodes[
            i + 1
        ]


        key, edge = get_best_edge(
            u,
            v
        )


        if edge is None:

            continue


        length = float(
            edge.get(
                "length",
                0
            )
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
                base_weight
            )
        )


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
    # Metrics
    # --------------------------------------------------------

    distance_km = (
        distance_m
        /
        1000
    )


    base_time_min = (
        base_time_sec
        /
        60
    )


    current_time_min = (
        current_time_sec
        /
        60
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
    # Traffic percentage
    # --------------------------------------------------------

    if base_time_min > 0:

        delay_percent = (
            delay_min
            /
            base_time_min
        ) * 100

    else:

        delay_percent = 0


    # --------------------------------------------------------
    # Road names
    # --------------------------------------------------------

    # --------------------------------------------------------

    road_names = []


    for _, _, _, edge in route_edges:

        name = edge.get(
            "name"
        )


        if isinstance(
            name,
            list
        ):

            names = name

        else:

            names = [
                name
            ]


        for name_item in names:

            if name_item is None:

                continue


            name_text = str(
                name_item
            ).strip()


            if (
                name_text
                and
                name_text
                not in road_names
            ):

                road_names.append(
                    name_text
                )


    # --------------------------------------------------------
    # Live observations used
    # --------------------------------------------------------

    traffic_points = []


    for u, v, key, edge in route_edges:

        if not edge.get(
            "traffic_observed",
            False
        ):

            continue


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
    # Average live confidence
    # --------------------------------------------------------

    confidence_values = []


    for point in traffic_points:

        value = point.get(
            "confidence"
        )


        if value is None:

            continue
            confidence_values.append(
                float(value)
            )

        except Exception:

            pass


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

    # --------------------------------------------------------
    # Traffic status
    # --------------------------------------------------------

    live_delay_values = []

    for point in traffic_points:

        value = point.get("delay_percent")

        if value is None:
            continue

        try:
            live_delay_values.append(float(value))
        except Exception:
            continue

    if live_delay_values:

        max_live_delay = max(live_delay_values)

        if max_live_delay <= 5:
            traffic_status = "FREE FLOW"

        elif max_live_delay <= 20:
            traffic_status = "MODERATE"

        elif max_live_delay <= 50:
            traffic_status = "HEAVY"

        else:
            traffic_status = "CRITICAL"

    else:

        if delay_percent <= 5:
            traffic_status = "FREE FLOW"

        elif delay_percent <= 20:
            traffic_status = "MODERATE"

        elif delay_percent <= 50:
            traffic_status = "HEAVY"

        else:
            traffic_status = "CRITICAL"


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

        "delay_min":
            round(
                delay_min,
                2
            ),

        "delay_percent":
            round(
                delay_percent,
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
# PRINT RESULT
# ============================================================

def print_result(
    result
):

    if result is None:

        return


    print()
    print("=" * 70)
    print("TRAFFIC-AWARE ROUTE RESULT")
    print("=" * 70)


    print(
        "Distance:",
        result[
            "distance_km"
        ],
        "km"
    )


    print(
        "Base travel time:",
        result[
            "base_travel_time_min"
        ],
        "min"
    )


    print(
        "Current travel time:",
        result[
            "current_travel_time_min"
        ],
        "min"
    )


    print(
        "Delay:",
        result[
            "delay_min"
        ],
        "min"
    )


    print(
        "Delay percentage:",
        result[
            "delay_percent"
        ],
        "%"
    )


    print(
        "Base speed:",
        result[
            "base_speed_kmh"
        ],
        "km/h"
    )


    print(
        "Current speed:",
        result[
            "current_speed_kmh"
        ],
        "km/h"
    )


    print(
        "Traffic:",
        result[
            "traffic_status"
        ]
    )


    print(
        "Confidence:",
        result[
            "confidence"
        ]
    )


    print()
    print("Roads:")


    for road in result[
        "road_names"
    ]:

        print(
            " -",
            road
        )


    print()
    print(
        "Live traffic observations used:",
        len(
            result[
                "traffic_points"
            ]
        )
    )


    if result[
        "traffic_points"
    ]:

        print()
        print(
            "Live traffic on route:"
        )


        for point in result[
            "traffic_points"
        ]:

            print(
                " -",
                point[
                    "road_name"
                ],
                "| speed:",
                point[
                    "current_speed_kmh"
                ],
                "km/h",
                "| delay:",
                point[
                    "delay_percent"
                ],
                "%"
            )


    print()
    print("=" * 70)
    print("ROUTE CALCULATION COMPLETE")
    print("=" * 70)


# ============================================================
# INPUT SOURCE
# ============================================================

def get_location(
    label
):

    print()
    print(
        "=" * 70
    )

    print(
        label
    )

    print(
        "=" * 70
    )


    print()
    print(
        "1 = Enter place name"
    )

    print(
        "2 = Enter latitude/longitude"
    )


    choice = input(
        "Choose 1 or 2: "
    ).strip()


    # --------------------------------------------------------
    # Place name
    # --------------------------------------------------------

    if choice == "1":

        place = input(
            "Enter place name: "
        ).strip()


        if not place:

            return None


        coordinates = geocode_place(
            place
        )


        if coordinates is None:

            return None


        return coordinates


    # --------------------------------------------------------
    # Coordinates
    # --------------------------------------------------------

    if choice == "2":

        try:

            latitude = float(
                input(
                    "Enter latitude: "
                ).strip()
            )


            longitude = float(
                input(
                    "Enter longitude: "
                ).strip()
            )


            return (
                latitude,
                longitude
            )


        except ValueError:

            print(
                "Invalid coordinates."
            )

            return None


    print(
        "Invalid choice."
    )


    return None


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("BENGALURU REAL-TIME TRAFFIC ROUTE ENGINE")
    print("=" * 70)

    print()
    print(
        "You can route from ANY location to ANY location"
    )

    print(
        "inside the coverage of the loaded Bengaluru road graph."
    )


    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source = get_location(
        "SOURCE LOCATION"
    )


    if source is None:

        print(
            "Could not determine source."
        )

        return


    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    destination = get_location(
        "DESTINATION LOCATION"
    )


    if destination is None:

        print(
            "Could not determine destination."
        )

        return


    source_lat, source_lon = source

    destination_lat, destination_lon = destination


    # --------------------------------------------------------
    # Calculate
    # --------------------------------------------------------

    result = calculate_traffic_route(

        source_lat,
        source_lon,

        destination_lat,
        destination_lon
    )


    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print_result(
        result
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()








