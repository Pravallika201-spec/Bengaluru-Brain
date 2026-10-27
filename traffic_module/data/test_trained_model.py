import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# PATHS
# ============================================================

GRAPH_FILE = r"D:\major project\traffic_module\data\local_gnn_graph.pt"

TRAFFIC_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

MODEL_FILE = r"D:\major project\traffic_module\models\traffic_model_v2.pth"


# ============================================================
# FEATURES
# ============================================================

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
    "node_degree",
]


# ============================================================
# MODEL
# ============================================================

class TrafficGNN(nn.Module):

    def __init__(self, input_dim):

        super().__init__()

        self.conv1 = GCNConv(input_dim, 64)
        self.conv2 = GCNConv(64, 32)
        self.conv3 = GCNConv(32, 16)

        self.output = nn.Linear(16, 1)

    def forward(self, x, edge_index):

        x = self.conv1(x, edge_index)
        x = F.relu(x)

        x = self.conv2(x, edge_index)
        x = F.relu(x)

        x = self.conv3(x, edge_index)
        x = F.relu(x)

        x = self.output(x)

        return x.squeeze(-1)


# ============================================================
# LOAD MODEL
# ============================================================

print("Loading trained model...")

checkpoint = torch.load(
    MODEL_FILE,
    weights_only=False
)

print("Model loaded successfully.")

print("\nSaved test metrics:")

print(
    checkpoint.get(
        "test_metrics",
        {}
    )
)


# ============================================================
# LOAD GRAPH
# ============================================================

print("\nLoading graph...")

saved_graph = torch.load(
    GRAPH_FILE,
    weights_only=False
)

graph = saved_graph["data"]

print(
    "Graph nodes:",
    graph.num_nodes
)

print(
    "Graph edges:",
    graph.edge_index.shape[1]
)


# ============================================================
# DEVICE
# ============================================================

device = torch.device("cpu")


# ============================================================
# CREATE MODEL
# ============================================================

model = TrafficGNN(
    len(FEATURE_COLUMNS)
).to(device)


model.load_state_dict(
    checkpoint["model_state_dict"]
)

model.eval()


# ============================================================
# LOAD DATA
# ============================================================

print("\nLoading traffic dataset...")

df = pd.read_csv(
    TRAFFIC_FILE
)


df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)


df["osm_node"] = pd.to_numeric(
    df["osm_node"],
    errors="coerce"
)


df["target_speed"] = pd.to_numeric(
    df["target_speed"],
    errors="coerce"
)


df = df.dropna(
    subset=[
        "Date",
        "osm_node",
        "target_speed"
    ]
).copy()


df["osm_node"] = (
    df["osm_node"]
    .astype(int)
)


# ============================================================
# CONVERT FEATURES
# ============================================================

for column in FEATURE_COLUMNS:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# ============================================================
# OSM NODE MAPPING
# ============================================================

osm_nodes = [
    int(x)
    for x in graph.osm_nodes.tolist()
]


osm_to_index = {
    node: index
    for index, node in enumerate(osm_nodes)
}


df = df[
    df["osm_node"].isin(
        osm_to_index
    )
].copy()


df["graph_index"] = (
    df["osm_node"]
    .map(osm_to_index)
    .astype(int)
)


# ============================================================
# TRAINING STATISTICS
# ============================================================

feature_mean = pd.Series(
    checkpoint["feature_mean"]
)

feature_std = pd.Series(
    checkpoint["feature_std"]
)


feature_std = feature_std.replace(
    0,
    1
)


# ============================================================
# USE 2024 TEST DATA
# ============================================================

test_df = df[
    df["Date"].dt.year == 2024
].copy()


print(
    "\n2024 observations:",
    len(test_df)
)


# ============================================================
# FILL MISSING VALUES
# ============================================================

test_df.loc[
    :,
    FEATURE_COLUMNS
] = (
    test_df[
        FEATURE_COLUMNS
    ]
    .fillna(feature_mean)
)


# ============================================================
# NORMALIZE
# ============================================================

features = (

    test_df[
        FEATURE_COLUMNS
    ]

    - feature_mean

) / feature_std


features = features.to_numpy(
    dtype=np.float32
)


# ============================================================
# GRAPH
# ============================================================

base_x = (
    graph.x
    .float()
    .to(device)
)


edge_index = (
    graph.edge_index
    .long()
    .to(device)
)


number_of_nodes = graph.num_nodes


number_of_edges = edge_index.shape[1]


# ============================================================
# PREDICT ONE OBSERVATION AT A TIME
# ============================================================

predictions = []


with torch.no_grad():

    for i in range(
        len(test_df)
    ):

        # Copy graph node features.

        x = base_x.clone()


        # Traffic node.

        node_index = int(
            test_df.iloc[i][
                "graph_index"
            ]
        )


        # Insert current observation.

        x[node_index] = torch.tensor(
            features[i],
            dtype=torch.float32,
            device=device
        )


        # GNN prediction.

        output = model(
            x,
            edge_index
        )


        predicted_speed = float(
            output[node_index]
            .cpu()
            .item()
        )


        predictions.append(
            predicted_speed
        )


# ============================================================
# RESULTS
# ============================================================

test_df["predicted_speed"] = (
    predictions
)


test_df["speed_error"] = (

    test_df["predicted_speed"]

    - test_df["target_speed"]

)


test_df["absolute_error"] = (

    test_df["speed_error"]
    .abs()

)


# ============================================================
# METRICS
# ============================================================

actual = test_df[
    "target_speed"
].to_numpy()


predicted = test_df[
    "predicted_speed"
].to_numpy()


mae = mean_absolute_error(
    actual,
    predicted
)


rmse = np.sqrt(
    mean_squared_error(
        actual,
        predicted
    )
)


r2 = r2_score(
    actual,
    predicted
)


print(
    "\n========================================"
)

print(
    "2024 PREDICTION TEST"
)

print(
    "========================================"
)

print(
    f"MAE  : {mae:.3f} km/h"
)

print(
    f"RMSE : {rmse:.3f} km/h"
)

print(
    f"R²   : {r2:.3f}"
)


# ============================================================
# SHOW SAMPLE PREDICTIONS
# ============================================================

print(
    "\n========================================"
)

print(
    "SAMPLE PREDICTIONS"
)

print(
    "========================================"
)


columns = [
    "Date",
    "Road/Intersection Name",
    "target_speed",
    "predicted_speed",
    "absolute_error"
]


print(
    test_df[
        columns
    ]
    .head(30)
    .to_string(
        index=False
    )
)


# ============================================================
# LOCATION SUMMARY
# ============================================================

print(
    "\n========================================"
)

print(
    "LOCATION SUMMARY"
)

print(
    "========================================"
)


location_summary = (

    test_df

    .groupby(
        "Road/Intersection Name"
    )

    .agg(

        actual_speed=(
            "target_speed",
            "mean"
        ),

        predicted_speed=(
            "predicted_speed",
            "mean"
        ),

        mae=(
            "absolute_error",
            "mean"
        ),

        observations=(
            "target_speed",
            "count"
        )

    )

    .sort_values(
        "mae"
    )

)


print(
    location_summary
    .round(2)
    .to_string()
)


# ============================================================
# SAVE PREDICTIONS
# ============================================================

OUTPUT_FILE = (
    r"D:\major project\traffic_module\data"
    r"\2024_gnn_predictions.csv"
)


test_df.to_csv(
    OUTPUT_FILE,
    index=False
)


print(
    "\nPredictions saved to:"
)

print(
    OUTPUT_FILE
)