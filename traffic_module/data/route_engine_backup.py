import pickle
import math
import networkx as nx


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"


# ============================================================
# LOAD BENGALURU GRAPH
# ============================================================

print("Loading Bengaluru road graph...")

with open(GRAPH_FILE, "rb") as file:
    graph = pickle.load(file)

print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine(lat1, lon1, lat2, lon2):

    R = 6371000

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

    return 2 * R * math.asin(
        math.sqrt(a)
    )


# ============================================================
# FIND NEAREST NODE
# ============================================================

def find_nearest_node(
    latitude,
    longitude
):

    best_node = None
    best_distance = float("inf")

    for node, data in graph.nodes(data=True):

        if "y" not in data or "x" not in data:
            continue

        node_lat = float(data["y"])
        node_lon = float(data["x"])

        distance = haversine(
            latitude,
            longitude,
            node_lat,
            node_lon
        )

        if distance < best_distance:

            best_distance = distance
            best_node = node

    return best_node, best_distance


# ============================================================
# ROUTE CALCULATION
# ============================================================

def calculate_route(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon
):

    print()
    print("=" * 60)
    print("CALCULATING BENGALURU ROUTE")
    print("=" * 60)

    # --------------------------------------------------------
    # Find nearest nodes
    # --------------------------------------------------------

    source_node, source_distance = (
        find_nearest_node(
            source_lat,
            source_lon
        )
    )

    destination_node, destination_distance = (
        find_nearest_node(
            destination_lat,
            destination_lon
        )
    )

    if source_node is None:
        raise ValueError(
            "Could not find source node."
        )

    if destination_node is None:
        raise ValueError(
            "Could not find destination node."
        )

    print(
        "Source node:",
        source_node
    )

    print(
        "Destination node:",
        destination_node
    )

    print(
        "Source snap distance:",
        round(source_distance, 2),
        "m"
    )

    print(
        "Destination snap distance:",
        round(destination_distance, 2),
        "m"
    )

    # --------------------------------------------------------
    # Calculate shortest route
    # --------------------------------------------------------

    try:

        route = nx.shortest_path(
            graph,
            source=source_node,
            target=destination_node,
            weight="travel_time"
        )

    except nx.NetworkXNoPath:

        raise ValueError(
            "No route found between the locations."
        )

    # --------------------------------------------------------
    # Calculate route statistics
    # --------------------------------------------------------

    total_distance = 0.0

    total_travel_time = 0.0

    road_names = []

    route_edges = []

    for u, v in zip(
        route[:-1],
        route[1:]
    ):

        edge_data = graph.get_edge_data(
            u,
            v
        )

        if edge_data is None:
            continue

        # MultiDiGraph may have multiple edges
        # between the same nodes.

        best_edge = min(
            edge_data.values(),
            key=lambda e:
            float(
                e.get(
                    "travel_time",
                    e.get(
                        "length",
                        0
                    )
                )
            )
        )

        length = float(
            best_edge.get(
                "length",
                0
            )
        )

        travel_time = float(
            best_edge.get(
                "travel_time",
                0
            )
        )

        total_distance += length

        total_travel_time += travel_time

        road_name = best_edge.get(
            "name"
        )

        if road_name:

            if isinstance(
                road_name,
                list
            ):

                for name in road_name:

                    if name not in road_names:
                        road_names.append(name)

            else:

                if road_name not in road_names:
                    road_names.append(
                        road_name
                    )

        route_edges.append({

            "from_node": u,

            "to_node": v,

            "road_name": road_name,

            "length_m": length,

            "travel_time_sec":
                travel_time
        })

    # --------------------------------------------------------
    # Average speed
    # --------------------------------------------------------

    if total_travel_time > 0:

        average_speed_kmh = (
            total_distance
            /
            total_travel_time
            * 3.6
        )

    else:

        average_speed_kmh = 0

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = {

        "source_node":
            source_node,

        "destination_node":
            destination_node,

        "source_snap_distance_m":
            source_distance,

        "destination_snap_distance_m":
            destination_distance,

        "route_nodes":
            route,

        "route_edges":
            route_edges,

        "distance_m":
            total_distance,

        "distance_km":
            total_distance / 1000,

        "base_travel_time_sec":
            total_travel_time,

        "base_travel_time_min":
            total_travel_time / 60,

        "average_speed_kmh":
            average_speed_kmh,

        "road_names":
            road_names
    }

    print()
    print(
        "Route nodes:",
        len(route)
    )

    print(
        "Distance:",
        round(
            result["distance_km"],
            2
        ),
        "km"
    )

    print(
        "Base travel time:",
        round(
            result["base_travel_time_min"],
            2
        ),
        "minutes"
    )

    print(
        "Average speed:",
        round(
            result["average_speed_kmh"],
            2
        ),
        "km/h"
    )

    print()
    print("Roads:")

    for road in road_names[:20]:
        print(
            " -",
            road
        )

    if len(road_names) > 20:
        print(
            "... and",
            len(road_names) - 20,
            "more"
        )

    return result


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    # Example:
    # Hebbal area → Bengaluru city area

    result = calculate_route(
        source_lat=13.0358,
        source_lon=77.5970,

        destination_lat=12.9716,
        destination_lon=77.5946
    )

    print()
    print("=" * 60)
    print("ROUTE ENGINE TEST COMPLETE")
    print("=" * 60)