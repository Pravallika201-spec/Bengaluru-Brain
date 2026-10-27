import pandas as pd

from route_engine import calculate_route


# ============================================================
# CONFIGURATION
# ============================================================

LIVE_PREDICTIONS_FILE = "latest_traffic_predictions.csv"


# ============================================================
# LOAD LIVE TRAFFIC
# ============================================================

def load_live_traffic():

    df = pd.read_csv(
        LIVE_PREDICTIONS_FILE
    )

    df["traffic_location"] = (
        df["traffic_location"]
        .astype(str)
    )

    return df


# ============================================================
# FIND NEAREST TRAFFIC LOCATION
# ============================================================

def find_nearest_traffic_point(
    latitude,
    longitude,
    traffic_df
):

    traffic_df = traffic_df.copy()

    # Approximate distance using latitude/longitude.
    # This is sufficient for matching our monitored
    # traffic points to the route.

    traffic_df["distance"] = (

        (traffic_df["latitude"] - latitude) ** 2

        +

        (traffic_df["longitude"] - longitude) ** 2

    ) ** 0.5

    nearest = traffic_df.loc[
        traffic_df["distance"].idxmin()
    ]

    return nearest


# ============================================================
# CALCULATE TRAFFIC-AWARE ROUTE
# ============================================================

def calculate_traffic_route(
    source_lat,
    source_lon,
    destination_lat,
    destination_lon
):

    print()
    print("=" * 60)
    print("BENGALURU TRAFFIC-AWARE ROUTE")
    print("=" * 60)

    # --------------------------------------------------------
    # Load traffic
    # --------------------------------------------------------

    traffic_df = load_live_traffic()

    print(
        "Live traffic locations:",
        len(traffic_df)
    )

    # --------------------------------------------------------
    # Calculate route
    # --------------------------------------------------------

    route = calculate_route(
        source_lat,
        source_lon,
        destination_lat,
        destination_lon
    )

    # --------------------------------------------------------
    # Route statistics
    # --------------------------------------------------------

    distance_km = route[
        "distance_km"
    ]

    base_time_min = route[
        "base_travel_time_min"
    ]

    base_speed = route[
        "average_speed_kmh"
    ]

    # --------------------------------------------------------
    # Find traffic observations near route
    # --------------------------------------------------------

    traffic_points = []

    route_nodes = route[
        "route_nodes"
    ]

    # Sample route nodes instead of querying
    # every node.

    sample_nodes = route_nodes[
        ::max(
            1,
            len(route_nodes) // 20
        )
    ]

    for node in sample_nodes:

        node_data = route_engine_graph.nodes[
            node
        ]

        if (
            "y" not in node_data
            or
            "x" not in node_data
        ):
            continue

        latitude = float(
            node_data["y"]
        )

        longitude = float(
            node_data["x"]
        )

        nearest = find_nearest_traffic_point(
            latitude,
            longitude,
            traffic_df
        )

        traffic_points.append(
            nearest
        )

    # --------------------------------------------------------
    # Remove duplicate traffic locations
    # --------------------------------------------------------

    if traffic_points:

        traffic_points_df = pd.DataFrame(
            traffic_points
        ).drop_duplicates(
            subset=[
                "traffic_location"
            ]
        )

    else:

        traffic_points_df = pd.DataFrame()


    # --------------------------------------------------------
    # Traffic calculations
    # --------------------------------------------------------

    if len(traffic_points_df) > 0:

        current_speed = (
            traffic_points_df[
                "current_speed_kmh"
            ].mean()
        )

        predicted_speed = (
            traffic_points_df[
                "predicted_next_speed_kmh"
            ].mean()
        )

        delay_percent = (
            traffic_points_df[
                "delay_percent"
            ].mean()
        )

        statuses = (
            traffic_points_df[
                "traffic_status"
            ].value_counts()
        )

        traffic_status = (
            statuses.index[0]
        )

        confidence = (
            traffic_points_df[
                "confidence"
            ].mean()
        )

    else:

        current_speed = base_speed

        predicted_speed = base_speed

        delay_percent = 0

        traffic_status = "UNKNOWN"

        confidence = 0


    # --------------------------------------------------------
    # Traffic-adjusted travel time
    # --------------------------------------------------------

    if current_speed > 0:

        traffic_time_min = (

            distance_km
            /
            current_speed
            * 60

        )

    else:

        traffic_time_min = (
            base_time_min
        )


    delay_min = (
        traffic_time_min
        -
        base_time_min
    )


    # --------------------------------------------------------
    # Predicted travel time
    # --------------------------------------------------------

    if predicted_speed > 0:

        predicted_time_min = (

            distance_km
            /
            predicted_speed
            * 60

        )

    else:

        predicted_time_min = (
            traffic_time_min
        )


    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result = {

        "distance_km":
            distance_km,

        "base_travel_time_min":
            base_time_min,

        "current_travel_time_min":
            traffic_time_min,

        "predicted_travel_time_min":
            predicted_time_min,

        "delay_min":
            delay_min,

        "base_speed_kmh":
            base_speed,

        "current_speed_kmh":
            current_speed,

        "predicted_speed_kmh":
            predicted_speed,

        "delay_percent":
            delay_percent,

        "traffic_status":
            traffic_status,

        "confidence":
            confidence,

        "road_names":
            route["road_names"],

        "traffic_points":
            traffic_points_df.to_dict(
                orient="records"
            )
    }


    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("TRAFFIC-AWARE ROUTE RESULT")
    print("=" * 60)

    print(
        "Distance:",
        round(
            distance_km,
            2
        ),
        "km"
    )

    print(
        "Base travel time:",
        round(
            base_time_min,
            2
        ),
        "min"
    )

    print(
        "Current travel time:",
        round(
            traffic_time_min,
            2
        ),
        "min"
    )

    print(
        "Predicted travel time:",
        round(
            predicted_time_min,
            2
        ),
        "min"
    )

    print(
        "Current speed:",
        round(
            current_speed,
            2
        ),
        "km/h"
    )

    print(
        "Predicted speed:",
        round(
            predicted_speed,
            2
        ),
        "km/h"
    )

    print(
        "Delay:",
        round(
            delay_min,
            2
        ),
        "min"
    )

    print(
        "Traffic:",
        traffic_status
    )

    print(
        "Confidence:",
        round(
            confidence,
            3
        )
    )

    print()
    print("Traffic points used:")

    for point in traffic_points_df[
        "traffic_location"
    ].tolist():

        print(
            " -",
            point
        )

    return result


# ============================================================
# LOAD GRAPH FOR NODE ACCESS
# ============================================================

import pickle

GRAPH_FILE = (
    r"D:\major project\traffic_module"
    r"\backend\data\bengaluru_graph.pkl"
)

with open(
    GRAPH_FILE,
    "rb"
) as file:

    route_engine_graph = pickle.load(
        file
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    # Same test route used previously.

    result = calculate_traffic_route(

        source_lat=13.0358,
        source_lon=77.5970,

        destination_lat=12.9716,
        destination_lon=77.5946

    )

    print()
    print("=" * 60)
    print("TRAFFIC ROUTE INTEGRATION TEST COMPLETE")
    print("=" * 60)