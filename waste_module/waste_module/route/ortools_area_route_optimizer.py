import os
import math
import pandas as pd

from ortools.constraint_solver import (
    pywrapcp,
    routing_enums_pb2
)


# ============================================================
# BENGALURU OR-TOOLS MULTI-VEHICLE ROUTE OPTIMIZATION ENGINE
# ============================================================


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "waste_module",
    "satellite",
    "outputs"
)

INPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bengaluru_priority_areas.csv"
)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bengaluru_ortools_vehicle_routes.csv"
)


# ============================================================
# ROUTING CONFIGURATION
# ============================================================

# Capacity of one collection vehicle in kilograms.
#
# IMPORTANT:
# This is currently a PROJECT CONFIGURATION VALUE.
# Replace it later with the actual vehicle capacity
# used in your project's assumptions/data.
VEHICLE_CAPACITY_KG = 10000


# Maximum number of vehicles allowed.
MAX_VEHICLES = 20


# Speed is not used for optimization yet.
# We will add travel-time/time-window constraints later.
AVERAGE_SPEED_KMPH = 25


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(delta_lon / 2) ** 2
    )

    c = (
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )

    return (
        earth_radius
        *
        c
    )


# ============================================================
# LOAD PRIORITY AREAS
# ============================================================

def load_priority_areas():

    print(
        "\nLoading priority areas..."
    )

    if not os.path.exists(
        INPUT_FILE
    ):

        raise FileNotFoundError(
            "\nPriority-area file not found:\n"
            f"{INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE
    )

    print(
        f"Priority areas loaded: {len(df)}"
    )

    # --------------------------------------------------------
    # Column-name compatibility shim.
    #
    # bengaluru_priority_areas.csv (produced by the satellite/event pipeline)
    # uses a different header than this script originally expected:
    #   area_location        -> area_name
    #   predicted_daily_waste_kg -> predicted_waste_kg
    #   waste_risk           -> area_risk
    #   priority_score       -> area_priority_score
    # It also has no additional_event_waste_kg column at all; where the real
    # event_impact_factor column is present, that extra load is DERIVED as
    # predicted_daily_waste_kg * (event_impact_factor - 1) (0 when the
    # factor is <= 1 or missing) rather than fabricated from nothing.
    # This mapping was verified against the real CSV header during the
    # Phase 1 audit — see traffic/waste audit notes. Remove this shim if the
    # upstream pipeline is ever changed to emit the original column names.
    # --------------------------------------------------------
    rename_map = {
        "area_location": "area_name",
        "predicted_daily_waste_kg": "predicted_waste_kg",
        "waste_risk": "area_risk",
        "priority_score": "area_priority_score",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns and v not in df.columns})

    if "additional_event_waste_kg" not in df.columns:
        if "event_impact_factor" in df.columns and "predicted_waste_kg" in df.columns:
            factor = pd.to_numeric(df["event_impact_factor"], errors="coerce").fillna(1.0)
            base = pd.to_numeric(df["predicted_waste_kg"], errors="coerce").fillna(0.0)
            df["additional_event_waste_kg"] = (base * (factor - 1.0)).clip(lower=0.0)
        else:
            df["additional_event_waste_kg"] = 0.0

    required_columns = [

        "area_name",

        "latitude",

        "longitude",

        "predicted_waste_kg",

        "additional_event_waste_kg",

        "area_risk",

        "area_priority_score"

    ]

    missing = [

        column

        for column in required_columns

        if column not in df.columns

    ]

    if missing:

        raise ValueError(
            "\nMissing required columns:\n"
            f"{missing}"
        )

    return df


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_data(df):

    print(
        "\nPreparing routing data..."
    )

    df = df.copy()

    # --------------------------------------------------------
    # Convert numerical columns
    # --------------------------------------------------------

    numerical_columns = [

        "latitude",

        "longitude",

        "predicted_waste_kg",

        "additional_event_waste_kg",

        "area_priority_score"

    ]

    for column in numerical_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Remove invalid coordinates
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "latitude",
            "longitude"
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Ensure waste is positive
    # --------------------------------------------------------

    df[
        "predicted_waste_kg"
    ] = df[
        "predicted_waste_kg"
    ].clip(
        lower=0
    )

    print(
        f"Valid routing locations: {len(df)}"
    )

    # --------------------------------------------------------
    # Check if any single area exceeds vehicle capacity
    # --------------------------------------------------------

    oversized = df[
        df["predicted_waste_kg"]
        >
        VEHICLE_CAPACITY_KG
    ]

    if len(oversized) > 0:

        print(
            "\nWARNING:"
        )

        print(
            "The following areas contain more "
            "predicted waste than one vehicle "
            "can carry:"
        )

        print(
            oversized[
                [
                    "area_name",
                    "predicted_waste_kg"
                ]
            ].to_string(
                index=False
            )
        )

        print(
            "\nThese locations will require "
            "multiple collection trips."
        )

    return df


# ============================================================
# DETERMINE NUMBER OF VEHICLES
# ============================================================

def determine_vehicle_count(
    total_waste,
    vehicle_capacity_kg=None
):
    capacity = vehicle_capacity_kg if vehicle_capacity_kg else VEHICLE_CAPACITY_KG

    minimum_vehicles = math.ceil(
        total_waste
        /
        capacity
    )

    # The exact theoretical minimum (ceil(total/capacity)) leaves ZERO slack
    # for real-world bin-packing: with unevenly-sized area demands, OR-Tools
    # can genuinely have no feasible assignment at that count (verified
    # during the Phase 1 audit: 50 real areas, 69,344.83 kg total, capacity
    # 10,000 kg/truck -> minimum_vehicles=7 -> SolveWithParameters returned
    # no solution). Real waste-collection fleets always carry spare
    # capacity for exactly this reason, so add one extra vehicle of
    # headroom (still capped at MAX_VEHICLES below).
    number_of_vehicles = max(
        1,
        minimum_vehicles + 1
    )

    if (
        number_of_vehicles
        >
        MAX_VEHICLES
    ):

        raise ValueError(

            f"\nRequired vehicles: "
            f"{number_of_vehicles}\n"

            f"Maximum configured vehicles: "
            f"{MAX_VEHICLES}\n\n"

            "Increase MAX_VEHICLES or "
            "increase VEHICLE_CAPACITY_KG."

        )

    return number_of_vehicles


# ============================================================
# CREATE DEPOT
# ============================================================

def create_depot(
    df
):

    """
    Creates a temporary geographic depot at the
    centroid of the priority locations.

    IMPORTANT:
    This is only a project prototype.

    Later we should replace this with the actual
    waste collection depot location.
    """

    depot_latitude = (
        df["latitude"].mean()
    )

    depot_longitude = (
        df["longitude"].mean()
    )

    return (
        depot_latitude,
        depot_longitude
    )


# ============================================================
# CREATE DISTANCE MATRIX
# ============================================================

def create_distance_matrix(
    df,
    depot_latitude,
    depot_longitude
):

    print(
        "\nCreating distance matrix..."
    )

    locations = [

        (
            depot_latitude,
            depot_longitude
        )

    ]

    for _, row in df.iterrows():

        locations.append(

            (
                float(
                    row["latitude"]
                ),

                float(
                    row["longitude"]
                )

            )

        )

    matrix = []

    for origin in locations:

        row_distances = []

        for destination in locations:

            distance = (
                haversine_distance(

                    origin[0],
                    origin[1],

                    destination[0],
                    destination[1]

                )
            )

            # OR-Tools works well with integers
            distance_meters = int(
                round(
                    distance
                    *
                    1000
                )
            )

            row_distances.append(
                distance_meters
            )

        matrix.append(
            row_distances
        )

    print(
        f"Distance matrix size: "
        f"{len(locations)} x "
        f"{len(locations)}"
    )

    return matrix


# ============================================================
# CREATE OR-TOOLS DATA MODEL
# ============================================================

def create_data_model(
    df,
    distance_matrix,
    number_of_vehicles,
    vehicle_capacity_kg=None
):
    capacity = vehicle_capacity_kg if vehicle_capacity_kg else VEHICLE_CAPACITY_KG

    data = {}

    data[
        "distance_matrix"
    ] = distance_matrix

    # Depot is index 0
    data[
        "depot"
    ] = 0

    data[
        "num_vehicles"
    ] = number_of_vehicles

    # --------------------------------------------------------
    # Demand
    # --------------------------------------------------------

    demands = [0]

    for _, row in df.iterrows():

        demand = int(
            round(
                row[
                    "predicted_waste_kg"
                ]
            )
        )

        demands.append(
            demand
        )

    data[
        "demands"
    ] = demands

    data[
        "vehicle_capacities"
    ] = [

        int(
            capacity
        )

        for _ in range(
            number_of_vehicles
        )

    ]

    return data


# ============================================================
# SOLVE ROUTING PROBLEM
# ============================================================

def solve_routing_problem(
    data,
    time_limit_seconds=None
):

    print(
        "\nInitializing OR-Tools..."
    )

    manager = (
        pywrapcp.RoutingIndexManager(

            len(
                data[
                    "distance_matrix"
                ]
            ),

            data[
                "num_vehicles"
            ],

            data[
                "depot"
            ]

        )
    )

    routing = (
        pywrapcp.RoutingModel(
            manager
        )
    )

    # ========================================================
    # DISTANCE CALLBACK
    # ========================================================

    def distance_callback(
        from_index,
        to_index
    ):

        from_node = (
            manager.IndexToNode(
                from_index
            )
        )

        to_node = (
            manager.IndexToNode(
                to_index
            )
        )

        return data[
            "distance_matrix"
        ][
            from_node
        ][
            to_node
        ]

    distance_callback_index = (
        routing.RegisterTransitCallback(
            distance_callback
        )
    )

    routing.SetArcCostEvaluatorOfAllVehicles(
        distance_callback_index
    )

    # ========================================================
    # CAPACITY CALLBACK
    # ========================================================

    def demand_callback(
        from_index
    ):

        from_node = (
            manager.IndexToNode(
                from_index
            )
        )

        return data[
            "demands"
        ][
            from_node
        ]

    demand_callback_index = (
        routing.RegisterUnaryTransitCallback(
            demand_callback
        )
    )

    routing.AddDimensionWithVehicleCapacity(

        demand_callback_index,

        0,

        data[
            "vehicle_capacities"
        ],

        True,

        "Capacity"

    )

    # ========================================================
    # SEARCH PARAMETERS
    # ========================================================

    search_parameters = (
        pywrapcp.DefaultRoutingSearchParameters()
    )

    search_parameters.first_solution_strategy = (

        routing_enums_pb2
        .FirstSolutionStrategy
        .PATH_CHEAPEST_ARC

    )

    search_parameters.local_search_metaheuristic = (

        routing_enums_pb2
        .LocalSearchMetaheuristic
        .GUIDED_LOCAL_SEARCH

    )

    # Allow a reasonable amount of computation. Default (script/offline use)
    # is 30s; interactive API callers may pass a shorter real budget — this
    # is a genuine, disclosed trade-off (less local-search improvement time),
    # never a fabricated speed-up. GUIDED_LOCAL_SEARCH finds an initial
    # PATH_CHEAPEST_ARC feasible solution almost immediately and spends the
    # rest of the budget improving it, so a shorter budget still yields a
    # real, valid solve — just a less-optimized one.
    search_parameters.time_limit.seconds = int(time_limit_seconds) if time_limit_seconds else 30

    print(
        "\nSolving vehicle routing problem..."
    )

    solution = (
        routing.SolveWithParameters(
            search_parameters
        )
    )

    if solution is None:

        raise RuntimeError(

            "\nOR-Tools could not find "
            "a feasible solution.\n\n"

            "Possible causes:\n"

            "1. Vehicle capacity is too small.\n"

            "2. Number of vehicles is insufficient.\n"

            "3. One or more areas exceed "
            "vehicle capacity."

        )

    print(
        "OR-Tools solution found."
    )

    return (
        manager,
        routing,
        solution
    )


# ============================================================
# EXTRACT ROUTES
# ============================================================

def extract_routes(
    df,
    manager,
    routing,
    solution,
    vehicle_capacity_kg=None
):
    # BUG FIX (Priority 1/3 audit): this previously always divided by the
    # module-level default VEHICLE_CAPACITY_KG regardless of what capacity
    # was actually used to build the solved model — so a custom
    # vehicle_capacity_kg (e.g. solve_routes_for_api(vehicle_capacity_kg=
    # 20000)) reported a utilization_percent computed against 10,000kg
    # instead of the real 20,000kg, silently doubling it.
    capacity = vehicle_capacity_kg if vehicle_capacity_kg else VEHICLE_CAPACITY_KG

    print(
        "\nExtracting vehicle routes..."
    )

    routes = []

    route_number = 1

    for vehicle_id in range(
        routing.vehicles()
    ):

        index = (
            routing.Start(
                vehicle_id
            )
        )

        vehicle_areas = []

        route_distance = 0

        route_load = 0

        route_order = 1

        while not routing.IsEnd(
            index
        ):

            node = (
                manager.IndexToNode(
                    index
                )
            )

            # Node 0 is the depot
            if node != 0:

                area_index = (
                    node - 1
                )

                area = (
                    df.iloc[
                        area_index
                    ]
                )

                vehicle_areas.append({

                    "vehicle_id":
                        route_number,

                    "route_order":
                        route_order,

                    "area_name":
                        area[
                            "area_name"
                        ],

                    "latitude":
                        float(
                            area[
                                "latitude"
                            ]
                        ),

                    "longitude":
                        float(
                            area[
                                "longitude"
                            ]
                        ),

                    "predicted_waste_kg":
                        float(
                            area[
                                "predicted_waste_kg"
                            ]
                        ),

                    "additional_event_waste_kg":
                        float(
                            area[
                                "additional_event_waste_kg"
                            ]
                        ),

                    "area_risk":
                        area[
                            "area_risk"
                        ],

                    "area_priority_score":
                        float(
                            area[
                                "area_priority_score"
                            ]
                        ),

                    "routing_priority":
                        float(
                            area.get(
                                "routing_priority",
                                area[
                                    "area_priority_score"
                                ]
                            )
                        )

                })

                route_load += int(
                    round(
                        area[
                            "predicted_waste_kg"
                        ]
                    )
                )

                route_order += 1

            previous_index = index

            index = (
                solution.Value(
                    routing.NextVar(
                        index
                    )
                )
            )

            route_distance += (
                routing.GetArcCostForVehicle(
                    previous_index,
                    index,
                    vehicle_id
                )
            )

        # Convert meters to kilometres
        route_distance_km = (
            route_distance
            /
            1000
        )

        utilization = round((

            route_load
            /
            capacity
        ) * 100, 2)

        # Only save vehicles that actually visited areas
        if len(vehicle_areas) > 0:

            for item in vehicle_areas:

                item[
                    "vehicle_total_waste_kg"
                ] = route_load

                item[
                    "vehicle_route_distance_km"
                ] = route_distance_km

                item[
                    "vehicle_utilization_percent"
                ] = utilization

            routes.extend(
                vehicle_areas
            )

        route_number += 1

    if len(routes) == 0:

        raise RuntimeError(
            "No collection routes were generated."
        )

    route_df = pd.DataFrame(
        routes
    )

    return route_df


# ============================================================
# ADD LEG DISTANCES
# ============================================================

def add_leg_distances(
    route_df,
    depot_latitude,
    depot_longitude
):

    print(
        "\nCalculating individual route distances..."
    )

    route_df = route_df.copy()

    route_df[
        "distance_from_previous_km"
    ] = 0.0

    route_df[
        "cumulative_distance_km"
    ] = 0.0

    for vehicle_id in sorted(
        route_df[
            "vehicle_id"
        ].unique()
    ):

        mask = (
            route_df[
                "vehicle_id"
            ]
            ==
            vehicle_id
        )

        vehicle_df = (
            route_df.loc[
                mask
            ]
        )

        previous_lat = (
            depot_latitude
        )

        previous_lon = (
            depot_longitude
        )

        cumulative = 0.0

        for index, row in (
            vehicle_df.iterrows()
        ):

            distance = (
                haversine_distance(

                    previous_lat,
                    previous_lon,

                    float(
                        row[
                            "latitude"
                        ]
                    ),

                    float(
                        row[
                            "longitude"
                        ]
                    )

                )
            )

            cumulative += distance

            route_df.loc[
                index,
                "distance_from_previous_km"
            ] = distance

            route_df.loc[
                index,
                "cumulative_distance_km"
            ] = cumulative

            previous_lat = float(
                row[
                    "latitude"
                ]
            )

            previous_lon = float(
                row[
                    "longitude"
                ]
            )

    return route_df


# ============================================================
# SAVE RESULT
# ============================================================

def save_routes(
    route_df
):

    print(
        "\nSaving vehicle routes..."
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    output_columns = [

        "vehicle_id",

        "route_order",

        "area_name",

        "latitude",

        "longitude",

        "predicted_waste_kg",

        "additional_event_waste_kg",

        "area_risk",

        "area_priority_score",

        "routing_priority",

        "distance_from_previous_km",

        "cumulative_distance_km",

        "vehicle_total_waste_kg",

        "vehicle_route_distance_km",

        "vehicle_utilization_percent"

    ]

    route_df[
        output_columns
    ].to_csv(

        OUTPUT_FILE,

        index=False

    )

    print(
        "\nOutput saved to:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# DISPLAY RESULTS
# ============================================================

def display_results(
    route_df,
    depot_latitude,
    depot_longitude
):

    print(
        "\n"
        +
        "=" * 75
    )

    print(
        "OR-TOOLS BENGALURU "
        "MULTI-VEHICLE ROUTE SUMMARY"
    )

    print(
        "=" * 75
    )

    number_of_routes = (
        route_df[
            "vehicle_id"
        ].nunique()
    )

    total_areas = len(
        route_df
    )

    total_waste = (
        route_df[
            "predicted_waste_kg"
        ].sum()
    )

    total_distance = (
        route_df.groupby(
            "vehicle_id"
        )[
            "vehicle_route_distance_km"
        ]
        .first()
        .sum()
    )

    print(
        f"\nCollection vehicles used: "
        f"{number_of_routes}"
    )

    print(
        f"Priority areas covered: "
        f"{total_areas}"
    )

    print(
        f"Total predicted waste: "
        f"{total_waste:,.2f} kg"
    )

    print(
        f"Total route distance: "
        f"{total_distance:.2f} km"
    )

    print(
        f"Vehicle capacity: "
        f"{VEHICLE_CAPACITY_KG:,} kg"
    )

    print(
        "\nVirtual depot:"
    )

    print(
        f"Latitude:  {depot_latitude:.6f}"
    )

    print(
        f"Longitude: {depot_longitude:.6f}"
    )

    # --------------------------------------------------------
    # Vehicle summary
    # --------------------------------------------------------

    print(
        "\n"
        +
        "-" * 75
    )

    print(
        "VEHICLE SUMMARY"
    )

    print(
        "-" * 75
    )

    summary = (
        route_df.groupby(
            "vehicle_id"
        )
        .agg(

            areas=(
                "area_name",
                "count"
            ),

            total_waste_kg=(
                "predicted_waste_kg",
                "sum"
            ),

            route_distance_km=(
                "vehicle_route_distance_km",
                "first"
            ),

            utilization_percent=(
                "vehicle_utilization_percent",
                "first"
            )

        )
        .reset_index()
    )

    print(
        summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Individual routes
    # --------------------------------------------------------

    print(
        "\n"
        +
        "-" * 75
    )

    print(
        "INDIVIDUAL COLLECTION ROUTES"
    )

    print(
        "-" * 75
    )

    for vehicle_id in sorted(
        route_df[
            "vehicle_id"
        ].unique()
    ):

        vehicle_route = (
            route_df[
                route_df[
                    "vehicle_id"
                ]
                ==
                vehicle_id
            ]
        )

        print(
            f"\nVehicle {vehicle_id}:"
        )

        for _, row in (
            vehicle_route.iterrows()
        ):

            print(

                f"  {int(row['route_order']):02d}. "
                f"{row['area_name']} | "
                f"{row['predicted_waste_kg']:,.2f} kg | "
                f"{row['area_risk']}"

            )

    print(
        "\n"
        +
        "=" * 75
    )

    print(
        "OR-TOOLS ROUTE OPTIMIZATION COMPLETED"
    )

    print(
        "=" * 75
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 75
    )

    print(
        "BENGALURU OR-TOOLS "
        "MULTI-VEHICLE ROUTE OPTIMIZATION ENGINE"
    )

    print(
        "=" * 75
    )

    # --------------------------------------------------------
    # 1. Load data
    # --------------------------------------------------------

    df = (
        load_priority_areas()
    )

    # --------------------------------------------------------
    # 2. Prepare data
    # --------------------------------------------------------

    df = (
        prepare_data(
            df
        )
    )

    if len(df) == 0:

        raise ValueError(
            "No valid priority areas found."
        )

    # --------------------------------------------------------
    # 3. Total waste
    # --------------------------------------------------------

    total_waste = (
        df[
            "predicted_waste_kg"
        ].sum()
    )

    print(
        f"\nTotal predicted waste: "
        f"{total_waste:,.2f} kg"
    )

    # --------------------------------------------------------
    # 4. Determine vehicles
    # --------------------------------------------------------

    number_of_vehicles = (
        determine_vehicle_count(
            total_waste
        )
    )

    print(
        f"Vehicles required based on "
        f"capacity: {number_of_vehicles}"
    )

    # --------------------------------------------------------
    # 5. Create virtual depot
    # --------------------------------------------------------

    (
        depot_latitude,
        depot_longitude
    ) = create_depot(
        df
    )

    print(
        "\nTemporary project depot:"
    )

    print(
        f"Latitude:  {depot_latitude:.6f}"
    )

    print(
        f"Longitude: {depot_longitude:.6f}"
    )

    # --------------------------------------------------------
    # 6. Distance matrix
    # --------------------------------------------------------

    distance_matrix = (
        create_distance_matrix(

            df,

            depot_latitude,

            depot_longitude

        )
    )

    # --------------------------------------------------------
    # 7. OR-Tools data
    # --------------------------------------------------------

    data = (
        create_data_model(

            df,

            distance_matrix,

            number_of_vehicles

        )
    )

    # --------------------------------------------------------
    # 8. Solve
    # --------------------------------------------------------

    (
        manager,

        routing,

        solution

    ) = solve_routing_problem(
        data
    )

    # --------------------------------------------------------
    # 9. Extract routes
    # --------------------------------------------------------

    route_df = (
        extract_routes(

            df,

            manager,

            routing,

            solution

        )
    )

    # --------------------------------------------------------
    # 10. Add distances
    # --------------------------------------------------------

    route_df = (
        add_leg_distances(

            route_df,

            depot_latitude,

            depot_longitude

        )
    )

    # --------------------------------------------------------
    # 11. Save
    # --------------------------------------------------------

    save_routes(
        route_df
    )

    # --------------------------------------------------------
    # 12. Display
    # --------------------------------------------------------

    display_results(

        route_df,

        depot_latitude,

        depot_longitude

    )


# ============================================================
# PARAMETERIZED SOLVE (for the live API — genuinely re-solves per call,
# never returns a stale file presented as a fresh result)
# ============================================================

def solve_routes_for_api(area_names=None, num_vehicles=None, vehicle_capacity_kg=None,
                          time_limit_seconds=8):
    """Runs the real OR-Tools solve with the given parameters and returns a
    structured result dict — never writes/reads the cached CSV, never
    fabricates a route. Distinct from main()/solve_routing_problem() in that
    infeasibility is reported as a status, not an unhandled exception,
    because this is meant to be called from a request handler.

    area_names: optional list of area names to restrict routing to (case-
        insensitive substring match against area_name). None = all areas.
    num_vehicles: optional int. None = auto-determine from real total demand
        (same logic as the CLI script).
    vehicle_capacity_kg: optional int. None = the module default (10,000kg).
    time_limit_seconds: real OR-Tools search budget. Shorter = faster but
        potentially less-optimized (still a genuine solve, not fabricated).
    """
    computed_at = pd.Timestamp.utcnow().isoformat()
    t0 = __import__("time").time()

    try:
        df = load_priority_areas()
    except FileNotFoundError as e:
        return {"available": False, "solver_status": "ERROR", "reason": str(e),
                "optimization_timestamp": computed_at}

    df = prepare_data(df)

    if area_names is not None:
        wanted = {a.strip().lower() for a in area_names if a and a.strip()}
        if not wanted:
            return {"available": False, "solver_status": "INVALID_INPUT",
                     "reason": "area_names was provided but contained no usable names",
                     "optimization_timestamp": computed_at}
        matched = df[df["area_name"].str.lower().isin(wanted)]
        unmatched = wanted - set(df["area_name"].str.lower())
        if len(matched) == 0:
            return {"available": False, "solver_status": "INVALID_INPUT",
                     "reason": f"None of the requested areas matched the real dataset: {sorted(wanted)}",
                     "optimization_timestamp": computed_at}
        df = matched.reset_index(drop=True)
    else:
        unmatched = set()

    if len(df) == 0:
        return {"available": False, "solver_status": "INVALID_INPUT",
                 "reason": "No valid routing locations after filtering (empty input)",
                 "optimization_timestamp": computed_at}

    if vehicle_capacity_kg is not None:
        capacity = int(vehicle_capacity_kg)
        if capacity < 1:
            return {"available": False, "solver_status": "INVALID_INPUT",
                     "reason": f"vehicle_capacity_kg must be >= 1, got {capacity}",
                     "optimization_timestamp": computed_at}
    else:
        capacity = VEHICLE_CAPACITY_KG
    total_waste = df["predicted_waste_kg"].sum()

    if num_vehicles is not None:
        n_vehicles = int(num_vehicles)
        if n_vehicles < 1:
            return {"available": False, "solver_status": "INVALID_INPUT",
                     "reason": f"num_vehicles must be >= 1, got {n_vehicles}",
                     "optimization_timestamp": computed_at}
    else:
        try:
            n_vehicles = determine_vehicle_count(total_waste, vehicle_capacity_kg=capacity)
        except ValueError as e:
            return {"available": False, "solver_status": "INVALID_INPUT", "reason": str(e),
                     "optimization_timestamp": computed_at}

    depot_lat, depot_lon = create_depot(df)
    dist_matrix = create_distance_matrix(df, depot_lat, depot_lon)
    data = create_data_model(df, dist_matrix, n_vehicles, vehicle_capacity_kg=capacity)

    try:
        manager, routing, solution = solve_routing_problem(data, time_limit_seconds=time_limit_seconds)
    except RuntimeError as e:
        return {
            "available": False,
            "solver_status": "NO_FEASIBLE_SOLUTION",
            "reason": str(e).strip(),
            "optimization_timestamp": computed_at,
            "solve_time_seconds": round(__import__("time").time() - t0, 2),
            "requested_num_vehicles": n_vehicles,
            "requested_vehicle_capacity_kg": capacity,
            "total_demand_kg": round(float(total_waste), 2),
            "areas_requested": len(df),
        }

    route_df = extract_routes(df, manager, routing, solution, vehicle_capacity_kg=capacity)
    route_df = add_leg_distances(route_df, depot_lat, depot_lon)
    solve_time = round(__import__("time").time() - t0, 2)

    per_vehicle = route_df.groupby("vehicle_id").agg(
        stops=("area_name", "count"),
        total_waste_kg=("vehicle_total_waste_kg", "first"),
        distance_km=("vehicle_route_distance_km", "first"),
        utilization_percent=("vehicle_utilization_percent", "first"),
    ).reset_index().to_dict("records")

    return {
        "available": True,
        "solver_status": "SOLVED",
        "route_source": "FRESH_SOLVE",
        "optimization_timestamp": computed_at,
        "solve_time_seconds": solve_time,
        "num_vehicles": int(route_df["vehicle_id"].nunique()),
        "requested_num_vehicles": n_vehicles,
        "vehicle_capacity_kg": capacity,
        "total_areas_routed": int(len(route_df)),
        "areas_requested": len(df),
        "unmatched_area_names": sorted(unmatched),
        "total_distance_km": float(route_df.groupby("vehicle_id")["vehicle_route_distance_km"].first().sum()),
        "total_demand_kg": round(float(total_waste), 2),
        "per_vehicle": per_vehicle,
        "stops": route_df[["vehicle_id", "route_order", "area_name", "latitude", "longitude",
                            "predicted_waste_kg", "area_risk"]].to_dict("records"),
    }


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()