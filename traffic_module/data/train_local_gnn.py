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

MODEL_FILE = r"D:\major project\traffic_module\models\traffic_model_v3.pth"


# ============================================================
# SETTINGS
# ============================================================

EPOCHS = 100

BATCH_SIZE = 32

LEARNING_RATE = 0.003

WEIGHT_DECAY = 1e-4

PATIENCE = 12


# ============================================================
# DEVICE
# ============================================================

device = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

print("Device:", device)


# ============================================================
# FEATURES
# ============================================================

BASE_FEATURES = [

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


TEMPORAL_FEATURES = [

    "hour",

    "day_of_week",

    "is_weekend",

    "month",

]


FEATURE_COLUMNS = (
    BASE_FEATURES
    + TEMPORAL_FEATURES
)


# ============================================================
# LOAD DATASET
# ============================================================

print("\nLoading traffic dataset...")

df = pd.read_csv(
    TRAFFIC_FILE
)


# ============================================================
# DATE
# ============================================================

df["Date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
)


# ============================================================
# BASIC NUMERIC COLUMNS
# ============================================================

df["osm_node"] = pd.to_numeric(
    df["osm_node"],
    errors="coerce"
)

df["target_speed"] = pd.to_numeric(
    df["target_speed"],
    errors="coerce"
)


# ============================================================
# REMOVE INVALID ROWS
# ============================================================

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


print(
    "Historical observations:",
    len(df)
)


# ============================================================
# CREATE TEMPORAL FEATURES
# ============================================================

print(
    "\nCreating temporal features..."
)


df["hour"] = (
    df["Date"]
    .dt.hour
)


df["day_of_week"] = (
    df["Date"]
    .dt.dayofweek
)


df["is_weekend"] = (
    df["day_of_week"] >= 5
).astype(float)


df["month"] = (
    df["Date"]
    .dt.month
)


print(
    "Temporal features:"
)

print(
    "- hour"
)

print(
    "- day_of_week"
)

print(
    "- is_weekend"
)

print(
    "- month"
)


# ============================================================
# CONVERT BASE FEATURES
# ============================================================

for column in BASE_FEATURES:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# ============================================================
# LOAD GRAPH
# ============================================================

print(
    "\nLoading local OSM graph..."
)


saved = torch.load(
    GRAPH_FILE,
    weights_only=False
)


graph = saved["data"]


print(
    "Graph nodes:",
    graph.num_nodes
)


print(
    "Graph connections:",
    graph.edge_index.shape[1]
)


print(
    "Graph features:",
    graph.num_node_features
)


# ============================================================
# GRAPH FEATURE CHECK
# ============================================================

if graph.num_node_features != 12:

    raise RuntimeError(
        "The existing graph must contain "
        "12 base node features."
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

    for index, node in enumerate(
        osm_nodes
    )

}


# ============================================================
# MAP OBSERVATIONS
# ============================================================

df = df[
    df["osm_node"].isin(
        osm_to_index
    )
].copy()


df["graph_index"] = (

    df["osm_node"]

    .map(
        osm_to_index
    )

    .astype(int)

)


print(
    "Observations mapped to graph:",
    len(df)
)


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
    "CHRONOLOGICAL SPLIT"
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
# HANDLE MISSING VALUES
# ============================================================

train_medians = (

    train_df[
        BASE_FEATURES
    ]

    .median()

)


train_df.loc[
    :,
    BASE_FEATURES
] = (

    train_df[
        BASE_FEATURES
    ]

    .fillna(
        train_medians
    )

)


val_df.loc[
    :,
    BASE_FEATURES
] = (

    val_df[
        BASE_FEATURES
    ]

    .fillna(
        train_medians
    )

)


test_df.loc[
    :,
    BASE_FEATURES
] = (

    test_df[
        BASE_FEATURES
    ]

    .fillna(
        train_medians
    )

)


# ============================================================
# FEATURE STATISTICS
# ============================================================

train_mean = (

    train_df[
        FEATURE_COLUMNS
    ]

    .mean()

)


train_std = (

    train_df[
        FEATURE_COLUMNS
    ]

    .std()

)


train_std = train_std.replace(
    0,
    1
)


# ============================================================
# FEATURE CREATION
# ============================================================

def make_features(
    frame
):

    values = (

        frame[
            FEATURE_COLUMNS
        ]

        - train_mean

    ) / train_std


    return values.to_numpy(
        dtype=np.float32
    )


train_features = make_features(
    train_df
)


val_features = make_features(
    val_df
)


test_features = make_features(
    test_df
)


# ============================================================
# GRAPH
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


number_of_nodes = (
    graph.num_nodes
)


number_of_edges = (
    edge_index.shape[1]
)


# ============================================================
# MODEL
# ============================================================

class TrafficGNN(
    nn.Module
):

    def __init__(
        self,
        input_dim
    ):

        super().__init__()


        self.conv1 = GCNConv(
            input_dim,
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


        x = self.output(
            x
        )


        return x.squeeze(
            -1
        )


# ============================================================
# CREATE MODEL
# ============================================================

model = TrafficGNN(
    len(FEATURE_COLUMNS)
).to(device)


print(
    "\nFeatures per observation:",
    len(FEATURE_COLUMNS)
)


print(
    "\nFeature columns:"
)


for i, column in enumerate(
    FEATURE_COLUMNS,
    1
):

    print(
        f"{i}. {column}"
    )


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

    batch_size = len(
        node_indices
    )


    # --------------------------------------------------------
    # Copy graph for every observation
    # --------------------------------------------------------

    x = (

        base_graph_x

        .unsqueeze(0)

        .expand(
            batch_size,
            -1,
            -1
        )

        .clone()

    )


    # --------------------------------------------------------
    # Observation features
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Insert traffic features
    # --------------------------------------------------------

    x[
        batch_ids,
        node_tensor
    ] = feature_tensor[:, :12]


    # --------------------------------------------------------
    # Temporal information
    #
    # Since the graph has 12 base node features,
    # temporal features are handled by concatenating
    # them to the traffic-node representation.
    # --------------------------------------------------------

    temporal_tensor = feature_tensor[:, 12:]


    # --------------------------------------------------------
    # Flatten graph
    # --------------------------------------------------------

    x = x.reshape(

        batch_size * number_of_nodes,

        12

    )


    # --------------------------------------------------------
    # Edge batching
    # --------------------------------------------------------

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


    return (

        x,

        batched_edges,

        node_tensor,

        temporal_tensor

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

                features[
                    start:end
                ]

            )


            node_batch = (

                frame.iloc[
                    start:end
                ][
                    "graph_index"
                ]

                .to_numpy(
                    dtype=np.int64
                )

            )


            x, edges, node_tensor, temporal = (

                create_batch(

                    feature_batch,

                    node_batch

                )

            )


            output = model(

                x,

                edges

            )


            batch_size = len(
                node_batch
            )


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

                output[
                    target_indices
                ]

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
                ][
                    "target_speed"
                ]

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
    "TRAINING GNN V3"
)

print(
    "========================================"
)


best_val_loss = float(
    "inf"
)


best_state = None


patience_counter = 0


# ============================================================
# TRAINING LOOP
# ============================================================

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


        indices = (

            permutation[
                start:
                start + BATCH_SIZE
            ]

        )


        feature_batch = (

            train_features[
                indices
            ]

        )


        node_batch = (

            train_df.iloc[
                indices
            ][
                "graph_index"
            ]

            .to_numpy(
                dtype=np.int64
            )

        )


        target_batch = torch.tensor(

            train_df.iloc[
                indices
            ][
                "target_speed"
            ]

            .to_numpy(
                dtype=np.float32
            ),

            dtype=torch.float32,

            device=device

        )


        x, edges, node_tensor, temporal = (

            create_batch(

                feature_batch,

                node_batch

            )

        )


        output = model(

            x,

            edges

        )


        batch_size = len(
            node_batch
        )


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

            output[
                target_indices
            ]

        )


        loss = loss_function(

            prediction,

            target_batch

        )


        optimizer.zero_grad()


        loss.backward()


        optimizer.step()


        total_loss += (
            loss.item()
        )


        batch_count += 1


    # ========================================================
    # VALIDATION
    # ========================================================

    validation_predictions, validation_actual = (

        predict_dataset(

            val_df,

            val_features

        )

    )


    validation_mse = (

        mean_squared_error(

            validation_actual,

            validation_predictions

        )

    )


    average_train_loss = (

        total_loss
        / batch_count

    )


    # ========================================================
    # BEST MODEL
    # ========================================================

    if validation_mse < best_val_loss:

        best_val_loss = validation_mse


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


    # ========================================================
    # PROGRESS
    # ========================================================

    print(

        f"Epoch {epoch:3d} | "

        f"Train Loss: "
        f"{average_train_loss:.4f} | "

        f"Validation MSE: "
        f"{validation_mse:.4f}"

    )


    # ========================================================
    # EARLY STOPPING
    # ========================================================

    if patience_counter >= PATIENCE:

        print()

        print(
            "Early stopping."
        )

        print(
            "Best validation MSE:",
            f"{best_val_loss:.4f}"
        )

        break


# ============================================================
# RESTORE BEST MODEL
# ============================================================

if best_state is not None:

    model.load_state_dict(
        best_state
    )


model.eval()


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

    print(
        name
    )


    print(

        f"MAE  : "
        f"{mae:.3f} km/h"

    )


    print(

        f"RMSE : "
        f"{rmse:.3f} km/h"

    )


    print(

        f"R²   : "
        f"{r2:.3f}"

    )


    return (

        mae,

        rmse,

        r2

    )


# ============================================================
# FINAL EVALUATION
# ============================================================

print()

print(
    "========================================"
)

print(
    "FINAL MODEL EVALUATION V3"
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

    os.path.dirname(
        MODEL_FILE
    ),

    exist_ok=True

)


torch.save(

    {

        "model_state_dict":
            model.state_dict(),

        "input_dim":
            len(FEATURE_COLUMNS),

        "feature_columns":
            FEATURE_COLUMNS,

        "base_features":
            BASE_FEATURES,

        "temporal_features":
            TEMPORAL_FEATURES,

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


print()

print(
    "========================================"
)

print(
    "MODEL SAVED"
)

print(
    "========================================"
)

print(
    MODEL_FILE
)