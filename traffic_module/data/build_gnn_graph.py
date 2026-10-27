import pickle
import pandas as pd
import torch
from torch_geometric.data import Data


# ============================================================
# PATHS
# ============================================================

GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

DATASET_PATH = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

OUTPUT_PATH = r"D:\major project\traffic_module\data\gnn_graph_data.pt"


# ============================================================
# LOAD OSM GRAPH
# ============================================================

print("Loading Bengaluru OSM graph...")

with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

print("OSM nodes:", len(G.nodes))
print("OSM edges:", len(G.edges))


# ============================================================
# LOAD TRAFFIC DATA
# ============================================================

print("\nLoading traffic dataset...")

df = pd.read_csv(DATASET_PATH)

# One representative traffic record per mapped OSM node
traffic_nodes = (
    df.drop_duplicates("osm_node")
      .copy()
)

traffic_nodes["osm_node"] = (
    traffic_nodes["osm_node"]
    .astype(int)
)

print(
    "Mapped traffic nodes:",
    len(traffic_nodes)
)


# ============================================================
# CREATE NODE INDEX
# ============================================================

traffic_osm_nodes = (
    traffic_nodes["osm_node"]
    .tolist()
)

node_to_index = {
    node_id: index
    for index, node_id
    in enumerate(traffic_osm_nodes)
}


# ============================================================
# CREATE FEATURES
# ============================================================

feature_columns = [
    "Traffic Volume",
    "Travel Time Index",
    "Congestion Level",
    "Road Capacity Utilization",
    "Incident Reports",
    "Environmental Impact",
    "Public Transport Usage",
    "Traffic Signal Compliance",
    "Parking Usage",
    "Pedestrian and Cyclist Count",
    "road_length_m",
    "node_degree",
]


features = traffic_nodes[
    feature_columns
].copy()


# Convert everything to numeric
features = features.apply(
    pd.to_numeric,
    errors="coerce"
)


# Fill missing values using column median
features = features.fillna(
    features.median()
)


# ============================================================
# TARGET
# ============================================================

target = pd.to_numeric(
    traffic_nodes["target_speed"],
    errors="coerce"
)

target = target.fillna(
    target.median()
)


# ============================================================
# STANDARDIZE FEATURES
# ============================================================

mean = features.mean()
std = features.std()

std = std.replace(0, 1)

features = (
    features - mean
) / std


# ============================================================
# CREATE REAL OSM CONNECTIONS
# ============================================================

print("\nBuilding OSM-based graph connections...")

edge_pairs = set()

for osm_node in traffic_osm_nodes:

    if osm_node not in G:
        continue

    # Outgoing OSM road connections
    for neighbor in G.successors(osm_node):

        if neighbor in node_to_index:

            source = node_to_index[osm_node]
            target_node = node_to_index[neighbor]

            edge_pairs.add(
                (source, target_node)
            )

            # Add reverse connection so the GNN can
            # exchange information in both directions.
            edge_pairs.add(
                (target_node, source)
            )


# ============================================================
# CONVERT EDGE INDEX
# ============================================================

if edge_pairs:

    edge_index = torch.tensor(
        list(edge_pairs),
        dtype=torch.long
    ).t().contiguous()

else:

    print(
        "\nWARNING: No direct connections found "
        "between the 13 mapped traffic nodes."
    )

    edge_index = torch.empty(
        (2, 0),
        dtype=torch.long
    )


# ============================================================
# CREATE PYTORCH GEOMETRIC DATA
# ============================================================

x = torch.tensor(
    features.values,
    dtype=torch.float32
)

y = torch.tensor(
    target.values,
    dtype=torch.float32
)


data = Data(
    x=x,
    edge_index=edge_index,
    y=y
)


# ============================================================
# ADD METADATA
# ============================================================

data.osm_nodes = torch.tensor(
    traffic_osm_nodes,
    dtype=torch.long
)


# ============================================================
# SAVE
# ============================================================

torch.save(
    {
        "data": data,
        "feature_columns": feature_columns,
        "traffic_osm_nodes": traffic_osm_nodes,
        "feature_mean": mean.to_dict(),
        "feature_std": std.to_dict(),
    },
    OUTPUT_PATH
)


# ============================================================
# SUMMARY
# ============================================================

print("\n========================================")
print("GNN GRAPH CREATED")
print("========================================")

print(
    "Traffic graph nodes:",
    data.num_nodes
)

print(
    "GNN features per node:",
    data.num_node_features
)

print(
    "Real OSM graph connections:",
    data.edge_index.shape[1]
)

print(
    "Target:",
    "Average Speed / target_speed"
)

print(
    "\nSaved to:"
)

print(OUTPUT_PATH)