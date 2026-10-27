import os
import time
import pickle
import math
import requests
import pandas as pd
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

OUTPUT_FILE = "bengaluru_traffic_segments.csv"

TOMTOM_URL = (
    "https://api.tomtom.com/"
    "traffic/services/4/flowSegmentData/"
    "absolute/10/json"
)

API_KEY = os.environ.get("TOMTOM_API_KEY")


# ------------------------------------------------------------
# PILOT SETTINGS
# ------------------------------------------------------------

# We are NOT querying every one of the 393,629 edges.
# The pilot samples important roads first.

ROAD_TYPES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
}

# Minimum distance between sample points in metres.
# This keeps the pilot controlled.
MIN_POINT_DISTANCE_M = 1000

# Maximum number of requests in the pilot.
MAX_REQUESTS = 100

REQUEST_TIMEOUT = 20


# ============================================================
# API KEY CHECK
# ============================================================

if not API_KEY:

    print("=" * 70)
    print("ERROR: TOMTOM_API_KEY IS NOT SET")
    print("=" * 70)

    print()
    print('Run:')
    print('$env:TOMTOM_API_KEY="YOUR_KEY"')
    print()

    raise SystemExit(1)


# ============================================================
# LOAD GRAPH
# ============================================================

print("=" * 70)
print("BENGALURU CITY-WIDE TRAFFIC PILOT")
print("=" * 70)

print()
print("Loading Bengaluru road graph...")

with open(
    GRAPH_FILE,
    "rb"
) as f:

    graph = pickle.load(f)


print(
    "Nodes:",
    len(graph.nodes)
)

print(
    "Edges:",
    len(graph.edges)
)


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_m(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(
        lat2 - lat1
    )

    dlambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dphi / 2) ** 2
        +
        math.cos(phi1)
        *
        math.cos(phi2)
        *
        math.sin(dlambda / 2) ** 2
    )

    return (
        2
        *
        R
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


# ============================================================
# GENERATE REPRESENTATIVE ROAD POINTS
# ============================================================

print()
print("Selecting important road edges...")

candidate_points = []


for u, v, key, data in graph.edges(
    keys=True,
    data=True
):

    highway = data.get(
        "highway"
    )

    if isinstance(
        highway,
        list
    ):

        highway_types = set(
            str(x)
            for x in highway
        )

    else:

        highway_types = {
            str(highway)
        }


    if not (
        highway_types
        &
        ROAD_TYPES
    ):

        continue


    # --------------------------------------------------------
    # Get edge endpoints
    # --------------------------------------------------------

    u_data = graph.nodes.get(u)
    v_data = graph.nodes.get(v)

    if not u_data or not v_data:
        continue


    lat1 = u_data.get("y")
    lon1 = u_data.get("x")

    lat2 = v_data.get("y")
    lon2 = v_data.get("x")


    if (
        lat1 is None
        or lon1 is None
        or lat2 is None
        or lon2 is None
    ):

        continue


    # --------------------------------------------------------
    # Use midpoint of edge
    # --------------------------------------------------------

    midpoint_lat = (
        float(lat1)
        +
        float(lat2)
    ) / 2

    midpoint_lon = (
        float(lon1)
        +
        float(lon2)
    ) / 2


    candidate_points.append({

        "u": u,

        "v": v,

        "key": key,

        "latitude":
            midpoint_lat,

        "longitude":
            midpoint_lon,

        "road_name":
            data.get(
                "name"
            ),

        "highway":
            str(
                data.get(
                    "highway"
                )
            ),

        "length_m":
            float(
                data.get(
                    "length",
                    0
                )
            ),

        "base_speed_kph":
            float(
                data.get(
                    "speed_kph",
                    0
                )
            ),
    })


print(
    "Candidate road points:",
    len(candidate_points)
)


# ============================================================
# SPATIAL SAMPLING
# ============================================================

print()
print(
    "Creating controlled city-wide sample..."
)

# Sort longer / more important roads first.
candidate_points.sort(
    key=lambda x: (
        -x["length_m"],
        -x["base_speed_kph"]
    )
)


selected_points = []


for point in candidate_points:

    if (
        len(selected_points)
        >= MAX_REQUESTS
    ):

        break


    too_close = False


    for selected in selected_points:

        distance = haversine_m(
            point["latitude"],
            point["longitude"],
            selected["latitude"],
            selected["longitude"]
        )


        if (
            distance
            <
            MIN_POINT_DISTANCE_M
        ):

            too_close = True

            break


    if not too_close:

        selected_points.append(
            point
        )


print(
    "Selected points:",
    len(selected_points)
)

print(
    "Maximum requests:",
    MAX_REQUESTS
)

print(
    "Minimum point spacing:",
    MIN_POINT_DISTANCE_M,
    "metres"
)


# ============================================================
# TOMTOM REQUEST
# ============================================================

def get_traffic(
    latitude,
    longitude
):

    params = {

        "key":
            API_KEY,

        "point":
            f"{latitude},{longitude}",
    }


    try:

        response = requests.get(

            TOMTOM_URL,

            params=params,

            timeout=REQUEST_TIMEOUT
        )


        if response.status_code != 200:

            return {

                "status":
                    "ERROR",

                "http_status":
                    response.status_code,

                "error":
                    response.text[:500]
            }


        data = response.json()


        flow = data.get(
            "flowSegmentData"
        )


        if not flow:

            return {

                "status":
                    "ERROR",

                "http_status":
                    response.status_code,

                "error":
                    "flowSegmentData missing"
            }


        return {

            "status":
                "OK",

            "http_status":
                response.status_code,

            "frc":
                flow.get(
                    "frc"
                ),

            "current_speed_kmh":
                flow.get(
                    "currentSpeed"
                ),

            "free_flow_speed_kmh":
                flow.get(
                    "freeFlowSpeed"
                ),

            "current_travel_time_sec":
                flow.get(
                    "currentTravelTime"
                ),

            "free_flow_travel_time_sec":
                flow.get(
                    "freeFlowTravelTime"
                ),

            "confidence":
                flow.get(
                    "confidence"
                ),

            "road_closure":
                flow.get(
                    "roadClosure"
                ),

            "coordinates":
                flow.get(
                    "coordinates"
                )
        }


    except Exception as e:

        return {

            "status":
                "ERROR",

            "http_status":
                None,

            "error":
                str(e)
        }


# ============================================================
# COLLECT ONE SNAPSHOT
# ============================================================

timestamp = datetime.now().strftime(
    "%Y-%m-%d %H:%M:%S"
)


print()
print("=" * 70)
print("COLLECTING REAL TOMTOM TRAFFIC")
print("=" * 70)

print(
    "Timestamp:",
    timestamp
)


results = []


for index, point in enumerate(
    selected_points,
    start=1
):

    print(
        f"[{index}/{len(selected_points)}]",
        point["road_name"],
        f"({point['latitude']:.6f},"
        f" {point['longitude']:.6f})"
    )


    traffic = get_traffic(

        point["latitude"],

        point["longitude"]
    )


    row = {

        "timestamp":
            timestamp,

        "osm_u":
            point["u"],

        "osm_v":
            point["v"],

        "osm_key":
            point["key"],

        "latitude":
            point["latitude"],

        "longitude":
            point["longitude"],

        "road_name":
            point["road_name"],

        "highway":
            point["highway"],

        "edge_length_m":
            point["length_m"],

        "base_speed_kph":
            point["base_speed_kph"],
    }


    row.update(
        traffic
    )


    # --------------------------------------------------------
    # Derived traffic values
    # --------------------------------------------------------

    current_speed = traffic.get(
        "current_speed_kmh"
    )

    free_speed = traffic.get(
        "free_flow_speed_kmh"
    )


    if (
        current_speed is not None
        and free_speed is not None
        and float(free_speed) > 0
    ):

        row["speed_ratio"] = (
            float(current_speed)
            /
            float(free_speed)
        )

        row["delay_percent"] = (
            1
            -
            (
                float(current_speed)
                /
                float(free_speed)
            )
        ) * 100

    else:

        row["speed_ratio"] = None

        row["delay_percent"] = None


    # --------------------------------------------------------
    # Save TomTom geometry as JSON text
    # --------------------------------------------------------

    import json

    coordinates = traffic.get(
        "coordinates"
    )

    if coordinates:

        row["segment_geometry"] = json.dumps(
            coordinates
        )

    else:

        row["segment_geometry"] = None


    results.append(
        row
    )


# ============================================================
# CREATE DATAFRAME
# ============================================================

df = pd.DataFrame(
    results
)


# ============================================================
# SAVE
# ============================================================

if os.path.exists(
    OUTPUT_FILE
):

    old = pd.read_csv(
        OUTPUT_FILE
    )

    df = pd.concat(
        [
            old,
            df
        ],
        ignore_index=True
    )


df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("CITY-WIDE TRAFFIC PILOT COMPLETE")
print("=" * 70)

print(
    "Requests:",
    len(results)
)

print(
    "Successful:",
    sum(
        1
        for x in results
        if x.get("status") == "OK"
    )
)

print(
    "Errors:",
    sum(
        1
        for x in results
        if x.get("status") == "ERROR"
    )
)

print(
    "Unique roads:",
    df["road_name"].nunique()
)

print(
    "Rows saved:",
    len(df)
)

print()
print(
    "Output:",
    OUTPUT_FILE
)


# ============================================================
# TRAFFIC SUMMARY
# ============================================================

successful = df[
    df["status"] == "OK"
].copy()


if len(successful) > 0:

    print()
    print(
        "Current speed statistics:"
    )

    print(
        successful[
            "current_speed_kmh"
        ].describe()
    )


    print()
    print(
        "Free-flow speed statistics:"
    )

    print(
        successful[
            "free_flow_speed_kmh"
        ].describe()
    )


    print()
    print(
        "Average delay:",
        successful[
            "delay_percent"
        ].mean()
    )


print()
print("=" * 70)
print("PILOT FINISHED")
print("=" * 70)