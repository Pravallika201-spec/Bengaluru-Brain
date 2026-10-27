import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from torch_geometric.nn import GCNConv


# ============================================================
# PATHS
# ============================================================

DATA_FILE = r"D:\major project\traffic_module\data\traffic_forecast_dataset.csv"

GRAPH_FILE = r"D:\major project\traffic_module\data\local_gnn_graph.pt"

MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

MODEL_FILE = r"D:\major project\traffic_module\models\traffic_forecast_gnn.pth"

OUTPUT_FILE = r"D:\major project\traffic_module\data\forecast_predictions_2024.csv"


# ============================================================
# SETTINGS
# ============================================================

BATCH_SIZE = 32


# ============================================================
# DEVICE
# ============================================================

device = torch.device("cpu")

print("Device:", device)


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [
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
    "road_length_m",
    "node_degree",
    "day_of_week",
    "is_weekend",
    "month",
]


# ============================================================
# MODEL
# ============================================================

class ForecastGNN(nn.Module):

    def __init__(self):

        super().__init__()

        self.conv1 = GCNConv(16, 64)

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

print("\nLoading trained forecast model...")

checkpoint = torch.load(
    MODEL_FILE,
    map_location=device,
    weights_only=False
)

model = ForecastGNN().to(device)

model.load_state_dict(
    checkpoint["model_state_dict"]
)

model.eval()

print("Model loaded successfully.")


# ============================================================
# LOAD DATA
# ============================================================

print("\nLoading forecasting dataset...")

df = pd.read_csv(DATA_FILE)

df["Date"] = pd.to_datetime(df["Date"])

df["target_date"] = pd.to_datetime(
    df["target_date"]
)

df["day_of_week"] = (
    df["Date"].dt.dayofweek.astype(float)
)

df["is_weekend"] = (
    df["day_of_week"] >= 5
).astype(float)

df["month"] = (
    df["Date"].dt.month.astype(float)
)


# ============================================================
# LOAD GRAPH
# ============================================================

print("\nLoading graph...")

saved = torch.load(
    GRAPH_FILE,
    weights_only=False
)

graph = saved["data"]

base_graph_x = (
    graph.x
    .float()
)

edge_index = (
    graph.edge_index
    .long()
)

number_of_nodes = graph.num_nodes

number_of_edges = (
    edge_index.shape[1]
)


# ============================================================
# OSM MAPPING
# ============================================================

print("\nLoading road mapping...")

mapping = pd.read_csv(
    MAPPING_FILE,
    usecols=[
        "Road/Intersection Name",
        "osm_node"
    ]
)

mapping = mapping.drop_duplicates(
    "Road/Intersection Name"
)

mapping = mapping.rename(
    columns={
        "osm_node": "mapped_osm_node"
    }
)

df = df.merge(
    mapping,
    on="Road/Intersection Name",
    how="inner"
)


osm_nodes = [
    int(x)
    for x in graph.osm_nodes.tolist()
]

osm_to_index = {
    node: index
    for index, node in enumerate(osm_nodes)
}


df["graph_index"] = (
    df["mapped_osm_node"]
    .map(osm_to_index)
)


df = df.dropna(
    subset=["graph_index"]
).copy()

df["graph_index"] = (
    df["graph_index"]
    .astype(int)
)


# ============================================================
# NUMERIC CONVERSION
# ============================================================

for column in FEATURE_COLUMNS:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# ============================================================
# TRAINING STATISTICS
# ============================================================

train_df = df[
    df["Date"].dt.year == 2022
].copy()

train_median = (
    train_df[FEATURE_COLUMNS]
    .median()
)

train_mean = pd.Series(
    checkpoint["feature_mean"]
)

train_std = pd.Series(
    checkpoint["feature_std"]
)

train_std = train_std.replace(
    0,
    1
)


# ============================================================
# 2024 TEST DATA
# ============================================================

test_df = df[
    df["Date"].dt.year == 2024
].copy()

test_df = test_df.dropna(
    subset=["target_speed_next_day"]
).copy()

test_df.loc[:, FEATURE_COLUMNS] = (
    test_df[FEATURE_COLUMNS]
    .fillna(train_median)
)


# ============================================================
# NORMALIZE
# ============================================================

features = (
    (
        test_df[FEATURE_COLUMNS]
        - train_mean
    )
    / train_std
).to_numpy(
    dtype=np.float32
)


# ============================================================
# PREDICT
# ============================================================

print(
    "\n========================================"
)

print(
    "2024 FORECAST PREDICTIONS"
)

print(
    "========================================"
)


predictions = []


with torch.no_grad():

    for start in range(
        0,
        len(test_df),
        BATCH_SIZE
    ):

        end = min(
            start + BATCH_SIZE,
            len(test_df)
        )

        batch_features = torch.tensor(
            features[start:end],
            dtype=torch.float32
        )

        node_indices = torch.tensor(
            test_df.iloc[
                start:end
            ]["graph_index"].to_numpy(),
            dtype=torch.long
        )

        batch_size = len(
            node_indices
        )

        x = torch.zeros(
            (
                batch_size,
                number_of_nodes,
                16
            ),
            dtype=torch.float32
        )

        x[:, :, :12] = (
            base_graph_x
            .unsqueeze(0)
            .expand(
                batch_size,
                -1,
                -1
            )
        )

        batch_ids = torch.arange(
            batch_size
        )

        x[
            batch_ids,
            node_indices,
            :12
        ] = batch_features[:, :12]

        x[
            batch_ids,
            node_indices,
            12:16
        ] = batch_features[:, 12:16]

        offsets = (
            torch.arange(
                batch_size
            )
            * number_of_nodes
        )

        batched_edges = (
            edge_index
            .unsqueeze(1)
            + offsets.view(
                1,
                batch_size,
                1
            )
        )

        batched_edges = (
            batched_edges
            .reshape(
                2,
                batch_size * number_of_edges
            )
        )

        x = x.reshape(
            batch_size * number_of_nodes,
            16
        )

        output = model(
            x,
            batched_edges
        )

        target_indices = (
            batch_ids
            * number_of_nodes
            + node_indices
        )

        batch_predictions = (
            output[target_indices]
            .numpy()
        )

        predictions.extend(
            batch_predictions.tolist()
        )


# ============================================================
# ADD PREDICTIONS
# ============================================================

test_df["predicted_next_day_speed"] = (
    predictions
)

test_df["absolute_error"] = (
    np.abs(
        test_df["target_speed_next_day"]
        - test_df["predicted_next_day_speed"]
    )
)


# ============================================================
# DISPLAY
# ============================================================

print(
    "\nSample predictions:"
)

print(
    test_df[
        [
            "Date",
            "target_date",
            "Road/Intersection Name",
            "Average Speed",
            "target_speed_next_day",
            "predicted_next_day_speed",
            "absolute_error"
        ]
    ]
    .head(30)
    .to_string(index=False)
)


# ============================================================
# SUMMARY
# ============================================================

print(
    "\n========================================"
)

print(
    "FORECAST SUMMARY"
)

print(
    "========================================"
)

print(
    "Observations:",
    len(test_df)
)

print(
    "Actual mean speed:",
    round(
        test_df["target_speed_next_day"].mean(),
        2
    ),
    "km/h"
)

print(
    "Predicted mean speed:",
    round(
        test_df["predicted_next_day_speed"].mean(),
        2
    ),
    "km/h"
)

print(
    "Mean absolute error:",
    round(
        test_df["absolute_error"].mean(),
        2
    ),
    "km/h"
)


# ============================================================
# SAVE
# ============================================================

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