"""
Serves predictions from the REAL-data GNN checkpoint (traffic_model_real_v1.pth,
see traffic_module/models/train_gnn_real_v1.py for how it was trained and its
honest spatial/temporal test metrics).

IMPORTANT — honesty boundary: this checkpoint has real ground-truth labels for
only ~772 of the ~393,090 edges in the Bengaluru OSM graph (~0.2% coverage).
This service therefore does NOT claim to score arbitrary routes. It:
  1. Loads the trained model + the small (4,304-node) subgraph it was trained on.
  2. Given a route's coordinate list (as returned by OSRM/ORS), checks whether
     any point on the route falls within MATCH_RADIUS_M of one of the labeled
     edges' midpoints.
  3. If yes, runs the real GNN on that specific edge and returns a clearly
     labeled prediction (source="REAL_GNN_V1", confidence based on which test
     split validated that kind of edge).
  4. If no, returns covered=False with an explicit reason — callers must NOT
     silently substitute the rule-based heuristic and call it "the GNN".
"""
import os
import json
import math
from functools import lru_cache

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.nn import GCNConv

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(os.path.dirname(HERE), "models")
CHECKPOINT_PATH = os.path.join(MODELS_DIR, "traffic_model_real_v1.pth")
LABELS_PATH = os.path.join(MODELS_DIR, "real_traffic_labels.json")
SUB_NODES_PATH = os.path.join(MODELS_DIR, "real_subgraph_nodes.csv")
SUB_EDGES_PATH = os.path.join(MODELS_DIR, "real_subgraph_edges.csv")

MATCH_RADIUS_M = 200.0
FRC_CATS = ["FRC0", "FRC1", "FRC2", "FRC3", "FRC4", "FRC5", "FRC6", "FRC7", "UNKNOWN"]


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


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def frc_onehot(frc):
    v = [0.0] * len(FRC_CATS)
    idx = FRC_CATS.index(frc) if frc in FRC_CATS else FRC_CATS.index("UNKNOWN")
    v[idx] = 1.0
    return v


class _RealGnnContext:
    """Lazily-loaded singleton: model + subgraph + labeled-edge geometry."""

    def __init__(self):
        self.available = False
        self.reason = None
        try:
            self._load()
            self.available = True
        except Exception as e:  # pragma: no cover - defensive
            self.reason = f"Failed to load real GNN checkpoint: {e}"

    def _load(self):
        if not os.path.exists(CHECKPOINT_PATH):
            raise FileNotFoundError(CHECKPOINT_PATH)
        checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)

        sub_nodes = pd.read_csv(SUB_NODES_PATH)
        sub_edges = pd.read_csv(SUB_EDGES_PATH)
        node_ids = sub_nodes["node_id"].astype(np.int64).tolist()
        self.node_index = {nid: i for i, nid in enumerate(node_ids)}
        n_nodes = len(node_ids)

        src = sub_edges["source"].astype(np.int64).map(self.node_index).values
        dst = sub_edges["target"].astype(np.int64).map(self.node_index).values
        self.edge_index = torch.tensor(
            np.concatenate([np.stack([src, dst]), np.stack([dst, src])], axis=1),
            dtype=torch.long,
        )

        node_mean = np.array(checkpoint["node_feature_mean"])
        node_std = np.array(checkpoint["node_feature_std"])

        # Recompute the same real node features used at training time
        # (degree, avg incident maxspeed, avg incident length) for this subgraph.
        degree = np.zeros(n_nodes)
        maxspeed_sum = np.zeros(n_nodes)
        maxspeed_cnt = np.zeros(n_nodes)
        length_sum = np.zeros(n_nodes)

        def parse_maxspeed(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            return f if math.isfinite(f) else None

        for row in sub_edges.itertuples(index=False):
            ui, vi = self.node_index[int(row.source)], self.node_index[int(row.target)]
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

        mean_global = float(np.nan_to_num(maxspeed_sum / np.maximum(maxspeed_cnt, 1)).mean())
        avg_maxspeed = np.where(maxspeed_cnt > 0, maxspeed_sum / np.maximum(maxspeed_cnt, 1), mean_global)
        avg_length = length_sum / np.maximum(degree, 1)
        node_feat_raw = np.stack([degree, avg_maxspeed, avg_length], axis=1)
        node_feat = (node_feat_raw - node_mean) / node_std
        self.node_feat_t = torch.tensor(node_feat, dtype=torch.float32)

        self.model = TrafficGNNReal(checkpoint["node_in_dim"], checkpoint["scalar_dim"])
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.scalar_mean = np.array(checkpoint["scalar_feature_mean"])
        self.scalar_std = np.array(checkpoint["scalar_feature_std"])
        self.metrics = {
            "spatial_test": checkpoint.get("test_metrics_spatial"),
            "temporal_test": checkpoint.get("test_metrics_temporal"),
        }
        self.provenance = checkpoint.get("data_provenance")

        # Labeled-edge geometry, for route-matching by distance
        with open(LABELS_PATH, encoding="utf-8") as f:
            labels_payload = json.load(f)
        node_coord = {int(r.node_id): (r.y, r.x) for r in sub_nodes.itertuples(index=False)}
        self.labeled_edges = []  # list of dicts: u, v, mid_lat, mid_lon, base_speed_kph, frc
        for key, row in labels_payload["snapshot_labeled"].items():
            u, v = row["u"], row["v"]
            if u not in node_coord or v not in node_coord or u not in self.node_index or v not in self.node_index:
                continue
            lat_u, lon_u = node_coord[u]
            lat_v, lon_v = node_coord[v]
            self.labeled_edges.append({
                "u": u, "v": v,
                "mid_lat": (lat_u + lat_v) / 2, "mid_lon": (lon_u + lon_v) / 2,
                "base_speed_kph": row["base_speed_kph"], "frc": row["frc"],
                "road_name": row.get("highway", "unknown"),
                "eval_group": "spatial_test_edge" if row["spatial_holdout"] else "trained_edge",
            })
        for key, row in labels_payload["live_static"].items():
            u, v = row["u"], row["v"]
            if u not in node_coord or v not in node_coord or u not in self.node_index or v not in self.node_index:
                continue
            lat_u, lon_u = node_coord[u]
            lat_v, lon_v = node_coord[v]
            self.labeled_edges.append({
                "u": u, "v": v,
                "mid_lat": (lat_u + lat_v) / 2, "mid_lon": (lon_u + lon_v) / 2,
                "base_speed_kph": row["base_speed_kph"], "frc": row.get("frc", "UNKNOWN"),
                "road_name": row.get("mapped_from_location", "unknown"),
                "eval_group": "trained_edge_temporal",
            })

        # --- Coverage expansion (Phase 5): the model's own trained subgraph
        # (real_subgraph_edges.csv, real OSM data) has 5,819 edges — only
        # ~749-772 of them have TomTom ground-truth labels (self.labeled_edges
        # above). The GNN's node embeddings come from message-passing over
        # the WHOLE subgraph, so predict_edge() is not limited to labeled
        # edges: it can genuinely run inference on any (u, v) pair whose
        # nodes are in this subgraph, using that edge's own real OSM
        # length/maxspeed. This is real model inference, not a lookup — but
        # unlike self.labeled_edges, these edges were never held out and
        # scored against ground truth, so they must NEVER be reported with
        # the same confidence/label as a validated match. Kept in a
        # SEPARATE list, matched only when no labeled edge is nearby, and
        # always returned as REAL_GNN_V1_EXTRAPOLATED with an explicit
        # "not individually validated" note (see get_route_traffic_signal).
        labeled_keys = {(e["u"], e["v"]) for e in self.labeled_edges} | {(e["v"], e["u"]) for e in self.labeled_edges}
        self.extrapolated_edges = []
        for row in sub_edges.itertuples(index=False):
            u, v = int(row.source), int(row.target)
            if (u, v) in labeled_keys or u not in node_coord or v not in node_coord:
                continue
            lat_u, lon_u = node_coord[u]
            lat_v, lon_v = node_coord[v]
            try:
                maxspeed = float(row.maxspeed)
                if not math.isfinite(maxspeed) or maxspeed <= 0:
                    maxspeed = 40.0
            except (TypeError, ValueError):
                maxspeed = 40.0
            self.extrapolated_edges.append({
                "u": u, "v": v,
                "mid_lat": (lat_u + lat_v) / 2, "mid_lon": (lon_u + lon_v) / 2,
                "base_speed_kph": maxspeed,
                # FRC (TomTom's Functional Road Class) was only ever assigned
                # by the original collector for labeled edges — we do not
                # have a verified OSM-highway->FRC crosswalk for the rest, so
                # honestly use the model's own UNKNOWN category rather than
                # guess one.
                "frc": "UNKNOWN",
                "road_name": str(row.name) if isinstance(row.name, str) else str(row.highway or "unknown"),
                "length_m": float(row.length) if row.length == row.length else 100.0,
                "eval_group": "extrapolated_unvalidated",
            })

    def predict_edge(self, u, v, base_speed_kph, frc, hour_sin, hour_cos, is_weekend, edge_length_m=100.0):
        scalar = np.array([[edge_length_m, base_speed_kph, hour_sin, hour_cos, is_weekend] + frc_onehot(frc)])
        scalar_norm = (scalar - self.scalar_mean) / self.scalar_std
        scalar_t = torch.tensor(scalar_norm, dtype=torch.float32)
        u_idx = torch.tensor([self.node_index[u]], dtype=torch.long)
        v_idx = torch.tensor([self.node_index[v]], dtype=torch.long)
        with torch.no_grad():
            pred = self.model(self.node_feat_t, self.edge_index, u_idx, v_idx, scalar_t)
        return float(pred.item())


@lru_cache(maxsize=1)
def _get_context():
    return _RealGnnContext()


def get_route_traffic_signal(route_coords, hour, is_weekend):
    """route_coords: list of [lat, lon]. Returns a dict describing whether the
    REAL retrained GNN has any actual ground-truth-adjacent coverage on this
    route, and if so, its prediction — never silently substituting a guess."""
    ctx = _get_context()
    if not ctx.available:
        return {"covered": False, "reason": ctx.reason, "source": "REAL_GNN_V1"}

    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)

    matches = []
    for point in route_coords[:: max(1, len(route_coords) // 40) or 1]:
        lat, lon = point[0], point[1]
        for edge in ctx.labeled_edges:
            d = haversine_m(lat, lon, edge["mid_lat"], edge["mid_lon"])
            if d <= MATCH_RADIUS_M:
                matches.append((d, edge))

    if matches:
        matches.sort(key=lambda t: t[0])
        seen = set()
        predictions = []
        for dist, edge in matches:
            key = (edge["u"], edge["v"])
            if key in seen:
                continue
            seen.add(key)
            speed = ctx.predict_edge(edge["u"], edge["v"], edge["base_speed_kph"], edge["frc"],
                                      hour_sin, hour_cos, 1.0 if is_weekend else 0.0)
            predictions.append({
                "road_name": edge["road_name"],
                "distance_from_route_m": round(dist, 1),
                "predicted_speed_kmh": round(speed, 1),
                "eval_group": edge["eval_group"],
            })
            if len(predictions) >= 5:
                break

        avg_speed = sum(p["predicted_speed_kmh"] for p in predictions) / len(predictions)
        return {
            "covered": True,
            "source": "REAL_GNN_V1",
            "matched_segments": predictions,
            "avg_predicted_speed_kmh": round(avg_speed, 1),
            "model_metrics": ctx.metrics,
            "note": "Prediction from the GNN retrained on real TomTom/OSM data "
                    "(see traffic_module/models/traffic_model_real_v1_metrics.json). "
                    "Covers only the specific monitored segment(s) matched above, "
                    "not the whole route.",
        }

    # Tier 2 (Phase 5 coverage expansion): no TomTom-labeled edge nearby, but
    # the route may still pass near one of the OTHER 5,819 real OSM edges in
    # the model's trained subgraph. The model can genuinely run inference on
    # these (same embed()+edge_mlp forward pass, real OSM length/maxspeed as
    # input) via graph-embedding generalization — but since these specific
    # edges were never scored against ground truth, this is honestly labeled
    # as unvalidated extrapolation, not the same claim as REAL_GNN_V1 above.
    extrap_matches = []
    for point in route_coords[:: max(1, len(route_coords) // 40) or 1]:
        lat, lon = point[0], point[1]
        for edge in ctx.extrapolated_edges:
            d = haversine_m(lat, lon, edge["mid_lat"], edge["mid_lon"])
            if d <= MATCH_RADIUS_M:
                extrap_matches.append((d, edge))

    if not extrap_matches:
        return {
            "covered": False,
            "reason": f"No point on this route is within {int(MATCH_RADIUS_M)}m of any of the "
                      f"{len(ctx.labeled_edges)} TomTom-labeled or {len(ctx.extrapolated_edges)} "
                      f"other real OSM edges in this model's trained subgraph.",
            "source": "REAL_GNN_V1",
        }

    extrap_matches.sort(key=lambda t: t[0])
    seen = set()
    predictions = []
    for dist, edge in extrap_matches:
        key = (edge["u"], edge["v"])
        if key in seen:
            continue
        seen.add(key)
        speed = ctx.predict_edge(edge["u"], edge["v"], edge["base_speed_kph"], edge["frc"],
                                  hour_sin, hour_cos, 1.0 if is_weekend else 0.0,
                                  edge_length_m=edge.get("length_m", 100.0))
        predictions.append({
            "road_name": edge["road_name"],
            "distance_from_route_m": round(dist, 1),
            "predicted_speed_kmh": round(speed, 1),
            "eval_group": edge["eval_group"],
        })
        if len(predictions) >= 5:
            break

    avg_speed = sum(p["predicted_speed_kmh"] for p in predictions) / len(predictions)
    return {
        "covered": True,
        "source": "REAL_GNN_V1_EXTRAPOLATED",
        "matched_segments": predictions,
        "avg_predicted_speed_kmh": round(avg_speed, 1),
        "model_metrics": ctx.metrics,
        "note": "EXTRAPOLATED — real GNN inference (same trained model, same graph-embedding "
                "forward pass) on a real OSM edge from this model's subgraph, but this specific "
                "edge has NO TomTom ground-truth label and was not part of any test split. "
                "Treat as a lower-confidence estimate, not a validated measurement.",
    }


def get_model_metrics():
    ctx = _get_context()
    if not ctx.available:
        return {"available": False, "reason": ctx.reason}
    return {"available": True, "metrics": ctx.metrics, "provenance": ctx.provenance,
            "n_labeled_edges": len(ctx.labeled_edges),
            "n_extrapolated_edges": len(ctx.extrapolated_edges),
            "extrapolated_edges_note": ("Real GNN inference is also available on these edges (same "
                "model, real OSM length/maxspeed as input) but they have no TomTom ground-truth "
                "label and were not part of any test split — reported separately as "
                "REAL_GNN_V1_EXTRAPOLATED, never merged into the validated coverage figure above.")}
