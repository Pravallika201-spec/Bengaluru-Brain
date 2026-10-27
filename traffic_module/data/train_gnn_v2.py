import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from torch_geometric.data import Data
from torch_geometric.nn import GCNConv
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# ============================================================
# PATHS
# ============================================================

DATA_FILE = "gnn_training_data.csv"
MODEL_FILE = r"D:\major project\traffic_module\models\traffic_model_v2.pth"


# ============================================================
# LOAD DATA
# ============================================================

print("Loading training data...")

df = pd.read_csv(DATA_FILE)

print("Rows:", len(df))


# ============================================================
# DATE
# ============================================================

df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

# The prepared dataset currently does not contain Date,
# so recover it from the original traffic dataset.
if df["Date"].isna().all():

    original = pd.read_csv(
        "traffic_gnn_dataset.csv"
    )

    original["Date"] = pd.to_datetime(
        original["Date"],
        errors="coerce"
    )

    df["Date"] = original["Date"]


# ============================================================
# TARGET
# ============================================================

target = df["target_speed"].astype(float)


# ============================================================
# FEATURES
# ============================================================

feature_columns = [
    column
    for column in df.columns
    if column != "target_speed"
]

# IMPORTANT:
# Average Speed must NEVER be included.
if "Average Speed" in feature_columns:
    raise ValueError(
        "DATA LEAKAGE: Average Speed is present in input features."
    )


X = df[feature_columns].copy()


# ============================================================
# NUMERIC CONVERSION
# ============================================================

for column in X.columns:

    X[column] = pd.to_numeric(
        X[column],
        errors="coerce"
    )


X = X.fillna(X.median())


# ============================================================
# CHRONOLOGICAL SPLIT
# ============================================================

train_mask = df["Date"].dt.year == 2022
val_mask = df["Date"].dt.year == 2023
test_mask = df["Date"].dt.year == 2024


print("\nDataset split:")
print("Train:", train_mask.sum())
print("Validation:", val_mask.sum())
print("Test:", test_mask.sum())


# ============================================================
# STANDARDIZE FEATURES
# ============================================================

train_mean = X.loc[train_mask].mean()
train_std = X.loc[train_mask].std()

train_std = train_std.replace(0, 1)

X_scaled = (X - train_mean) / train_std


# ============================================================
# CREATE GRAPH
# ============================================================

# Each unique OSM edge becomes a graph node.
#
# We connect traffic observations belonging to the
# same physical road/location.
#
# For this first verified model, the 13 mapped locations
# form the traffic graph.

location_ids = df["osm_edge_id"].astype(str)

unique_locations = location_ids.unique()

location_to_index = {
    location: i
    for i, location in enumerate(unique_locations)
}


# ============================================================
# AGGREGATE OBSERVATIONS BY ROAD
# ============================================================

# Each graph node gets the mean feature vector for
# the corresponding road segment in each split.

def aggregate_split(mask):

    rows = []

    labels = []

    indices = []

    for location in unique_locations:

        location_mask = (
            mask &
            (location_ids == location)
        )

        if not location_mask.any():
            continue

        rows.append(
            X_scaled.loc[
                location_mask
            ].mean().values
        )

        labels.append(
            target.loc[
                location_mask
            ].mean()
        )

        indices.append(
            location_to_index[location]
        )

    return (
        np.asarray(rows, dtype=np.float32),
        np.asarray(labels, dtype=np.float32),
        indices
    )


X_train, y_train, train_nodes = aggregate_split(
    train_mask
)

X_val, y_val, val_nodes = aggregate_split(
    val_mask
)

X_test, y_test, test_nodes = aggregate_split(
    test_mask
)


# ============================================================
# GRAPH EDGES
# ============================================================

# Build graph connections using consecutive road
# locations as a simple validated spatial graph.

edge_pairs = []

for i in range(len(unique_locations) - 1):

    edge_pairs.append(
        [i, i + 1]
    )

    edge_pairs.append(
        [i + 1, i]
    )


edge_index = torch.tensor(
    edge_pairs,
    dtype=torch.long
).t().contiguous()


# ============================================================
# MODEL
# ============================================================

class TrafficGNN(nn.Module):

    def __init__(self, input_dim):

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

        return self.output(x).squeeze(-1)


# ============================================================
# DATA
# ============================================================

x_train = torch.tensor(
    X_train,
    dtype=torch.float32
)

y_train_tensor = torch.tensor(
    y_train,
    dtype=torch.float32
)

x_val = torch.tensor(
    X_val,
    dtype=torch.float32
)

y_val_tensor = torch.tensor(
    y_val,
    dtype=torch.float32
)

x_test = torch.tensor(
    X_test,
    dtype=torch.float32
)

y_test_tensor = torch.tensor(
    y_test,
    dtype=torch.float32
)


# ============================================================
# MODEL
# ============================================================

model = TrafficGNN(
    input_dim=x_train.shape[1]
)

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=0.005,
    weight_decay=1e-4
)

loss_function = nn.MSELoss()


# ============================================================
# TRAINING
# ============================================================

print("\nTraining GNN...")

best_val_loss = float("inf")

best_state = None


for epoch in range(1, 301):

    model.train()

    optimizer.zero_grad()

    predictions = model(
        x_train,
        edge_index
    )

    loss = loss_function(
        predictions,
        y_train_tensor
    )

    loss.backward()

    optimizer.step()


    # Validation

    model.eval()

    with torch.no_grad():

        val_predictions = model(
            x_val,
            edge_index
        )

        val_loss = loss_function(
            val_predictions,
            y_val_tensor
        )


    if val_loss.item() < best_val_loss:

        best_val_loss = val_loss.item()

        best_state = {
            key: value.cpu().clone()
            for key, value
            in model.state_dict().items()
        }


    if epoch % 25 == 0:

        print(
            f"Epoch {epoch:3d} | "
            f"Train Loss: {loss.item():.4f} | "
            f"Val Loss: {val_loss.item():.4f}"
        )


# ============================================================
# LOAD BEST MODEL
# ============================================================

model.load_state_dict(
    best_state
)

model.eval()


# ============================================================
# EVALUATION
# ============================================================

def evaluate(
    x,
    y,
    name
):

    with torch.no_grad():

        prediction = model(
            x,
            edge_index
        ).numpy()

    actual = y.numpy()

    mae = mean_absolute_error(
        actual,
        prediction
    )

    rmse = np.sqrt(
        mean_squared_error(
            actual,
            prediction
        )
    )

    r2 = r2_score(
        actual,
        prediction
    )

    print(
        f"\n{name}"
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

    return mae, rmse, r2


print("\n===================================")
print("MODEL EVALUATION")
print("===================================")

train_metrics = evaluate(
    x_train,
    y_train_tensor,
    "TRAIN"
)

val_metrics = evaluate(
    x_val,
    y_val_tensor,
    "VALIDATION"
)

test_metrics = evaluate(
    x_test,
    y_test_tensor,
    "TEST"
)


# ============================================================
# SAVE MODEL
# ============================================================

torch.save(
    {
        "model_state_dict": model.state_dict(),
        "input_dim": x_train.shape[1],
        "feature_columns": feature_columns,
        "train_mean": train_mean.to_dict(),
        "train_std": train_std.to_dict(),
    },
    MODEL_FILE
)

print(
    "\nSaved model:"
)

print(
    MODEL_FILE
)