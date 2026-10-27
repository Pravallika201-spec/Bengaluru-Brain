"""
Builds a REAL-data training set for the Bengaluru traffic-speed GNN, replacing
the old traffic_gnn_dataset.csv (which looked synthetic — round numbers,
uniform 'Congestion Level: 100.0' rows, no real TomTom fields).

Sources (all genuine TomTom / OSM data, no fabricated rows):
  1. D:\\major project\\bengaluru_traffic_history.csv       (739 unique OSM
     edges, ONE snapshot timestamp, has osm_u/osm_v graph node ids)
  2. D:\\major project\\bengaluru_traffic_segments.csv      (100 edges, one
     snapshot ~8 min earlier; 21 of them are NOT in file 1 -> used as an
     independent, never-trained-on spatial holdout)
  3. traffic_module/data/live_traffic_history.csv           (13 named road
     segments, TomTom-polled repeatedly over ~3 days -> the only real
     TIME-VARYING signal available; has no osm_u/osm_v pair, only a
     'nearest_node' id, so each segment is mapped to the graph edge incident
     to that node whose OSM 'name' best matches the TomTom location name)

Structural graph context (node degree, neighboring edge speeds) comes from
traffic_module/data/edges.csv + nodes.csv (154,902 real OSM nodes / 393,090
real OSM edges — confirmed same OSM vintage: 98-100% of the above files'
node ids are found in this graph).

Honesty notes baked into the output:
  - Only ~760 of 393,090 edges (~0.2%) have a real observed speed label.
    Coverage is genuinely narrow; this script does NOT fabricate labels for
    the rest.
  - The single-snapshot files (1, 2) give spatial breadth but zero temporal
    signal each. The live-history file (3) gives real temporal signal but
    for only 13 segments. Both kinds of held-out test sets are produced
    separately so spatial-generalization and temporal-generalization are
    never conflated into one misleading number.
"""
import os
import csv
import json
import math
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\major project
TRAFFIC_MODULE_DATA = os.path.join(ROOT, "traffic_module", "data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))  # traffic_module/models

HISTORY_CSV = os.path.join(ROOT, "bengaluru_traffic_history.csv")
SEGMENTS_CSV = os.path.join(ROOT, "bengaluru_traffic_segments.csv")
LIVE_HISTORY_CSV = os.path.join(TRAFFIC_MODULE_DATA, "live_traffic_history.csv")
FORECASTING_DATA_DIR = os.path.join(ROOT, "traffic_module", "backend", "forecasting", "data")
EXPANDED_LIVE_HISTORY_CSV = os.path.join(FORECASTING_DATA_DIR, "bengaluru_t120_expanded_history.csv")
EDGES_CSV = os.path.join(TRAFFIC_MODULE_DATA, "edges.csv")
NODES_CSV = os.path.join(TRAFFIC_MODULE_DATA, "nodes.csv")

FRC_ORDER = ["FRC0", "FRC1", "FRC2", "FRC3", "FRC4", "FRC5", "FRC6", "FRC7", "UNKNOWN"]


def _safe_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def load_graph():
    edges = pd.read_csv(EDGES_CSV)
    nodes = pd.read_csv(NODES_CSV)
    nodes["node_id"] = nodes["node_id"].astype(np.int64)
    edges["source"] = edges["source"].astype(np.int64)
    edges["target"] = edges["target"].astype(np.int64)
    return nodes, edges


def load_snapshot_edges():
    """Returns a dict keyed by (u, v) -> row dict, from files 1 and 2, deduped
    (file 1 takes priority; file 2 rows unique to it are flagged spatial_holdout=True)."""
    labeled = {}

    with open(HISTORY_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            u, v = _safe_int(row["osm_u"]), _safe_int(row["osm_v"])
            if u is None or v is None:
                continue
            labeled[(u, v)] = {
                "u": u, "v": v,
                "edge_length_m": float(row["edge_length_m"] or 0),
                "base_speed_kph": float(row["osm_base_speed_kph"] or 0),
                "frc": row.get("frc") or "UNKNOWN",
                "highway": row.get("osm_highway") or "unknown",
                "current_speed_kmh": float(row["current_speed_kmh"] or 0),
                "free_flow_speed_kmh": float(row["free_flow_speed_kmh"] or 0),
                "confidence": float(row.get("confidence") or 1.0),
                "timestamp": row["timestamp"],
                "spatial_holdout": False,
                "source_file": "bengaluru_traffic_history.csv",
            }

    n_from_history = len(labeled)

    with open(SEGMENTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            u, v = _safe_int(row["osm_u"]), _safe_int(row["osm_v"])
            if u is None or v is None:
                continue
            key = (u, v)
            if key in labeled:
                continue  # already have this edge from the history snapshot
            labeled[key] = {
                "u": u, "v": v,
                "edge_length_m": float(row["edge_length_m"] or 0),
                "base_speed_kph": float(row["base_speed_kph"] or 0),
                "frc": row.get("frc") or "UNKNOWN",
                "highway": row.get("highway") or "unknown",
                "current_speed_kmh": float(row["current_speed_kmh"] or 0),
                "free_flow_speed_kmh": float(row["free_flow_speed_kmh"] or 0),
                "confidence": float(row.get("confidence") or 1.0),
                "timestamp": row["timestamp"],
                "spatial_holdout": True,  # unique to segments.csv -> never trained on
                "source_file": "bengaluru_traffic_segments.csv",
            }

    n_spatial_holdout = sum(1 for r in labeled.values() if r["spatial_holdout"])
    print(f"[snapshot] {n_from_history} edges from history.csv, "
          f"{n_spatial_holdout} additional held-out edges unique to segments.csv, "
          f"{len(labeled)} total unique labeled edges")
    return labeled


def map_live_segments_to_edges(edges_df, nodes_df):
    """Maps the 13 named, repeatedly-polled TomTom segments onto real graph
    edges incident to their nearest_node, choosing the incident edge whose
    OSM `name` best overlaps the TomTom `traffic_location` string. Falls back
    to the highest-maxspeed incident edge (arterial-like) if no name matches.
    Returns: dict[(u,v)] -> list of {current_speed_kmh, free_flow_speed_kmh,
    timestamp, confidence} time-series rows for that mapped edge, plus the
    static edge attributes for feature-building.
    """
    live = pd.read_csv(LIVE_HISTORY_CSV)
    live["nearest_node"] = live["nearest_node"].astype(float).astype(np.int64)

    edge_lookup = defaultdict(list)  # node -> list of edge rows incident to it
    for row in edges_df.itertuples(index=False):
        edge_lookup[row.source].append(row)
        edge_lookup[row.target].append(row)

    location_to_edge = {}
    ts_rows = defaultdict(list)
    static_attrs = {}

    for location, group in live.groupby("traffic_location"):
        node = int(group["nearest_node"].iloc[0])
        candidates = edge_lookup.get(node, [])
        if not candidates:
            print(f"[live-map] WARNING: no graph edges incident to nearest_node "
                  f"{node} for '{location}' -> segment dropped")
            continue

        loc_norm = str(location).lower().replace(" ", "")
        best = None
        for c in candidates:
            name = str(getattr(c, "name", "") or "").lower().replace(" ", "")
            if name and (name in loc_norm or loc_norm in name):
                best = c
                break
        if best is None:
            # fallback: highest-maxspeed incident edge (arterial-like), else first
            def speed_key(c):
                try:
                    v = float(c.maxspeed)
                except (TypeError, ValueError):
                    return -1.0
                return v if math.isfinite(v) else -1.0
            best = max(candidates, key=speed_key)

        u, v = int(best.source), int(best.target)
        location_to_edge[location] = (u, v)
        static_attrs[(u, v)] = {
            "u": u, "v": v,
            "edge_length_m": float(best.length or 0),
            "base_speed_kph": float(best.maxspeed) if _safe_int(best.maxspeed) else 0.0,
            "frc": "UNKNOWN",
            "highway": str(best.highway or "unknown"),
            "mapped_from_location": location,
            "mapping_method": "name_match" if best is not None and loc_norm in str(getattr(best,'name','') or '').lower().replace(' ','') else "nearest_node_fallback",
        }

    n_dropped_failed_poll = 0
    for _, row in live.iterrows():
        loc = row["traffic_location"]
        if loc not in location_to_edge:
            continue
        # Skip rows where the TomTom poll itself failed (status == 'ERROR',
        # no http_status, current_speed_kmh missing) — these are real
        # collection failures, not valid zero-speed observations, and
        # including them would poison the regression target with NaN/garbage.
        if row.get("status") != "OK" or pd.isna(row.get("current_speed_kmh")):
            n_dropped_failed_poll += 1
            continue
        key = location_to_edge[loc]
        ts_rows[key].append({
            "current_speed_kmh": float(row["current_speed_kmh"]),
            "free_flow_speed_kmh": float(row["free_flow_speed_kmh"]),
            "confidence": float(row["confidence"]),
            "timestamp": row["timestamp"],
        })

    print(f"[live-map] dropped {n_dropped_failed_poll} rows with failed TomTom polls (status != OK)")
    print(f"[live-map] mapped {len(location_to_edge)}/{live['traffic_location'].nunique()} "
          f"named segments onto real graph edges "
          f"({sum(1 for a in static_attrs.values() if a['mapping_method']=='name_match')} by name match, "
          f"{sum(1 for a in static_attrs.values() if a['mapping_method']=='nearest_node_fallback')} by nearest-node fallback)")
    return ts_rows, static_attrs


def load_expanded_forecast_segments(edges_df):
    """Loads the SEPARATE 21-segment expanded forecasting collector's real
    TomTom observations
    (traffic_module/backend/forecasting/collect_forecast_segments_expanded.py
    output, i.e. bengaluru_t120_expanded_history.csv) and turns them into the
    same live_static/live_timeseries shape map_live_segments_to_edges()
    produces above -- but WITHOUT any name-matching or nearest-node
    inference, because this source file already carries the real
    (osm_u, osm_v, osm_key) edge identity directly, resolved by the collector
    straight from this project's own OSM graph. Only status=="OK" rows are
    used; nothing here fabricates, interpolates, or fills a missing
    observation -- an edge/row that can't be trusted is skipped and counted,
    never guessed.

    Returns (ts_rows, static_attrs) in the exact same shape
    map_live_segments_to_edges() returns, so main() can merge them uniformly.
    Does not touch, import from, or modify map_live_segments_to_edges() or
    live_traffic_history.csv in any way.
    """
    if not os.path.exists(EXPANDED_LIVE_HISTORY_CSV):
        print(f"[expanded] {EXPANDED_LIVE_HISTORY_CSV} not found -- skipping "
              f"(fine if the expanded collector hasn't been run yet)")
        return {}, {}

    raw = pd.read_csv(EXPANDED_LIVE_HISTORY_CSV)
    n_total_rows = len(raw)

    ok = raw[raw["status"] == "OK"].copy()
    # Defensive re-validation -- never trust a downstream file blindly even
    # though the collector already row-validates before writing.
    ok = ok.dropna(subset=["osm_u", "osm_v", "current_speed_kmh", "free_flow_speed_kmh", "timestamp"])
    n_ok_rows = len(ok)

    ok["u"] = ok["osm_u"].astype(np.int64)
    ok["v"] = ok["osm_v"].astype(np.int64)

    ts_rows = defaultdict(list)
    static_attrs = {}
    seen_timestamps = defaultdict(set)  # key -> real dedup guard, never a fabricated/synthetic filter
    n_duplicate_skipped = 0

    for row in ok.itertuples(index=False):
        key = (int(row.u), int(row.v))

        if row.timestamp in seen_timestamps[key]:
            n_duplicate_skipped += 1
            continue
        seen_timestamps[key].add(row.timestamp)

        ts_rows[key].append({
            "current_speed_kmh": float(row.current_speed_kmh),
            "free_flow_speed_kmh": float(row.free_flow_speed_kmh),
            "confidence": float(row.confidence) if pd.notna(row.confidence) else 1.0,
            "timestamp": row.timestamp,
        })

        if key not in static_attrs:
            static_attrs[key] = {
                "u": int(row.u), "v": int(row.v),
                "edge_length_m": float(row.edge_length_m) if pd.notna(row.edge_length_m) else 0.0,
                "base_speed_kph": float(row.base_speed_kph) if pd.notna(row.base_speed_kph) else 0.0,
                "frc": "UNKNOWN",
                "highway": str(row.highway) if pd.notna(row.highway) else "unknown",
                "mapped_from_location": str(row.road_name) if pd.notna(row.road_name) else None,
                "mapping_method": "direct_osm_edge_id",  # real (u,v,key) from the graph, zero inference
            }

    n_unique_edges = len(ts_rows)
    n_timeseries_rows = sum(len(v) for v in ts_rows.values())

    print(f"[expanded] {n_total_rows} total rows read from {os.path.basename(EXPANDED_LIVE_HISTORY_CSV)}")
    print(f"[expanded] {n_ok_rows} valid status=OK rows")
    print(f"[expanded] {n_unique_edges} unique new OSM edges (osm_u,osm_v) detected")
    print(f"[expanded] {n_timeseries_rows} real observations kept as live_timeseries rows "
          f"({n_duplicate_skipped} duplicate timestamps skipped)")

    # Non-excluding integrity check: this project has two independent real
    # OSM graph files (traffic_module/data/edges.csv, used here and by
    # train_gnn_real_v1.py; backend/data/bengaluru_graph.pkl, used by the
    # forecasting collectors). They are not guaranteed identical. An edge
    # can be genuinely real and still be absent from THIS graph file -- that
    # is a data-provenance fact to surface loudly, not a reason to silently
    # drop real, already-collected observations from live_timeseries (which
    # would contradict "build entries for all new edges using their real
    # observations"). Downstream, build_subgraph()/train_gnn_real_v1.py
    # already silently skip any edge whose nodes aren't in this graph file
    # (pre-existing, unmodified behavior) -- so such an edge simply won't
    # contribute training samples until the graph-file mismatch is resolved,
    # but its real data is not hidden or fabricated away here.
    known_nodes = set(edges_df["source"].astype(np.int64)) | set(edges_df["target"].astype(np.int64))
    missing_from_graph = [key for key in ts_rows if key[0] not in known_nodes or key[1] not in known_nodes]
    if missing_from_graph:
        print(f"[expanded] WARNING: {len(missing_from_graph)} edge(s) have real observations here but "
              f"neither endpoint exists in traffic_module/data/edges.csv (a DIFFERENT graph file than "
              f"the one the collector validated against) -- their data is still included in "
              f"live_timeseries/live_static below, but train_gnn_real_v1.py's existing subgraph-membership "
              f"check will not be able to use it as training samples until this is reconciled: "
              f"{missing_from_graph}")

    return dict(ts_rows), static_attrs


def build_subgraph(labeled_keys, edges_df, nodes_df, hops=1):
    """Labeled edges + up to `hops` neighboring edges, for real GCN message
    passing context (not just isolated labeled points)."""
    node_to_edges = defaultdict(list)
    for idx, row in enumerate(edges_df.itertuples(index=False)):
        node_to_edges[row.source].append(idx)
        node_to_edges[row.target].append(idx)

    frontier = set()
    for (u, v) in labeled_keys:
        frontier.add(u)
        frontier.add(v)

    included_edge_idx = set()
    current = set(frontier)
    for _ in range(hops):
        next_frontier = set()
        for node in current:
            for eidx in node_to_edges.get(node, []):
                if eidx in included_edge_idx:
                    continue
                included_edge_idx.add(eidx)
                r = edges_df.iloc[eidx]
                next_frontier.add(int(r.source))
                next_frontier.add(int(r.target))
        current = next_frontier

    sub_edges = edges_df.iloc[sorted(included_edge_idx)].reset_index(drop=True)
    sub_nodes = pd.unique(pd.concat([sub_edges["source"], sub_edges["target"]]))
    sub_nodes_df = nodes_df[nodes_df["node_id"].isin(sub_nodes)].reset_index(drop=True)
    print(f"[subgraph] {len(sub_nodes_df)} nodes, {len(sub_edges)} edges "
          f"(built from {len(labeled_keys)} labeled edges, {hops}-hop neighborhood)")
    return sub_nodes_df, sub_edges


def main():
    nodes_df, edges_df = load_graph()
    snapshot_labeled = load_snapshot_edges()
    live_ts, live_static = map_live_segments_to_edges(edges_df, nodes_df)

    # ---- additive merge: the separate 21-segment expanded forecasting
    # collector's real observations (see load_expanded_forecast_segments()).
    # This only ADDS new (u,v) keys on top of the original 13-segment
    # mapping above -- live_ts/live_static themselves are never modified,
    # never overwritten, never re-derived; they are the base the merge
    # starts from.
    expanded_ts, expanded_static = load_expanded_forecast_segments(edges_df)

    n_before_merge = len(live_ts)
    merged_ts = dict(live_ts)
    merged_static = dict(live_static)
    n_unexpected_overlap = 0
    for key, rows in expanded_ts.items():
        if key in merged_ts:
            # Measured real overlap with the existing 13 segments is 0 --
            # this branch is defensive only. Never drop either source's real
            # observations on an unexpected overlap: union by timestamp so
            # nothing is silently lost or double-counted.
            n_unexpected_overlap += 1
            existing_timestamps = {r["timestamp"] for r in merged_ts[key]}
            merged_ts[key] = merged_ts[key] + [r for r in rows if r["timestamp"] not in existing_timestamps]
        else:
            merged_ts[key] = rows
            merged_static[key] = expanded_static[key]

    n_new_edges_merged = len(merged_ts) - n_before_merge
    print(f"[merge] {n_new_edges_merged} new edges merged into live_timeseries "
          f"(original {n_before_merge} + new {n_new_edges_merged} = {len(merged_ts)}"
          + (f", {n_unexpected_overlap} unexpected overlap handled by timestamp union" if n_unexpected_overlap else "")
          + ")")
    print(f"[merge] FINAL live_timeseries edge count: {len(merged_ts)}")

    all_labeled_keys = set(snapshot_labeled.keys()) | set(merged_static.keys())
    sub_nodes_df, sub_edges_df = build_subgraph(all_labeled_keys, edges_df, nodes_df, hops=1)
    print(f"[merge] FINAL subgraph node count: {len(sub_nodes_df)}")
    print(f"[merge] FINAL subgraph edge count: {len(sub_edges_df)}")

    payload = {
        "snapshot_labeled": {f"{k[0]}_{k[1]}": v for k, v in snapshot_labeled.items()},
        "live_static": {f"{k[0]}_{k[1]}": v for k, v in merged_static.items()},
        "live_timeseries": {f"{k[0]}_{k[1]}": v for k, v in merged_ts.items()},
        "meta": {
            "built_at": datetime.now().isoformat(),
            "n_snapshot_edges": len(snapshot_labeled),
            "n_spatial_holdout_edges": sum(1 for r in snapshot_labeled.values() if r["spatial_holdout"]),
            "n_live_segments": len(merged_static),
            "n_live_timeseries_rows": sum(len(v) for v in merged_ts.values()),
            "subgraph_nodes": len(sub_nodes_df),
            "subgraph_edges": len(sub_edges_df),
        },
    }

    with open(os.path.join(OUT_DIR, "real_traffic_labels.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    sub_nodes_df.to_csv(os.path.join(OUT_DIR, "real_subgraph_nodes.csv"), index=False)
    sub_edges_df.to_csv(os.path.join(OUT_DIR, "real_subgraph_edges.csv"), index=False)

    print("\n=== SUMMARY (all real TomTom/OSM data, nothing fabricated) ===")
    print(json.dumps(payload["meta"], indent=2))


if __name__ == "__main__":
    main()
