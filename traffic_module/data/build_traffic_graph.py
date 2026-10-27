import pickle
import pandas as pd
import osmnx as ox
import networkx as nx


# ============================================================
# FILE PATHS
# ============================================================

GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

TRAFFIC_FILE = r"C:\Users\ravip\OneDrive\Desktop\Banglore_traffic_Dataset.csv"

MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_location_mapping.csv"

OUTPUT_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"


# ============================================================
# LOAD OSM GRAPH
# ============================================================

print("Loading Bengaluru road graph...")

with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

print("Graph loaded.")
print("Nodes:", len(G.nodes))
print("Edges:", len(G.edges))


# ============================================================
# LOAD TRAFFIC DATA
# ============================================================

print("\nLoading traffic dataset...")

traffic = pd.read_csv(TRAFFIC_FILE)

print("Traffic rows:", len(traffic))


# ============================================================
# LOAD LOCATION MAPPING
# ============================================================

print("\nLoading location mapping...")

mapping = pd.read_csv(MAPPING_FILE)

print("Mapping rows:", len(mapping))


# ============================================================
# KEEP ONLY RELIABLE MAPPINGS
# ============================================================

valid_mapping = mapping[
    mapping["status"] == "MATCHED"
].copy()

print(
    "Valid mapped locations:",
    len(valid_mapping)
)

print(
    "\nExcluded locations:"
)

excluded = mapping[
    mapping["status"] != "MATCHED"
]

for _, row in excluded.iterrows():
    print(
        f"- {row['traffic_location']} "
        f"({row['status']})"
    )


# ============================================================
# CREATE NODE LOOKUP
# ============================================================

node_lookup = {}

for _, row in valid_mapping.iterrows():

    location = row["traffic_location"]

    node_id = int(row["nearest_node"])

    node_lookup[location] = node_id


# ============================================================
# KEEP ONLY TRAFFIC LOCATIONS THAT HAVE
# RELIABLE OSM MAPPINGS
# ============================================================

traffic = traffic[
    traffic["Road/Intersection Name"]
    .isin(node_lookup.keys())
].copy()

print(
    "\nTraffic rows after location filtering:",
    len(traffic)
)


# ============================================================
# MAP OSM NODE
# ============================================================

traffic["osm_node"] = (
    traffic["Road/Intersection Name"]
    .map(node_lookup)
)


# ============================================================
# GET NODE FEATURES
# ============================================================

print("\nExtracting OSM node features...")


def get_node_degree(node_id):

    try:
        return G.degree[node_id]
    except Exception:
        return None


traffic["node_degree"] = (
    traffic["osm_node"]
    .apply(get_node_degree)
)


# ============================================================
# FIND NEARBY ROAD EDGE
# ============================================================

print("Finding nearby road edges...")


def get_nearest_edge_info(node_id):

    try:

        edges = list(G.out_edges(
            node_id,
            keys=True,
            data=True
        ))

        if not edges:
            edges = list(G.in_edges(
                node_id,
                keys=True,
                data=True
            ))

        if not edges:
            return pd.Series(
                [None, None, None, None, None]
            )

        # Choose the longest connected edge
        # as a representative road segment.

        best_edge = max(
            edges,
            key=lambda x: float(
                x[3].get("length", 0)
            )
        )

        u, v, key, data = best_edge

        length = data.get("length")

        highway = data.get("highway")

        lanes = data.get("lanes")

        maxspeed = data.get("maxspeed")

        name = data.get("name")

        if isinstance(highway, list):
            highway = highway[0]

        if isinstance(lanes, list):
            lanes = lanes[0]

        if isinstance(maxspeed, list):
            maxspeed = maxspeed[0]

        if isinstance(name, list):
            name = name[0]

        return pd.Series([
            f"{u}_{v}_{key}",
            length,
            highway,
            lanes,
            maxspeed
        ])

    except Exception:
        return pd.Series(
            [None, None, None, None, None]
        )


edge_features = traffic["osm_node"].apply(
    get_nearest_edge_info
)

edge_features.columns = [
    "osm_edge_id",
    "road_length_m",
    "road_type",
    "lanes",
    "maxspeed"
]


traffic = pd.concat(
    [traffic, edge_features],
    axis=1
)


# ============================================================
# TARGET
# ============================================================

traffic["target_speed"] = pd.to_numeric(
    traffic["Average Speed"],
    errors="coerce"
)


# ============================================================
# CONVERT NUMERIC FEATURES
# ============================================================

numeric_columns = [
    "Traffic Volume",
    "Average Speed",
    "Travel Time Index",
    "Congestion Level",
    "Road Capacity Utilization",
    "Incident Reports",
    "Environmental Impact",
    "Public Transport Usage",
    "Traffic Signal Compliance",
    "Parking Usage",
    "Pedestrian and Cyclist Count",
    "Road Capacity Utilization",
    "target_speed",
    "road_length_m",
    "node_degree"
]


for column in numeric_columns:

    if column in traffic.columns:

        traffic[column] = pd.to_numeric(
            traffic[column],
            errors="coerce"
        )


# ============================================================
# SAVE
# ============================================================

traffic.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print("\n========================================")
print("TRAFFIC GNN DATASET CREATED")
print("========================================")

print(
    "Original traffic rows:",
    len(pd.read_csv(TRAFFIC_FILE))
)

print(
    "Mapped traffic rows:",
    len(traffic)
)

print(
    "Valid locations:",
    len(valid_mapping)
)

print(
    "Unique OSM nodes:",
    traffic["osm_node"].nunique()
)

print(
    "Unique OSM edges:",
    traffic["osm_edge_id"].nunique()
)

print(
    "\nOutput:",
    OUTPUT_FILE
)

print(
    "\nColumns:"
)

for column in traffic.columns:
    print("-", column)