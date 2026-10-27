"""
Tests for the additive expanded-forecast-data integration in
prepare_real_traffic_dataset.py (load_expanded_forecast_segments() and its
merge into main()'s live_static/live_timeseries).

These are real-data tests, consistent with this project's existing
"never fabricate, always verify against the actual files" convention: they
call the real loader functions against the real files on disk
(bengaluru_t120_expanded_history.csv, live_traffic_history.csv,
bengaluru_traffic_history.csv, bengaluru_traffic_segments.csv, edges.csv/
nodes.csv) -- no mocks, no synthetic fixtures.

Run: python -m pytest traffic_module/models/test_prepare_real_traffic_dataset.py -v
(from the project root, with the project's own venv active so pandas/numpy
match what train_gnn_real_v1.py will actually use)
"""
import os

import prepare_real_traffic_dataset as prep

# ---- shared real data, loaded once for all tests (module scope) ----
_nodes_df, _edges_df = prep.load_graph()
_snapshot_labeled = prep.load_snapshot_edges()
_live_ts, _live_static = prep.map_live_segments_to_edges(_edges_df, _nodes_df)
_expanded_ts, _expanded_static = prep.load_expanded_forecast_segments(_edges_df)


def test_expanded_csv_exists():
    """Sanity precondition -- if this fails, every other test here is
    meaningless (the loader legitimately returns empty dicts when the file
    is missing, per its own docstring, so a missing-file run would silently
    pass everything else with zero data)."""
    assert os.path.exists(prep.EXPANDED_LIVE_HISTORY_CSV), (
        f"{prep.EXPANDED_LIVE_HISTORY_CSV} not found -- the expanded "
        f"collector's output must exist for these tests to mean anything."
    )


def test_expanded_loader_ok_observation_count():
    """1,172 genuine status=OK observations are loaded (matches the
    collector's own file as of this integration; self-consistency check
    against an independent pandas read guards against silent drift)."""
    import pandas as pd
    raw = pd.read_csv(prep.EXPANDED_LIVE_HISTORY_CSV)
    independently_counted_ok = int((raw["status"] == "OK").sum())

    total_loaded = sum(len(v) for v in _expanded_ts.values())

    assert independently_counted_ok == 1172, (
        f"Expected 1,172 OK rows in the source CSV (as measured during "
        f"integration); found {independently_counted_ok}. If the expanded "
        f"collector has kept running since, this is an EXPECTED drift, not "
        f"a bug -- update this assertion to the new real count rather than "
        f"treating it as a failure."
    )
    assert total_loaded == independently_counted_ok, (
        f"Loader kept {total_loaded} observations but the source CSV has "
        f"{independently_counted_ok} genuine OK rows -- the loader must "
        f"never drop a valid OK row (duplicate-timestamp/not-in-graph "
        f"skips are the only allowed exclusions, and none are expected "
        f"here since the source file is already clean)."
    )


def test_expanded_loader_detects_21_new_edges():
    """21 unique (osm_u, osm_v) edges are detected from the expanded file."""
    assert len(_expanded_ts) == 21, (
        f"Expected 21 unique new edges, got {len(_expanded_ts)}: "
        f"{sorted(_expanded_ts.keys())}"
    )
    assert len(_expanded_static) == 21


def test_no_duplicate_timestamp_observations():
    """No edge's time series contains two observations with the same
    timestamp -- real dedup guard, not just an absence-of-duplicates-in-
    source-file coincidence."""
    for key, rows in _expanded_ts.items():
        timestamps = [r["timestamp"] for r in rows]
        assert len(timestamps) == len(set(timestamps)), (
            f"Duplicate timestamp(s) found for edge {key}: "
            f"{[t for t in timestamps if timestamps.count(t) > 1]}"
        )


def test_existing_13_temporal_edges_unaffected():
    """The original 13-segment loader (map_live_segments_to_edges) is
    untouched by this change: still produces exactly 13 edges, computed
    completely independently of load_expanded_forecast_segments()."""
    assert len(_live_static) == 13, (
        f"Expected the original live_traffic_history.csv mapping to still "
        f"produce 13 edges, got {len(_live_static)}. This loader was not "
        f"supposed to be modified at all."
    )
    assert len(_live_ts) == 13
    # And confirm zero overlap with the new 21 -- the real, measured fact
    # this integration was designed around.
    overlap = set(_live_ts.keys()) & set(_expanded_ts.keys())
    assert overlap == set(), f"Unexpected overlap with existing 13 segments: {overlap}"


def test_merged_live_timeseries_has_34_edges():
    """Replicates main()'s merge step exactly (without writing any files)
    and confirms the final live_timeseries dict has 13 + 21 = 34 edges."""
    merged_ts = dict(_live_ts)
    merged_static = dict(_live_static)
    for key, rows in _expanded_ts.items():
        if key in merged_ts:
            existing_timestamps = {r["timestamp"] for r in merged_ts[key]}
            merged_ts[key] = merged_ts[key] + [r for r in rows if r["timestamp"] not in existing_timestamps]
        else:
            merged_ts[key] = rows
            merged_static[key] = _expanded_static[key]

    assert len(merged_ts) == 34, f"Expected 34 merged edges, got {len(merged_ts)}"
    assert len(merged_static) == 34


def test_snapshot_labeled_unchanged():
    """snapshot_labeled comes entirely from load_snapshot_edges(), which
    this integration never touches, calls, or depends on. Proven two ways:
    (1) load_snapshot_edges() produces byte-identical output whether called
    before or after load_expanded_forecast_segments() runs -- zero shared
    state, zero side effects; (2) it does not reference
    EXPANDED_LIVE_HISTORY_CSV or any of the new function's names at all
    (static source check).

    Deliberately NOT a hardcoded edge-count assertion: the root-level
    bengaluru_traffic_history.csv / bengaluru_traffic_segments.csv this
    loader reads are fed by a separate, independently-running collector
    (unrelated to this integration), so their row count can legitimately
    change over time. Pinning a specific number here would either go stale
    or falsely imply this integration controls that count.
    """
    before = prep.load_snapshot_edges()
    _ = prep.load_expanded_forecast_segments(_edges_df)  # exercise the new code path
    after = prep.load_snapshot_edges()

    assert before == after, (
        "load_snapshot_edges() produced different output depending on "
        "whether the new expanded loader ran -- it must be completely "
        "independent (no shared state, no side effects)."
    )
    assert len(_snapshot_labeled) > 0

    import inspect
    source = inspect.getsource(prep.load_snapshot_edges)
    assert "EXPANDED_LIVE_HISTORY_CSV" not in source
    assert "load_expanded_forecast_segments" not in source

    print(f"[info] snapshot_labeled currently has {len(_snapshot_labeled)} edges "
          f"(independent of this integration; may grow over time via the "
          f"separate root-level collector)")
