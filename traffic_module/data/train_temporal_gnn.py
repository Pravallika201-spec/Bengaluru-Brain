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

SEQUENCE_FILE = r"D:\major project\traffic_module\data\traffic_sequence_dataset.csv"
GRAPH_FILE = r"D:\major project\traffic_module\data\local_gnn_graph.pt"
MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"
MODEL_FILE = r"D:\major project\traffic_module\models\temporal_gnn.pth"


# ============================================================
# SETTINGS
# ============================================================

HISTORY_DAYS = 7
EPOCHS = 100
BATCH_SIZE = 16
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4
PATIENCE = 12


# ============================================================
# DEVICE
# ============================================================

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print("Device:", device)


# ============================================================
# FEATURES
# ============================================================

FEATURES = [
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
]


SEQUENCE_COLUMNS = []

for day in range(1, HISTORY_DAYS + 1):

    for feature in FEATURES:

        SEQUENCE_COLUMNS.append(
            f"{feature}_d{day}"
        )


# ============================================================
# LOAD DATA
# ============================================================

print("\nLoading sequence dataset...")

df = pd.read_csv(SEQUENCE_FILE)

df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)

df["target_date"] = pd.to_datetime(
    df["target_date"],
    errors="coerce"
)

print("Sequence rows:", len(df))


# ============================================================
# LOAD GRAPH
# ============================================================

print("\nLoading local OSM graph...")

saved = torch.load(
    GRAPH_FILE,
    weights_only=False
)

graph = saved["data"]

print("Graph nodes:", graph.num_nodes)
print("Graph edges:", graph.edge_index.shape[1])
print("Graph features:", graph.num_node_features)


# ============================================================
# ROAD → OSM NODE MAPPING
# ============================================================

print("\nLoading road/OSM mapping...")

mapping = pd.read_csv(
    MAPPING_FILE,
    usecols=[
        "Road/Intersection Name",
        "osm_node"
    ]
)

mapping["osm_node"] = pd.to_numeric(
    mapping["osm_node"],
    errors="coerce"
)

mapping = mapping.dropna(
    subset=["osm_node"]
).copy()

mapping["osm_node"] = (
    mapping["osm_node"]
    .astype(int)
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


# ============================================================
# GRAPH NODE INDEX
# ============================================================

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

print(
    "Mapped sequences:",
    len(df)
)


# ============================================================
# NUMERIC CONVERSION
# ============================================================

for column in SEQUENCE_COLUMNS:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


df["target_speed_next_day"] = pd.to_numeric(
    df["target_speed_next_day"],
    errors="coerce"
)


df = df.dropna(
    subset=SEQUENCE_COLUMNS + [
        "target_speed_next_day"
    ]
).copy()


# ============================================================
# CHRONOLOGICAL SPLIT
# ============================================================

train_df = df[
    df["Date"].dt.year == 2022
].copy()

val_df = df[
    df["Date"].dt.year == 2023
].copy()

test_df = df[
    df["Date"].dt.year == 2024
].copy()


print(
    "\n========================================"
)

print(
    "CHRONOLOGICAL TEMPORAL SPLIT"
)

print(
    "========================================"
)

print(
    "Training 2022:",
    len(train_df)
)

print(
    "Validation 2023:",
    len(val_df)
)

print(
    "Testing 2024:",
    len(test_df)
)


# ============================================================
# NORMALIZATION
# ============================================================

train_median = (
    train_df[SEQUENCE_COLUMNS]
    .median()
)

for frame in [
    train_df,
    val_df,
    test_df
]:

    frame.loc[:, SEQUENCE_COLUMNS] = (
        frame[SEQUENCE_COLUMNS]
        .fillna(train_median)
    )


train_mean = (
    train_df[SEQUENCE_COLUMNS]
    .mean()
)

train_std = (
    train_df[SEQUENCE_COLUMNS]
    .std()
)

train_std = train_std.replace(
    0,
    1
)


def make_features(frame):

    values = (
        frame[SEQUENCE_COLUMNS]
        - train_mean
    ) / train_std

    return values.to_numpy(
        dtype=np.float32
    )


train_features = make_features(train_df)
val_features = make_features(val_df)
test_features = make_features(test_df)


# ============================================================
# GRAPH TENSORS
# ============================================================

base_graph_x = (
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

number_of_edges = (
    edge_index.shape[1]
)


# ============================================================
# MODEL
# ============================================================

class TemporalGNN(nn.Module):

    def __init__(self):

        super().__init__()

        self.temporal = nn.GRU(
            input_size=len(FEATURES),
            hidden_size=32,
            batch_first=True
        )

        self.conv1 = GCNConv(
            32,
            64
        )

        self.conv2 = GCNConv(
            64,
            32
        )

        self.conv3 = GCNConv(
            32,
            16
        )

        self.output = nn.Linear(
            16,
            1
        )


    def forward(
        self,
        x,
        edges
    ):

        # x shape:
        # [batch * nodes, 7, 13]

        temporal_output, _ = self.temporal(x)

        # Take representation of latest historical day

        x = temporal_output[:, -1, :]

        x = self.conv1(
            x,
            edges
        )

        x = F.relu(x)

        x = self.conv2(
            x,
            edges
        )

        x = F.relu(x)

        x = self.conv3(
            x,
            edges
        )

        x = F.relu(x)

        x = self.output(x)

        return x.squeeze(-1)


model = TemporalGNN().to(device)


# ============================================================
# OPTIMIZER
# ============================================================

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LEARNING_RATE,
    weight_decay=WEIGHT_DECAY
)

loss_function = nn.MSELoss()


# ============================================================
# CREATE BATCH
# ============================================================

def create_batch(
    feature_array,
    node_indices
):

    batch_size = len(node_indices)

    # [batch, 7, 13]

    daily_features = torch.tensor(
        feature_array,
        dtype=torch.float32,
        device=device
    )

    daily_features = daily_features.reshape(
        batch_size,
        HISTORY_DAYS,
        len(FEATURES)
    )

    # Create one temporal sequence for every
    # graph node.

    x = daily_features.unsqueeze(1).repeat(
        1,
        number_of_nodes,
        1,
        1
    )

    node_tensor = torch.tensor(
        node_indices,
        dtype=torch.long,
        device=device
    )

    batch_ids = torch.arange(
        batch_size,
        dtype=torch.long,
        device=device
    )

    # Only the selected road receives its
    # actual traffic sequence.

    x[
        batch_ids,
        node_tensor,
        :,
        :
    ] = daily_features

    # --------------------------------------------------------
    # Batched graph edges
    # --------------------------------------------------------

    offsets = (
        torch.arange(
            batch_size,
            dtype=torch.long,
            device=device
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

    # --------------------------------------------------------
    # Flatten only the graph/node dimension.
    #
    # IMPORTANT:
    # Keep [7, 13] intact for GRU.
    # --------------------------------------------------------

    x = x.reshape(
        batch_size * number_of_nodes,
        HISTORY_DAYS,
        len(FEATURES)
    )

    return (
        x,
        batched_edges,
        node_tensor
    )


# ============================================================
# PREDICTION
# ============================================================

def predict_dataset(
    frame,
    features
):

    model.eval()

    predictions = []

    actual = []

    with torch.no_grad():

        for start in range(
            0,
            len(frame),
            BATCH_SIZE
        ):

            end = min(
                start + BATCH_SIZE,
                len(frame)
            )

            feature_batch = (
                features[start:end]
            )

            node_batch = (
                frame.iloc[
                    start:end
                ]["graph_index"]
                .to_numpy(
                    dtype=np.int64
                )
            )

            x, edges, node_tensor = (
                create_batch(
                    feature_batch,
                    node_batch
                )
            )

            output = model(
                x,
                edges
            )

            batch_size = len(node_batch)

            batch_ids = torch.arange(
                batch_size,
                dtype=torch.long,
                device=device
            )

            target_indices = (
                batch_ids
                * number_of_nodes
                + node_tensor
            )

            prediction = (
                output[target_indices]
            )

            predictions.extend(
                prediction
                .cpu()
                .numpy()
                .tolist()
            )

            actual.extend(
                frame.iloc[
                    start:end
                ]["target_speed_next_day"]
                .to_numpy(
                    dtype=np.float32
                )
                .tolist()
            )

    return (
        np.asarray(
            predictions,
            dtype=np.float32
        ),
        np.asarray(
            actual,
            dtype=np.float32
        )
    )


# ============================================================
# TRAINING
# ============================================================

print(
    "\n========================================"
)

print(
    "TRAINING TEMPORAL GNN"
)

print(
    "========================================"
)


best_validation_mse = float("inf")

best_state = None

patience_counter = 0


for epoch in range(
    1,
    EPOCHS + 1
):

    model.train()

    permutation = np.random.permutation(
        len(train_df)
    )

    total_loss = 0.0

    batch_count = 0


    for start in range(
        0,
        len(train_df),
        BATCH_SIZE
    ):

        indices = permutation[
            start:start + BATCH_SIZE
        ]

        feature_batch = (
            train_features[indices]
        )

        node_batch = (
            train_df.iloc[
                indices
            ]["graph_index"]
            .to_numpy(
                dtype=np.int64
            )
        )

        target_batch = torch.tensor(
            train_df.iloc[
                indices
            ]["target_speed_next_day"]
            .to_numpy(
                dtype=np.float32
            ),
            dtype=torch.float32,
            device=device
        )

        x, edges, node_tensor = (
            create_batch(
                feature_batch,
                node_batch
            )
        )

        output = model(
            x,
            edges
        )

        batch_size = len(node_batch)

        batch_ids = torch.arange(
            batch_size,
            dtype=torch.long,
            device=device
        )

        target_indices = (
            batch_ids
            * number_of_nodes
            + node_tensor
        )

        prediction = (
            output[target_indices]
        )

        loss = loss_function(
            prediction,
            target_batch
        )

        optimizer.zero_grad()

        loss.backward()

        optimizer.step()

        total_loss += loss.item()

        batch_count += 1


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    validation_predictions, validation_actual = (
        predict_dataset(
            val_df,
            val_features
        )
    )

    validation_mse = mean_squared_error(
        validation_actual,
        validation_predictions
    )

    train_loss = (
        total_loss / batch_count
    )


    if validation_mse < best_validation_mse:

        best_validation_mse = (
            validation_mse
        )

        best_state = {
            key:
                value.detach()
                .cpu()
                .clone()

            for key, value
            in model.state_dict().items()
        }

        patience_counter = 0

    else:

        patience_counter += 1


    print(
        f"Epoch {epoch:3d} | "
        f"Train Loss: {train_loss:.4f} | "
        f"Validation MSE: {validation_mse:.4f}"
    )


    if patience_counter >= PATIENCE:

        print("\nEarly stopping.")

        print(
            "Best validation MSE:",
            f"{best_validation_mse:.4f}"
        )

        break


# ============================================================
# RESTORE BEST MODEL
# ============================================================

if best_state is not None:

    model.load_state_dict(
        best_state
    )


# ============================================================
# EVALUATION
# ============================================================

def evaluate(
    frame,
    features,
    name
):

    predictions, actual = (
        predict_dataset(
            frame,
            features
        )
    )

    mae = mean_absolute_error(
        actual,
        predictions
    )

    rmse = np.sqrt(
        mean_squared_error(
            actual,
            predictions
        )
    )

    r2 = r2_score(
        actual,
        predictions
    )

    print()
    print(name)

    print(
        f"MAE  : {mae:.3f} km/h"
    )

    print(
        f"RMSE : {rmse:.3f} km/h"
    )

    print(
        f"R²   : {r2:.3f}"
    )

    return (
        mae,
        rmse,
        r2
    )


# ============================================================
# FINAL EVALUATION
# ============================================================

print(
    "\n========================================"
)

print(
    "FINAL TEMPORAL GNN EVALUATION"
)

print(
    "========================================"
)


train_metrics = evaluate(
    train_df,
    train_features,
    "TRAIN — 2022"
)

validation_metrics = evaluate(
    val_df,
    val_features,
    "VALIDATION — 2023"
)

test_metrics = evaluate(
    test_df,
    test_features,
    "TEST — 2024"
)


# ============================================================
# SAVE MODEL
# ============================================================

os.makedirs(
    os.path.dirname(MODEL_FILE),
    exist_ok=True
)

torch.save(
    {
        "model_state_dict":
            model.state_dict(),

        "history_days":
            HISTORY_DAYS,

        "features":
            FEATURES,

        "feature_mean":
            train_mean.to_dict(),

        "feature_std":
            train_std.to_dict(),

        "osm_nodes":
            osm_nodes,

        "test_metrics":
            {
                "MAE":
                    test_metrics[0],

                "RMSE":
                    test_metrics[1],

                "R2":
                    test_metrics[2]
            }
    },
    MODEL_FILE
)


print(
    "\n========================================"
)

print(
    "TEMPORAL MODEL SAVED"
)

print(
    "========================================"
)

print(
    MODEL_FILE
)