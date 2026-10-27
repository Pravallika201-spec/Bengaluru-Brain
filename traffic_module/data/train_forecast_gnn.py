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

DATA_FILE = r"D:\major project\traffic_module\data\traffic_forecast_dataset.csv"
GRAPH_FILE = r"D:\major project\traffic_module\data\local_gnn_graph.pt"
MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"
MODEL_FILE = r"D:\major project\traffic_module\models\traffic_forecast_gnn.pth"


# ============================================================
# SETTINGS
# ============================================================

EPOCHS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.002
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
# LOAD FORECAST DATA
# ============================================================

print("\nLoading forecasting dataset...")

df = pd.read_csv(DATA_FILE)

print("Forecast rows:", len(df))


# ============================================================
# DATES
# ============================================================

df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)

df["target_date"] = pd.to_datetime(
    df["target_date"],
    errors="coerce"
)


# ============================================================
# CALENDAR FEATURES
# ============================================================

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
# NUMERIC FEATURES
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
    "road_length_m",
    "node_degree",
    "target_speed_next_day",
]


for column in numeric_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


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
# GET OSM NODE LIST
# ============================================================

osm_nodes = [
    int(x)
    for x in graph.osm_nodes.tolist()
]

osm_to_index = {
    node: index
    for index, node in enumerate(osm_nodes)
}


# ============================================================
# LOAD ROAD MAPPING
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
    mapping["osm_node"].astype(int)
)

mapping = mapping.drop_duplicates(
    "Road/Intersection Name"
)


# ============================================================
# CREATE CLEAN GRAPH NODE COLUMN
# ============================================================

mapping = mapping.rename(
    columns={
        "osm_node": "mapped_osm_node"
    }
)


# ============================================================
# MERGE ON ROAD NAME
# ============================================================

df = df.merge(
    mapping,
    on="Road/Intersection Name",
    how="inner"
)


print(
    "After OSM mapping:",
    len(df)
)


# ============================================================
# MAP TO LOCAL GRAPH INDEX
# ============================================================

df["graph_index"] = (
    df["mapped_osm_node"]
    .map(osm_to_index)
)


# Keep only nodes that exist in local graph

df = df.dropna(
    subset=["graph_index"]
).copy()


df["graph_index"] = (
    df["graph_index"]
    .astype(int)
)


print(
    "Mapped forecasting observations:",
    len(df)
)

print(
    "Mapped locations:",
    df["Road/Intersection Name"].nunique()
)


# ============================================================
# REMOVE INVALID DATA
# ============================================================

df = df.dropna(
    subset=[
        "Date",
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
    "CHRONOLOGICAL FORECAST SPLIT"
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
# MISSING VALUES
# ============================================================

train_medians = (
    train_df[FEATURE_COLUMNS]
    .median()
)


for frame in [
    train_df,
    val_df,
    test_df
]:

    frame.loc[:, FEATURE_COLUMNS] = (
        frame[FEATURE_COLUMNS]
        .fillna(train_medians)
    )


# ============================================================
# NORMALIZATION
# ============================================================

train_mean = (
    train_df[FEATURE_COLUMNS]
    .mean()
)

train_std = (
    train_df[FEATURE_COLUMNS]
    .std()
)

train_std = train_std.replace(
    0,
    1
)


def make_features(frame):

    values = (
        frame[FEATURE_COLUMNS]
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
number_of_edges = edge_index.shape[1]


# ============================================================
# MODEL
# ============================================================

class ForecastGNN(nn.Module):

    def __init__(self):

        super().__init__()

        self.conv1 = GCNConv(
            16,
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
        edge_index
    ):

        x = self.conv1(
            x,
            edge_index
        )

        x = F.relu(x)

        x = self.conv2(
            x,
            edge_index
        )

        x = F.relu(x)

        x = self.conv3(
            x,
            edge_index
        )

        x = F.relu(x)

        x = self.output(x)

        return x.squeeze(-1)


model = ForecastGNN().to(device)


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

    x = torch.zeros(
        (
            batch_size,
            number_of_nodes,
            16
        ),
        dtype=torch.float32,
        device=device
    )

    # Existing 12 graph features
    x[:, :, :12] = (
        base_graph_x
        .unsqueeze(0)
        .expand(
            batch_size,
            -1,
            -1
        )
    )

    feature_tensor = torch.tensor(
        feature_array,
        dtype=torch.float32,
        device=device
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

    # First 13 forecasting features
    # replace observed node representation.
    #
    # Graph itself has 12 dimensions.
    # We put the first 12 traffic/road features
    # into graph dimensions 0:12.
    x[
        batch_ids,
        node_tensor,
        :12
    ] = feature_tensor[:, :12]

    # Four remaining forecasting features:
    # node_degree + calendar features
    #
    # node_degree is already represented by the graph,
    # so dimensions 12-15 contain:
    #
    # node_degree
    # day_of_week
    # is_weekend
    # month

    x[
        batch_ids,
        node_tensor,
        12:16
    ] = feature_tensor[:, 12:16]

    # Batched edges
    offsets = (
        torch.arange(
            batch_size,
            dtype=torch.long,
            device=device
        )
        * number_of_nodes
    )

    offsets = offsets.view(
        1,
        batch_size,
        1
    )

    batched_edges = (
        edge_index
        .unsqueeze(1)
        + offsets
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
# TRAIN
# ============================================================

print(
    "\n========================================"
)

print(
    "TRAINING FORECAST GNN"
)

print(
    "========================================"
)


best_val_loss = float("inf")
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


    # Validation
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


    if validation_mse < best_val_loss:

        best_val_loss = validation_mse

        best_state = {
            key: value.detach()
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

        print()
        print("Early stopping.")
        print(
            "Best validation MSE:",
            f"{best_val_loss:.4f}"
        )

        break


# ============================================================
# RESTORE BEST
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

    return mae, rmse, r2


# ============================================================
# FINAL EVALUATION
# ============================================================

print()
print(
    "========================================"
)

print(
    "FINAL FORECAST MODEL EVALUATION"
)

print(
    "========================================"
)


train_metrics = evaluate(
    train_df,
    train_features,
    "TRAIN — 2022"
)

val_metrics = evaluate(
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

        "input_dim":
            16,

        "feature_columns":
            FEATURE_COLUMNS,

        "feature_mean":
            train_mean.to_dict(),

        "feature_std":
            train_std.to_dict(),

        "osm_nodes":
            osm_nodes,

        "test_metrics":
            {
                "MAE": test_metrics[0],
                "RMSE": test_metrics[1],
                "R2": test_metrics[2]
            }
    },
    MODEL_FILE
)


print()
print(
    "========================================"
)

print(
    "FORECAST MODEL SAVED"
)

print(
    "========================================"
)

print(
    MODEL_FILE
)