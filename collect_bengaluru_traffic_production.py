import os
import time
import json
import math
import pickle
import hashlib
import argparse
import requests
import pandas as pd

from datetime import datetime, timedelta

# --once collects exactly one snapshot and exits (for a scheduler / a manual
# single run); default (no flag) behavior is unchanged — loop forever at
# INTERVAL_SECONDS. Same pattern as traffic_module/data/collect_live_traffic_history.py.
_parser = argparse.ArgumentParser(description="Bengaluru production traffic collector")
_parser.add_argument("--once", action="store_true",
                      help="Collect exactly one snapshot and exit instead of looping forever.")
_args, _unknown = _parser.parse_known_args()


# ============================================================
# BENGALURU REAL-TIME TRAFFIC COLLECTOR
# PRODUCTION / RESTART-SAFE VERSION
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

OUTPUT_FILE = "bengaluru_traffic_history.csv"

ERROR_FILE = "bengaluru_traffic_errors.csv"

TOMTOM_URL = (
    "https://api.tomtom.com/"
    "traffic/services/4/flowSegmentData/"
    "absolute/10/json"
)

API_KEY = os.environ.get("TOMTOM_API_KEY")


# ============================================================
# COLLECTION CONFIGURATION
# ============================================================

# Important traffic-carrying road classes.
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

# Bengaluru graph coverage.
MIN_LAT = 12.8353021
MAX_LAT = 13.1421946
MIN_LON = 77.4599903
MAX_LON = 77.7766383


# Request timeout.
REQUEST_TIMEOUT = 20

# Delay between requests.
REQUEST_DELAY_SECONDS = 0.15

# Continuous collection interval.
INTERVAL_SECONDS = 300


# ============================================================
# API KEY
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
print("BENGALURU REAL TRAFFIC COLLECTOR")
print("=" * 70)

print()
print("Loading Bengaluru road graph...")

with open(
    GRAPH_FILE,
    "rb"
) as f:

    graph = pickle.load(f)


print("Nodes:", len(graph.nodes))
print("Edges:", len(graph.edges))


# ============================================================
# DISTANCE
# ============================================================

def haversine_m(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371000.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(
        lat2 - lat1
    )

    dl = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        *
        math.cos(p2)
        *
        math.sin(dl / 2) ** 2
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
# NORMALIZE OSM VALUE
# ============================================================

def normalize_value(value):

    if value is None:
        return None

    if isinstance(
        value,
        list
    ):

        values = []

        for item in value:

            if item is None:
                continue

            text = str(item).strip()

            if text:
                values.append(text)

        return " | ".join(
            dict.fromkeys(values)
        )

    return str(value)


# ============================================================
# SEGMENT ID
# ============================================================

def create_segment_id(
    coordinates
):

    if not coordinates:

        return None

    try:

        coordinate_list = (
            coordinates.get(
                "coordinate",
                []
            )
        )

        if not coordinate_list:

            return None

        normalized = []

        for c in coordinate_list:

            lat = round(
                float(c["latitude"]),
                5
            )

            lon = round(
                float(c["longitude"]),
                5
            )

            normalized.append(
                f"{lat},{lon}"
            )

        raw = "|".join(
            normalized
        )

        return hashlib.sha1(
            raw.encode("utf-8")
        ).hexdigest()

    except Exception:

        return None


# ============================================================
# WARD REGISTRY + BOUNDARIES (real data)
# ============================================================
# Same ward-mapping method already used by
# integration/geo/build_ward_registry.py: real polygon containment first
# (shapely), nearest real-ward-centroid (haversine) otherwise. Reused,
# not reinvented — never a fabricated or guessed ward assignment.

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

WARD_REGISTRY_FILE = r"D:\major project\integration\geo\ward_registry.json"
WARD_GEOJSON_FILE = r"D:\major project\integration\geo\bengaluru_wards.geojson"

# These 3 wards were found — by an actual network-free dry run against
# this same graph file, not assumed — to have zero candidate edges among
# motorway/trunk/primary/secondary/tertiary. For ONLY these 3, real
# residential/unclassified OSM edges are allowed as a fallback so they
# aren't silently left uncovered. Every other ward must have a major-road
# candidate or it is honestly reported as uncovered — never fabricated.
FALLBACK_ONLY_WARD_IDS = {19883386, 19883419, 19884565}
FALLBACK_ROAD_TYPES = {"residential", "unclassified"}

# Rotation state persisted here so restarting the collector (or running
# repeated --once invocations from a scheduler) continues the rotation
# instead of always starting again at the first batch.
ROTATION_STATE_FILE = "bengaluru_collector_rotation_state.json"

BATCH_SIZE = 8

print()
print("Loading ward registry + boundaries...")

with open(WARD_REGISTRY_FILE, encoding="utf-8") as f:
    _ward_registry = json.load(f)

_wards_by_id = {
    w["ward_id"]: w
    for w in _ward_registry["wards"].values()
}

with open(WARD_GEOJSON_FILE, encoding="utf-8") as f:
    _ward_geo = json.load(f)

_ward_polygons = []
_ward_polygon_ids = []

for _feat in _ward_geo["features"]:
    _ward_polygons.append(shape(_feat["geometry"]))
    _ward_polygon_ids.append(_feat["properties"]["ward_id"])

_ward_tree = STRtree(_ward_polygons)

print("Wards loaded:", len(_wards_by_id))
print("Ward boundaries loaded:", len(_ward_polygons), "(of", len(_wards_by_id), "total — the rest use nearest-centroid fallback)")


def find_ward_for_point(lat, lon):
    """Real polygon containment first; nearest real ward centroid
    (haversine) otherwise. Never a fabricated or guessed assignment."""

    pt = Point(lon, lat)

    for idx in _ward_tree.query(pt):
        if _ward_polygons[idx].contains(pt):
            return _ward_polygon_ids[idx]

    best_wid, best_dist = None, float("inf")

    for wid, w in _wards_by_id.items():
        if w.get("centroid_lat") is None:
            continue
        d = haversine_m(lat, lon, w["centroid_lat"], w["centroid_lon"])
        if d < best_dist:
            best_dist = d
            best_wid = wid

    return best_wid


# ============================================================
# SELECT ROAD POINTS (real OSM edges only)
# ============================================================

print()
print("Selecting road edges...")


def extract_candidates(allowed_highway_types):
    """Real OSM edges (bengaluru_graph.pkl) whose midpoint falls in the
    Bengaluru bbox and whose highway tag matches allowed_highway_types.
    No coordinate is ever invented — every point here is an actual edge
    midpoint from the real graph."""

    found = []

    for u, v, key, data in graph.edges(keys=True, data=True):

        highway = data.get("highway")

        if isinstance(highway, list):
            highway_types = {str(x) for x in highway}
        else:
            highway_types = {str(highway)}

        if not (highway_types & allowed_highway_types):
            continue

        u_data = graph.nodes.get(u)
        v_data = graph.nodes.get(v)

        if not u_data or not v_data:
            continue

        lat1 = u_data.get("y")
        lon1 = u_data.get("x")
        lat2 = v_data.get("y")
        lon2 = v_data.get("x")

        if None in (lat1, lon1, lat2, lon2):
            continue

        midpoint_lat = (float(lat1) + float(lat2)) / 2
        midpoint_lon = (float(lon1) + float(lon2)) / 2

        if not (MIN_LAT <= midpoint_lat <= MAX_LAT):
            continue

        if not (MIN_LON <= midpoint_lon <= MAX_LON):
            continue

        length = float(data.get("length", 0))
        speed = float(data.get("speed_kph", 0))

        road_name = normalize_value(data.get("name"))
        highway_name = normalize_value(data.get("highway"))

        found.append({
            "u": u,
            "v": v,
            "key": key,
            "latitude": midpoint_lat,
            "longitude": midpoint_lon,
            "road_name": road_name,
            "highway": highway_name,
            "length_m": length,
            "base_speed_kph": speed,
        })

    return found


candidates = extract_candidates(ROAD_TYPES)

print("Candidate major-road edges:", len(candidates))


# Prioritize larger roads. Fallback classes (residential/unclassified)
# rank below every real major-road class — they are only ever used for
# the 3 wards in FALLBACK_ONLY_WARD_IDS that have no major-road candidate.
road_priority = {

    "motorway": 10,
    "motorway_link": 9,
    "trunk": 8,
    "trunk_link": 7,
    "primary": 6,
    "primary_link": 5,
    "secondary": 4,
    "secondary_link": 3,
    "tertiary": 2,
    "tertiary_link": 1,
    "residential": 0,
    "unclassified": 0,
}


def best_candidate(cands):

    cands = list(cands)

    cands.sort(
        key=lambda p: (
            max(
                road_priority.get(x.strip(), 0)
                for x in p["highway"].split("|")
            ),
            p["length_m"],
        ),
        reverse=True,
    )

    return cands[0]


# ---- map every major-road candidate to its real ward ----
ward_to_candidates = {}

for c in candidates:
    wid = find_ward_for_point(c["latitude"], c["longitude"])
    ward_to_candidates.setdefault(wid, []).append(c)

# ---- one representative per ward, ordered deterministically by ward_id ----
# Sorting by ward_id (a fixed real OSM identifier, never changes between
# runs) is what makes the master list — and therefore every batch — the
# same across restarts, together with the persisted rotation index below.
master_list = []
uncovered_wards = []
_fallback_candidates_cache = None

for wid in sorted(_wards_by_id.keys()):

    cands = ward_to_candidates.get(wid, [])

    if not cands and wid in FALLBACK_ONLY_WARD_IDS:

        if _fallback_candidates_cache is None:
            _fallback_candidates_cache = extract_candidates(FALLBACK_ROAD_TYPES)

        cands = [
            c for c in _fallback_candidates_cache
            if find_ward_for_point(c["latitude"], c["longitude"]) == wid
        ]

    if not cands:
        uncovered_wards.append(wid)
        continue

    rep = dict(best_candidate(cands))
    rep["ward_id"] = wid
    rep["ward_name"] = _wards_by_id[wid]["ward_name"]
    master_list.append(rep)

print()
print("Wards with a representative point:", len(master_list))
print("Wards WITHOUT a representative point:", len(uncovered_wards))

if uncovered_wards:
    for _wid in uncovered_wards:
        print(
            "  -", _wid, _wards_by_id[_wid]["ward_name"],
            "(no real OSM road edge found for this ward, including fallback classes where applicable)"
        )

NUM_BATCHES = -(-len(master_list) // BATCH_SIZE) if master_list else 0

print()
print("Master list size (deterministic, fixed across restarts):", len(master_list))
print("Batch size:", BATCH_SIZE)
print("Number of batches:", NUM_BATCHES)
print("Max revisit interval per ward:", NUM_BATCHES * (INTERVAL_SECONDS // 60), "minutes",
      f"(~{NUM_BATCHES * INTERVAL_SECONDS / 3600:.1f}h)" if NUM_BATCHES else "")

print()
print("First 5 master-list entries:")
for _m in master_list[:5]:
    print(
        "  -", f"ward={_m['ward_id']} ({_m['ward_name']})",
        "->", _m["road_name"] or "(unnamed)",
        f"[{_m['highway']}]",
        f"osm_edge=({_m['u']},{_m['v']},{_m['key']})"
    )


# ============================================================
# ROTATION STATE (restart-safe)
# ============================================================

def load_rotation_state():

    if NUM_BATCHES == 0:
        return 0

    if os.path.exists(ROTATION_STATE_FILE):

        try:

            with open(ROTATION_STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)

            return int(state.get("next_batch_index", 0)) % NUM_BATCHES

        except Exception:

            return 0

    return 0


def save_rotation_state(next_index):

    if NUM_BATCHES == 0:
        return

    with open(ROTATION_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"next_batch_index": next_index % NUM_BATCHES}, f)


def get_batch(batch_index):

    start = batch_index * BATCH_SIZE
    end = start + BATCH_SIZE

    return master_list[start:end]


_batch_index = load_rotation_state()

print()
print("Rotation state loaded — starting at batch index:", _batch_index,
      "(0 = first run or no state file yet; otherwise resumed from a previous run)")


# ============================================================
# TOMTOM
# ============================================================

def get_traffic(
    latitude,
    longitude
):

    params = {

        "key":
            API_KEY,

        "point":
            f"{latitude},{longitude}"
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


        coordinates = flow.get(
            "coordinates"
        )


        return {

            "status":
                "OK",

            "http_status":
                response.status_code,

            "frc":
                flow.get("frc"),

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

            "segment_geometry":
                json.dumps(
                    coordinates
                )
                if coordinates
                else None,

            "tomtom_segment_id":
                create_segment_id(
                    coordinates
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
# COLLECT SNAPSHOT
# ============================================================

def collect_snapshot(points):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    print()
    print("=" * 70)
    print("COLLECTING REAL BENGALURU TRAFFIC")
    print("=" * 70)

    print(
        "Timestamp:",
        timestamp
    )

    print(
        "Points this batch:",
        len(points)
    )


    results = []


    for index, point in enumerate(
        points,
        start=1
    ):

        print(
            f"[{index}/{len(points)}]",
            f"ward={point.get('ward_id')}",
            point["road_name"],
            "|",
            point["latitude"],
            point["longitude"]
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

            "sample_latitude":
                point["latitude"],

            "sample_longitude":
                point["longitude"],

            "osm_road_name":
                point["road_name"],

            "osm_highway":
                point["highway"],

            "edge_length_m":
                point["length_m"],

            "osm_base_speed_kph":
                point["base_speed_kph"]
        }


        row.update(
            traffic
        )


        current = traffic.get(
            "current_speed_kmh"
        )

        free = traffic.get(
            "free_flow_speed_kmh"
        )


        if (
            current is not None
            and free is not None
            and float(free) > 0
        ):

            current = float(
                current
            )

            free = float(
                free
            )


            row["speed_ratio"] = (
                current / free
            )


            row["delay_percent"] = (
                1 -
                current / free
            ) * 100


        else:

            row["speed_ratio"] = None

            row["delay_percent"] = None


        results.append(
            row
        )


        time.sleep(
            REQUEST_DELAY_SECONDS
        )


    return pd.DataFrame(
        results
    )


# ============================================================
# SAVE SNAPSHOT
# ============================================================

def save_snapshot(df):

    if len(df) == 0:

        return


    if os.path.exists(
        OUTPUT_FILE
    ):

        df.to_csv(
            OUTPUT_FILE,
            mode="a",
            header=False,
            index=False
        )

    else:

        df.to_csv(
            OUTPUT_FILE,
            index=False
        )


# ============================================================
# ERROR LOG
# ============================================================

def save_errors(df):

    errors = df[
        df["status"] == "ERROR"
    ].copy()


    if len(errors) == 0:

        return


    if os.path.exists(
        ERROR_FILE
    ):

        errors.to_csv(
            ERROR_FILE,
            mode="a",
            header=False,
            index=False
        )

    else:

        errors.to_csv(
            ERROR_FILE,
            index=False
        )


# ============================================================
# SNAPSHOT SUMMARY
# ============================================================

def print_summary(df):

    successful = df[
        df["status"] == "OK"
    ]


    errors = df[
        df["status"] == "ERROR"
    ]


    print()
    print("=" * 70)
    print("SNAPSHOT COMPLETE")
    print("=" * 70)

    print(
        "Requests:",
        len(df)
    )

    print(
        "Successful:",
        len(successful)
    )

    print(
        "Errors:",
        len(errors)
    )


    if len(successful) > 0:

        print(
            "Unique TomTom segments:",
            successful[
                "tomtom_segment_id"
            ].nunique()
        )


        print(
            "Observed road types:",
            successful[
                "osm_highway"
            ].nunique()
        )


        print()
        print(
            "Current speed:"
        )

        print(
            successful[
                "current_speed_kmh"
            ].describe()
        )


        print()
        print(
            "Delay percentage:"
        )

        print(
            successful[
                "delay_percent"
            ].describe()
        )


        print()
        print(
            "Road closures:",
            successful[
                "road_closure"
            ].fillna(False).astype(bool).sum()
        )


# ============================================================
# MAIN LOOP
# ============================================================

print()
print("=" * 70)
print("PRODUCTION COLLECTOR READY")
print("=" * 70)

print(
    "Interval:",
    INTERVAL_SECONDS // 60,
    "minutes"
)

print(
    "Output:",
    OUTPUT_FILE
)

if _args.once:

    print("Mode: --once (single snapshot, then exit)")

print("Batch size:", BATCH_SIZE)
print("Batches in rotation:", NUM_BATCHES)

print("=" * 70)

if NUM_BATCHES == 0:

    print("No representative points available — nothing to collect. Exiting.")
    raise SystemExit(1)


try:

    while True:

        current_batch_index = _batch_index
        batch = get_batch(current_batch_index)

        print()
        print(
            f"Batch {current_batch_index + 1}/{NUM_BATCHES}",
            "— wards:",
            [p["ward_id"] for p in batch]
        )

        # A failure anywhere in one cycle (a bad response shape, a disk
        # hiccup, anything unexpected) must not kill the whole
        # long-running process — that is what actually happened to the
        # earlier collection run (one snapshot written, then the process
        # silently died with nothing catching the error). Individual
        # per-point request failures were already handled inside
        # get_traffic() (returns a status="ERROR" row instead of
        # raising); this is the cycle-level safety net on top of that.
        try:

            snapshot = collect_snapshot(batch)

            save_snapshot(
                snapshot
            )

            save_errors(
                snapshot
            )

            print_summary(
                snapshot
            )

            failed_this_cycle = int(
                (snapshot["status"] == "ERROR").sum()
            )

            successful_this_cycle = int(
                (snapshot["status"] == "OK").sum()
            )

        except Exception as cycle_error:

            failed_this_cycle = len(batch)
            successful_this_cycle = 0

            print()
            print("=" * 70)
            print("CYCLE ERROR — this cycle failed, collection continues")
            print("=" * 70)
            print(cycle_error)

        print()
        print(
            "Successful requests this cycle:",
            successful_this_cycle
        )
        print(
            "Failed requests this cycle:",
            failed_this_cycle
        )

        # Advance and persist rotation state regardless of this cycle's
        # success/failure — a batch that errored still counts as "visited"
        # for rotation purposes (its own next attempt will come back
        # around after NUM_BATCHES more cycles), otherwise a persistently
        # failing batch could stall the whole rotation on itself forever.
        _batch_index = (current_batch_index + 1) % NUM_BATCHES
        save_rotation_state(_batch_index)

        if _args.once:

            break

        next_run = datetime.now() + timedelta(seconds=INTERVAL_SECONDS)

        print()
        print(
            "Next collection at:",
            next_run.strftime("%Y-%m-%d %H:%M:%S"),
            f"(in {INTERVAL_SECONDS // 60} minutes)"
        )

        time.sleep(
            INTERVAL_SECONDS
        )


except KeyboardInterrupt:

    print()
    print("=" * 70)
    print("COLLECTOR STOPPED SAFELY")
    print("=" * 70)