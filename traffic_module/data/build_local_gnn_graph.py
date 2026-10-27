import pickle
import pandas as pd
import networkx as nx
import torch
from torch_geometric.data import Data


# ============================================================
# PATHS
# ============================================================

GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

DATASET_PATH = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

OUTPUT_PATH = r"D:\major project\traffic_module\data\local_gnn_graph.pt"


# ============================================================
# SETTINGS
# ============================================================

HOPS = 3


# ============================================================
# LOAD BENGALURU OSM GRAPH
# ============================================================

print("Loading Bengaluru OSM graph...")

with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

print("OSM nodes:", len(G.nodes))
print("OSM edges:", len(G.edges))


# ============================================================
# LOAD TRAFFIC DATASET
# ============================================================

print("\nLoading traffic dataset...")

df = pd.read_csv(DATASET_PATH)

df["osm_node"] = pd.to_numeric(
    df["osm_node"],
    errors="coerce"
)

df["target_speed"] = pd.to_numeric(
    df["target_speed"],
    errors="coerce"
)

df = df.dropna(
    subset=["osm_node"]
).copy()

df["osm_node"] = df["osm_node"].astype(int)


# ============================================================
# GET THE 13 MAPPED TRAFFIC LOCATIONS
# ============================================================

traffic_locations = (
    df.drop_duplicates("osm_node")
      .copy()
)

mapped_nodes = (
    traffic_locations["osm_node"]
    .tolist()
)

print(
    "\nMapped traffic locations:",
    len(mapped_nodes)
)


# ============================================================
# BUILD LOCAL OSM SUBGRAPH
# ============================================================

print(
    f"\nBuilding local OSM subgraphs using {HOPS} hops..."
)

local_nodes = set()

for node in mapped_nodes:

    if node not in G:
        continue

    nearby_nodes = nx.single_source_shortest_path_length(
        G,
        node,
        cutoff=HOPS
    )

    local_nodes.update(
        nearby_nodes.keys()
    )


print(
    "Local OSM nodes:",
    len(local_nodes)
)


# ============================================================
# CREATE LOCAL GRAPH
# ============================================================

local_graph = G.subgraph(
    local_nodes
).copy()

print(
    "Local OSM edges:",
    len(local_graph.edges)
)


# ============================================================
# CREATE NODE INDEX
# ============================================================

osm_nodes = list(
    local_graph.nodes
)

node_to_index = {
    node_id: index
    for index, node_id in enumerate(osm_nodes)
}


# ============================================================
# CREATE REAL OSM EDGES
# ============================================================

edge_pairs = set()

for u, v in local_graph.edges():

    if u in node_to_index and v in node_to_index:

        source = node_to_index[u]
        target = node_to_index[v]

        edge_pairs.add(
            (source, target)
        )

        # Reverse edge for message passing
        edge_pairs.add(
            (target, source)
        )


if len(edge_pairs) == 0:

    raise RuntimeError(
        "No OSM connections were created."
    )


edge_index = torch.tensor(
    list(edge_pairs),
    dtype=torch.long
).t().contiguous()


# ============================================================
# FEATURE DEFINITIONS
# ============================================================

# IMPORTANT:
# There are EXACTLY 12 features.
#
# These MUST match train_local_gnn.py.

FEATURE_COLUMNS = [
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
    "node_degree"
]


# ============================================================
# CREATE FEATURE MATRIX
# ============================================================

feature_rows = []

target_values = []

historical_observed = []


# ------------------------------------------------------------
# We use one representative traffic record for each
# mapped traffic node to initialize the graph.
# ------------------------------------------------------------

traffic_by_node = (
    traffic_locations
    .set_index("osm_node")
)


for node in osm_nodes:

    # --------------------------------------------------------
    # OSM INFORMATION
    # --------------------------------------------------------

    degree = local_graph.degree(
        node
    )

    road_length = 0.0

    outgoing_edges = list(
        local_graph.out_edges(
            node,
            data=True
        )
    )

    if outgoing_edges:

        lengths = []

        for _, _, edge_data in outgoing_edges:

            value = edge_data.get(
                "length"
            )

            if value is not None:

                try:
                    lengths.append(
                        float(value)
                    )
                except:
                    pass

        if lengths:

            road_length = (
                sum(lengths)
                / len(lengths)
            )


    # --------------------------------------------------------
    # HISTORICAL TRAFFIC INFORMATION
    # --------------------------------------------------------

    if node in traffic_by_node.index:

        row = traffic_by_node.loc[
            node
        ]

        traffic_volume = pd.to_numeric(
            row["Traffic Volume"],
            errors="coerce"
        )

        travel_time_index = pd.to_numeric(
            row["Travel Time Index"],
            errors="coerce"
        )

        congestion = pd.to_numeric(
            row["Congestion Level"],
            errors="coerce"
        )

        capacity = pd.to_numeric(
            row["Road Capacity Utilization"],
            errors="coerce"
        )

        incidents = pd.to_numeric(
            row["Incident Reports"],
            errors="coerce"
        )

        environmental = pd.to_numeric(
            row["Environmental Impact"],
            errors="coerce"
        )

        public_transport = pd.to_numeric(
            row["Public Transport Usage"],
            errors="coerce"
        )

        signal_compliance = pd.to_numeric(
            row["Traffic Signal Compliance"],
            errors="coerce"
        )

        parking = pd.to_numeric(
            row["Parking Usage"],
            errors="coerce"
        )

        pedestrian = pd.to_numeric(
            row["Pedestrian and Cyclist Count"],
            errors="coerce"
        )

        target_speed = pd.to_numeric(
            row["target_speed"],
            errors="coerce"
        )

        historical_observed.append(
            1
        )

    else:

        # ----------------------------------------------------
        # This is an ordinary OSM context node.
        #
        # We do NOT invent traffic values.
        # ----------------------------------------------------

        traffic_volume = 0.0
        travel_time_index = 0.0
        congestion = 0.0
        capacity = 0.0
        incidents = 0.0
        environmental = 0.0
        public_transport = 0.0
        signal_compliance = 0.0
        parking = 0.0
        pedestrian = 0.0

        target_speed = 0.0

        historical_observed.append(
            0
        )


    # --------------------------------------------------------
    # HANDLE MISSING VALUES
    # --------------------------------------------------------

    values = [
        traffic_volume,
        travel_time_index,
        congestion,
        capacity,
        incidents,
        environmental,
        public_transport,
        signal_compliance,
        parking,
        pedestrian,
        road_length,
        degree
    ]

    cleaned_values = []

    for value in values:

        try:

            if pd.isna(value):
                value = 0.0

            cleaned_values.append(
                float(value)
            )

        except:

            cleaned_values.append(
                0.0
            )


    # --------------------------------------------------------
    # ADD EXACTLY 12 FEATURES
    # --------------------------------------------------------

    feature_rows.append(
        cleaned_values
    )

    # Target
    try:

        if pd.isna(target_speed):
            target_speed = 0.0

        target_values.append(
            float(target_speed)
        )

    except:

        target_values.append(
            0.0
        )


# ============================================================
# VERIFY FEATURE COUNT
# ============================================================

feature_count = len(
    feature_rows[0]
)

print(
    "\nFeature count:",
    feature_count
)

if feature_count != 12:

    raise RuntimeError(
        f"Expected exactly 12 features, "
        f"but created {feature_count}."
    )


# ============================================================
# CREATE PYTORCH TENSORS
# ============================================================

x = torch.tensor(
    feature_rows,
    dtype=torch.float32
)

y = torch.tensor(
    target_values,
    dtype=torch.float32
)


# ============================================================
# HISTORICAL OBSERVATION MASK
# ============================================================

traffic_mask = torch.tensor(
    historical_observed,
    dtype=torch.bool
)


# ============================================================
# CREATE PYTORCH GEOMETRIC DATA
# ============================================================

data = Data(
    x=x,
    edge_index=edge_index,
    y=y
)

data.traffic_mask = traffic_mask

data.osm_nodes = torch.tensor(
    osm_nodes,
    dtype=torch.long
)


# ============================================================
# SAVE GRAPH
# ============================================================

torch.save(
    {
        "data": data,
        "hops": HOPS,
        "mapped_traffic_nodes": mapped_nodes,
        "feature_columns": FEATURE_COLUMNS
    },
    OUTPUT_PATH
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n========================================")
print("LOCAL GNN GRAPH CREATED")
print("========================================")

print(
    "Traffic observation nodes:",
    len(mapped_nodes)
)

print(
    "Local OSM nodes:",
    data.num_nodes
)

print(
    "Real OSM connections:",
    data.edge_index.shape[1]
)

print(
    "Nodes with historical traffic:",
    int(traffic_mask.sum())
)

print(
    "Features per node:",
    data.num_node_features
)

print(
    "\nFeature columns:"
)

for i, column in enumerate(
    FEATURE_COLUMNS,
    start=1
):

    print(
        f"{i}. {column}"
    )

print(
    "\nSaved to:"
)

print(
    OUTPUT_PATH
)