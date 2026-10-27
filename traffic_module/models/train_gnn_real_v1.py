"""
Retrains the Bengaluru traffic-speed GNN on REAL TomTom/OSM data (see
prepare_real_traffic_dataset.py for provenance), replacing the old checkpoint
that was trained on a synthetic-looking dataset and scored R^2=0.09.

Architecture: 3-layer GCNConv produces a real-OSM-graph-aware embedding for
every node in the 1-hop subgraph around the labeled edges (so message
passing has genuine structural context, not isolated points). An edge
regressor then predicts current_speed_kmh for a given (u, v) edge from
[node_emb[u], node_emb[v], edge_scalar_features].

Two INDEPENDENT, clearly-separated evaluations (never averaged together,
per the project's "never fabricate accuracy" rule):
  - SPATIAL test: random held-out edges from the two single-snapshot files,
    PLUS the 21 edges that only exist in bengaluru_traffic_segments.csv
    (never seen in training at all) -> tests generalization to unseen roads.
  - TEMPORAL test: last ~20% of timestamps (per segment) from the 13
    repeatedly-polled live segments -> tests generalization across time for
    roads the model DOES know about. n=13 segments only; explicitly flagged
    as a small-sample, exploratory metric, not a strong claim.

Run: python traffic_module/models/train_gnn_real_v1.py
"""
import os
import json
import math
import random
from datetime import datetime

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.nn import GCNConv

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_PATH = os.path.join(HERE, "real_traffic_labels.json")
SUB_NODES_PATH = os.path.join(HERE, "real_subgraph_nodes.csv")
SUB_EDGES_PATH = os.path.join(HERE, "real_subgraph_edges.csv")
CHECKPOINT_OUT = os.path.join(HERE, "traffic_model_real_v1.pth")

FRC_CATS = ["FRC0", "FRC1", "FRC2", "FRC3", "FRC4", "FRC5", "FRC6", "FRC7", "UNKNOWN"]


def frc_onehot(frc):
    v = [0.0] * len(FRC_CATS)
    idx = FRC_CATS.index(frc) if frc in FRC_CATS else FRC_CATS.index("UNKNOWN")
    v[idx] = 1.0
    return v


def parse_hour_features(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
    except ValueError:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    hour = dt.hour + dt.minute / 60.0
    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)
    is_weekend = 1.0 if dt.weekday() >= 5 else 0.0
    return hour_sin, hour_cos, is_weekend


def main():
    with open(LABELS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    sub_nodes = pd.read_csv(SUB_NODES_PATH)
    sub_edges = pd.read_csv(SUB_EDGES_PATH)

    node_ids = sub_nodes["node_id"].astype(np.int64).tolist()
    node_index = {nid: i for i, nid in enumerate(node_ids)}
    n_nodes = len(node_ids)

    # ---------------- graph tensors (real OSM structure) ----------------
    src = sub_edges["source"].astype(np.int64).map(node_index).values
    dst = sub_edges["target"].astype(np.int64).map(node_index).values
    edge_index = torch.tensor(
        np.concatenate([np.stack([src, dst]), np.stack([dst, src])], axis=1),
        dtype=torch.long,
    )  # undirected for message passing

    # ---------------- real node input features ----------------
    degree = np.zeros(n_nodes, dtype=np.float64)
    maxspeed_sum = np.zeros(n_nodes, dtype=np.float64)
    maxspeed_cnt = np.zeros(n_nodes, dtype=np.float64)
    length_sum = np.zeros(n_nodes, dtype=np.float64)

    def parse_maxspeed(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    for row in sub_edges.itertuples(index=False):
        ui, vi = node_index[int(row.source)], node_index[int(row.target)]
        degree[ui] += 1
        degree[vi] += 1
        length_sum[ui] += row.length
        length_sum[vi] += row.length
        ms = parse_maxspeed(row.maxspeed)
        if ms is not None:
            maxspeed_sum[ui] += ms
            maxspeed_cnt[ui] += 1
            maxspeed_sum[vi] += ms
            maxspeed_cnt[vi] += 1

    mean_maxspeed_global = float(np.nan_to_num(maxspeed_sum / np.maximum(maxspeed_cnt, 1)).mean())
    avg_maxspeed = np.where(maxspeed_cnt > 0, maxspeed_sum / np.maximum(maxspeed_cnt, 1), mean_maxspeed_global)
    avg_length = length_sum / np.maximum(degree, 1)

    node_feat_raw = np.stack([degree, avg_maxspeed, avg_length], axis=1)  # [n_nodes, 3]
    node_feat_mean = node_feat_raw.mean(axis=0)
    node_feat_std = node_feat_raw.std(axis=0) + 1e-6
    node_feat = (node_feat_raw - node_feat_mean) / node_feat_std
    node_feat_t = torch.tensor(node_feat, dtype=torch.float32)

    # ---------------- assemble labeled edge samples ----------------
    samples = []  # each: dict(u_idx, v_idx, edge_scalar[len,basekph,hsin,hcos,wknd]+frc_onehot, target, split_group)

    for key, row in payload["snapshot_labeled"].items():
        u, v = row["u"], row["v"]
        if u not in node_index or v not in node_index:
            continue
        hsin, hcos, wknd = parse_hour_features(row["timestamp"])
        scalar = [row["edge_length_m"], row["base_speed_kph"], hsin, hcos, wknd] + frc_onehot(row["frc"])
        samples.append({
            "u": node_index[u], "v": node_index[v],
            "scalar": scalar, "target": row["current_speed_kmh"],
            "group": "spatial_holdout" if row["spatial_holdout"] else "spatial_pool",
        })

    for key, ts_list in payload["live_timeseries"].items():
        u_raw, v_raw = key.split("_")
        u, v = int(u_raw), int(v_raw)
        if u not in node_index or v not in node_index:
            continue
        static = payload["live_static"][key]
        ts_sorted = sorted(ts_list, key=lambda r: r["timestamp"])
        cutoff = max(1, int(len(ts_sorted) * 0.8))
        for i, row in enumerate(ts_sorted):
            hsin, hcos, wknd = parse_hour_features(row["timestamp"])
            scalar = [static["edge_length_m"], static["base_speed_kph"], hsin, hcos, wknd] + frc_onehot(static["frc"])
            samples.append({
                "u": node_index[u], "v": node_index[v],
                "scalar": scalar, "target": row["current_speed_kmh"],
                "group": "temporal_train" if i < cutoff else "temporal_test",
            })

    print(f"[data] {len(samples)} labeled edge-samples total")
    for g in ["spatial_pool", "spatial_holdout", "temporal_train", "temporal_test"]:
        print(f"  {g}: {sum(1 for s in samples if s['group'] == g)}")

    # ---------------- spatial train/val/test split (random, seeded) ----------------
    spatial_pool = [s for i, s in enumerate(samples) if s["group"] == "spatial_pool"]
    random.Random(SEED).shuffle(spatial_pool)
    n = len(spatial_pool)
    n_val = max(1, int(n * 0.15))
    n_test = max(1, int(n * 0.15))
    spatial_val = spatial_pool[:n_val]
    spatial_test = spatial_pool[n_val:n_val + n_test]
    spatial_train = spatial_pool[n_val + n_test:]

    train_samples = spatial_train + [s for s in samples if s["group"] == "temporal_train"]
    spatial_test_full = spatial_test + [s for s in samples if s["group"] == "spatial_holdout"]
    temporal_test = [s for s in samples if s["group"] == "temporal_test"]

    print(f"[split] train={len(train_samples)} val={len(spatial_val)} "
          f"spatial_test={len(spatial_test_full)} temporal_test={len(temporal_test)}")

    scalar_dim = len(train_samples[0]["scalar"])
    scalar_arr = np.array([s["scalar"] for s in train_samples], dtype=np.float64)
    scalar_mean = scalar_arr.mean(axis=0)
    scalar_std = scalar_arr.std(axis=0) + 1e-6

    def to_tensors(sample_list):
        u_idx = torch.tensor([s["u"] for s in sample_list], dtype=torch.long)
        v_idx = torch.tensor([s["v"] for s in sample_list], dtype=torch.long)
        scalars = np.array([s["scalar"] for s in sample_list], dtype=np.float64)
        scalars_norm = (scalars - scalar_mean) / scalar_std
        scalars_t = torch.tensor(scalars_norm, dtype=torch.float32)
        target = torch.tensor([s["target"] for s in sample_list], dtype=torch.float32)
        return u_idx, v_idx, scalars_t, target

    train_u, train_v, train_s, train_y = to_tensors(train_samples)
    val_u, val_v, val_s, val_y = to_tensors(spatial_val)
    stest_u, stest_v, stest_s, stest_y = to_tensors(spatial_test_full)
    ttest_u, ttest_v, ttest_s, ttest_y = to_tensors(temporal_test)

    # ---------------- model ----------------
    class TrafficGNNReal(nn.Module):
        def __init__(self, node_in_dim, scalar_dim, hidden=64):
            super().__init__()
            self.conv1 = GCNConv(node_in_dim, hidden)
            self.conv2 = GCNConv(hidden, 32)
            self.conv3 = GCNConv(32, 16)
            self.relu = nn.ReLU()
            self.edge_mlp = nn.Sequential(
                nn.Linear(16 * 2 + scalar_dim, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def embed(self, x, edge_index):
            x = self.relu(self.conv1(x, edge_index))
            x = self.relu(self.conv2(x, edge_index))
            x = self.relu(self.conv3(x, edge_index))
            return x

        def forward(self, x, edge_index, u_idx, v_idx, scalars):
            emb = self.embed(x, edge_index)
            edge_in = torch.cat([emb[u_idx], emb[v_idx], scalars], dim=1)
            return self.edge_mlp(edge_in).squeeze(-1)

    model = TrafficGNNReal(node_in_dim=node_feat_t.shape[1], scalar_dim=scalar_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-4)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    best_state = None
    patience, bad_epochs = 40, 0

    for epoch in range(1, 401):
        model.train()
        optimizer.zero_grad()
        pred = model(node_feat_t, edge_index, train_u, train_v, train_s)
        loss = loss_fn(pred, train_y)
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(node_feat_t, edge_index, val_u, val_v, val_s)
            val_loss = loss_fn(val_pred, val_y).item()

        if val_loss < best_val - 1e-4:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1

        if epoch % 50 == 0 or epoch == 1:
            print(f"epoch {epoch:4d}  train_mse={loss.item():.3f}  val_mse={val_loss:.3f}")

        if bad_epochs >= patience:
            print(f"early stopping at epoch {epoch} (best val_mse={best_val:.3f})")
            break

    model.load_state_dict(best_state)
    model.eval()

    def metrics(u_idx, v_idx, scalars, y_true):
        with torch.no_grad():
            y_pred = model(node_feat_t, edge_index, u_idx, v_idx, scalars).numpy()
        y_true_np = y_true.numpy()
        mae = float(np.mean(np.abs(y_pred - y_true_np)))
        rmse = float(np.sqrt(np.mean((y_pred - y_true_np) ** 2)))
        ss_res = float(np.sum((y_true_np - y_pred) ** 2))
        ss_tot = float(np.sum((y_true_np - y_true_np.mean()) ** 2)) or 1e-9
        r2 = 1 - ss_res / ss_tot
        return {"MAE": mae, "RMSE": rmse, "R2": r2, "n": int(len(y_true_np))}

    train_metrics = metrics(train_u, train_v, train_s, train_y)
    val_metrics = metrics(val_u, val_v, val_s, val_y)
    spatial_metrics = metrics(stest_u, stest_v, stest_s, stest_y)
    temporal_metrics = metrics(ttest_u, ttest_v, ttest_s, ttest_y)
    print("\n=== HONEST METRICS (no fabricated accuracy) ===")
    print("train:", train_metrics)
    print("val (spatial, held out during training):", val_metrics)
    print("SPATIAL TEST (unseen roads, incl. 21 edges only ever in segments.csv):", spatial_metrics)
    print("TEMPORAL TEST (known roads, unseen future timestamps, n=13 segments only):", temporal_metrics)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "node_in_dim": int(node_feat_t.shape[1]),
        "scalar_dim": int(scalar_dim),
        "node_feature_columns": ["degree", "avg_incident_maxspeed_kph", "avg_incident_length_m"],
        "node_feature_mean": node_feat_mean.tolist(),
        "node_feature_std": node_feat_std.tolist(),
        "scalar_feature_columns": ["edge_length_m", "base_speed_kph", "hour_sin", "hour_cos", "is_weekend"] + [f"frc_{c}" for c in FRC_CATS],
        "scalar_feature_mean": scalar_mean.tolist(),
        "scalar_feature_std": scalar_std.tolist(),
        "subgraph_node_ids": node_ids,
        "trained_at": datetime.now().isoformat(),
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "test_metrics_spatial": spatial_metrics,
        "test_metrics_temporal": temporal_metrics,
        "data_provenance": (
            "Trained on 760 real TomTom-observed OSM edges (single spatial "
            "snapshot, 2026-08-27) + 13 real TomTom-monitored road segments "
            "polled repeatedly over ~3 days (2026-08-26 onward). "
            "NOT a citywide model: covers ~0.2% of the 393,090-edge Bengaluru "
            "OSM graph with real labels; other edges have no ground truth and "
            "must be treated as graph-propagated estimates, not measurements. "
            "See traffic_module/models/prepare_real_traffic_dataset.py for "
            "exact source files and mapping methodology."
        ),
    }
    torch.save(checkpoint, CHECKPOINT_OUT)
    print(f"\nSaved checkpoint -> {CHECKPOINT_OUT}")

    with open(os.path.join(HERE, "traffic_model_real_v1_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({
            "train": train_metrics, "val": val_metrics,
            "spatial_test": spatial_metrics, "temporal_test": temporal_metrics,
            "provenance": checkpoint["data_provenance"],
        }, f, indent=2)


if __name__ == "__main__":
    main()
