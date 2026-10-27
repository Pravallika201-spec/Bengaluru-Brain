"""
Builds real T -> T+120min forecasting pairs from the validated TomTom
observation log (see csv_validator.py). A pair is only created from two
GENUINE observations of the SAME real OSM edge — never a random future
row, never an interpolated/fabricated value, never future information
leaked into the input side of the pair.

Horizon: 120 minutes (TARGET_HORIZON_MINUTES).
Tolerance: a future observation counts as "the +120min observation" if it
falls within TOLERANCE_MINUTES of exactly target_time = t + 120min. This
tolerance exists because the collector's per-edge revisit interval is not
a perfectly regular 120 minutes (it depends on ward-rotation batch timing)
— see the data-readiness report this module produces for what the ACTUAL
per-edge revisit interval is in the currently-collected data.

If, for a given edge, no observation falls inside the tolerance window
around t+120min, NO pair is created for that (edge, t) — not the nearest
available row, not an interpolated value. This is what "do not use random
future rows" and "do not create fake 120-minute targets" mean concretely.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

TARGET_HORIZON_MINUTES = 120
TOLERANCE_MINUTES = 15  # accept an observation within [105, 135] minutes as "T+120"

# Real, genuine input features available at time T (no future information).
INPUT_FEATURE_COLUMNS = [
    "current_speed_kmh", "free_flow_speed_kmh", "speed_ratio", "delay_percent",
    "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
]


@dataclass
class DataReadinessReport:
    horizon_minutes: int = TARGET_HORIZON_MINUTES
    tolerance_minutes: int = TOLERANCE_MINUTES
    total_valid_observations: int = 0
    unique_edges: int = 0
    edges_with_2plus_observations: int = 0
    median_revisit_gap_minutes: float | None = None
    min_revisit_gap_minutes: float | None = None
    max_revisit_gap_minutes: float | None = None
    candidate_pairs_within_tolerance: int = 0
    edges_with_at_least_one_pair: int = 0
    time_span_start: str | None = None
    time_span_end: str | None = None
    verdict: str = ""

    def to_dict(self) -> dict:
        return dict(
            horizon_minutes=self.horizon_minutes,
            tolerance_minutes=self.tolerance_minutes,
            total_valid_observations=self.total_valid_observations,
            unique_edges=self.unique_edges,
            edges_with_2plus_observations=self.edges_with_2plus_observations,
            median_revisit_gap_minutes=self.median_revisit_gap_minutes,
            min_revisit_gap_minutes=self.min_revisit_gap_minutes,
            max_revisit_gap_minutes=self.max_revisit_gap_minutes,
            candidate_pairs_within_tolerance=self.candidate_pairs_within_tolerance,
            edges_with_at_least_one_pair=self.edges_with_at_least_one_pair,
            time_span_start=self.time_span_start,
            time_span_end=self.time_span_end,
            verdict=self.verdict,
        )


def _parse_ts(s: str) -> datetime | None:
    """Accepts both real timestamp formats in this project: the citywide
    collector's naive 'YYYY-MM-DD HH:MM:SS', and the fixed-8-segment
    forecasting collector's timezone-aware ISO-8601 ('...+05:30')."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def build_forecast_pairs(clean_rows: list[dict]) -> tuple[list[dict], DataReadinessReport]:
    """clean_rows: output of csv_validator.validate_and_repair (status may
    be OK or ERROR — only OK rows with real numeric speed data can serve
    as either the input or the target side of a pair)."""

    report = DataReadinessReport()

    by_edge: dict[tuple, list[dict]] = {}
    for r in clean_rows:
        if r.get("status") != "OK":
            continue
        ts = _parse_ts(r.get("timestamp"))
        if ts is None:
            continue
        cs = r.get("current_speed_kmh")
        if cs in (None, ""):
            continue
        key = (r["osm_u"], r["osm_v"], r["osm_key"])
        row = dict(r)
        row["_ts"] = ts
        by_edge.setdefault(key, []).append(row)

    report.total_valid_observations = sum(len(v) for v in by_edge.values())
    report.unique_edges = len(by_edge)

    all_timestamps = [row["_ts"] for rows in by_edge.values() for row in rows]
    if all_timestamps:
        report.time_span_start = min(all_timestamps).strftime("%Y-%m-%d %H:%M:%S")
        report.time_span_end = max(all_timestamps).strftime("%Y-%m-%d %H:%M:%S")

    gaps_minutes: list[float] = []
    edges_with_2plus = 0

    for key, rows in by_edge.items():
        rows.sort(key=lambda r: r["_ts"])
        if len(rows) >= 2:
            edges_with_2plus += 1
        for i in range(len(rows) - 1):
            gap = (rows[i + 1]["_ts"] - rows[i]["_ts"]).total_seconds() / 60.0
            gaps_minutes.append(gap)

    report.edges_with_2plus_observations = edges_with_2plus

    if gaps_minutes:
        gaps_sorted = sorted(gaps_minutes)
        report.median_revisit_gap_minutes = round(gaps_sorted[len(gaps_sorted) // 2], 1)
        report.min_revisit_gap_minutes = round(gaps_sorted[0], 1)
        report.max_revisit_gap_minutes = round(gaps_sorted[-1], 1)

    # ---- actual T -> T+120min pairing, tolerance-based, no fabrication ----
    pairs: list[dict] = []
    edges_with_pair: set = set()

    for key, rows in by_edge.items():
        for i, base in enumerate(rows):
            target_time = base["_ts"] + timedelta(minutes=TARGET_HORIZON_MINUTES)
            lo = target_time - timedelta(minutes=TOLERANCE_MINUTES)
            hi = target_time + timedelta(minutes=TOLERANCE_MINUTES)

            best_match = None
            best_delta = None
            for cand in rows[i + 1:]:
                if cand["_ts"] < lo:
                    continue
                if cand["_ts"] > hi:
                    break  # rows are sorted by time; nothing further can match
                delta = abs((cand["_ts"] - target_time).total_seconds())
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_match = cand

            if best_match is None:
                continue  # no fabricated pair — genuinely no observation in tolerance

            input_features = {c: base.get(c) for c in INPUT_FEATURE_COLUMNS}
            input_features["hour"] = base["_ts"].hour
            input_features["day_of_week"] = base["_ts"].weekday()
            input_features["is_weekend"] = 1 if base["_ts"].weekday() >= 5 else 0

            pairs.append({
                "osm_u": key[0], "osm_v": key[1], "osm_key": key[2],
                "input_timestamp": base["_ts"].strftime("%Y-%m-%d %H:%M:%S"),
                "target_timestamp": best_match["_ts"].strftime("%Y-%m-%d %H:%M:%S"),
                "actual_gap_minutes": round((best_match["_ts"] - base["_ts"]).total_seconds() / 60, 1),
                "input_features": input_features,
                "target_current_speed_kmh": best_match.get("current_speed_kmh"),
                "target_speed_ratio": best_match.get("speed_ratio"),
                "target_delay_percent": best_match.get("delay_percent"),
            })
            edges_with_pair.add(key)

    report.candidate_pairs_within_tolerance = len(pairs)
    report.edges_with_at_least_one_pair = len(edges_with_pair)

    MIN_PAIRS_FOR_TRAINING = 200  # a floor, not a target — see report verdict text

    if report.candidate_pairs_within_tolerance == 0:
        report.verdict = (
            "INSUFFICIENT: zero T+120min pairs available. The per-edge revisit "
            f"interval in this dataset is currently ~{report.median_revisit_gap_minutes} "
            f"minutes (median), driven by the collector's 369-ward batch-rotation "
            f"schedule — every edge is revisited roughly once per full rotation, "
            f"not every ~120 minutes. No amount of preprocessing can create a "
            f"120-minute pair when no two real observations of the same edge "
            f"exist that close together. A trained model would be fabricated."
        )
    elif report.candidate_pairs_within_tolerance < MIN_PAIRS_FOR_TRAINING:
        report.verdict = (
            f"INSUFFICIENT: only {report.candidate_pairs_within_tolerance} pairs "
            f"available (floor considered for a first honest model: {MIN_PAIRS_FOR_TRAINING}). "
            f"Not enough for a reliable time-aware train/val/test split."
        )
    else:
        report.verdict = (
            f"SUFFICIENT for a first exploratory model: "
            f"{report.candidate_pairs_within_tolerance} pairs across "
            f"{report.edges_with_at_least_one_pair} edges."
        )

    return pairs, report


def save_pairs(pairs: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, indent=2)


def save_readiness_report(report: DataReadinessReport, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)


# ---------------------------------------------------------------------------
# API-facing status — cached (mtime-checked) so /api/traffic/forecast-2h
# doesn't re-parse the whole CSV on every request. No model is ever trained
# or invoked here unless readiness.verdict genuinely starts with
# "SUFFICIENT" — with the currently-collected data that branch is not
# reachable, and is intentionally left unimplemented rather than faked.
# ---------------------------------------------------------------------------

_cache: dict = {"mtime": None, "pairs": None, "report": None}


def get_forecast_status(csv_path: str) -> dict:

    try:
        mtime = os.path.getmtime(csv_path)
    except OSError:
        return {
            "forecast_horizon_minutes": TARGET_HORIZON_MINUTES,
            "available": False,
            "status": "UNAVAILABLE",
            "reason": f"traffic history file not found: {csv_path}",
            "data_quality": None,
        }

    if _cache["mtime"] != mtime:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from forecasting.csv_validator import validate_and_repair

        clean_rows, _val_report = validate_and_repair(csv_path)
        pairs, readiness = build_forecast_pairs(clean_rows)
        _cache.update(mtime=mtime, pairs=pairs, report=readiness)

    readiness: DataReadinessReport = _cache["report"]

    if not readiness.verdict.startswith("SUFFICIENT"):
        return {
            "forecast_horizon_minutes": TARGET_HORIZON_MINUTES,
            "forecast_timestamp": None,
            "traffic_condition": None,
            "predicted_speed_kmh": None,
            "predicted_delay_percent": None,
            "confidence": None,
            "available": False,
            "status": "UNAVAILABLE",
            "reason": "2-hour forecast unavailable: insufficient historical temporal coverage.",
            "data_source": "traffic_module/backend/bengaluru_traffic_history.csv",
            "model": "none — no model has been trained; see data_quality for why",
            "data_quality": readiness.to_dict(),
        }

    # Not reachable with the data collected so far (see forecast_dataset_builder
    # tests / data_readiness_report.json) — left unimplemented rather than
    # faked. When enough real T+120 pairs exist, a real trained model's
    # prediction goes here instead of this placeholder.
    return {
        "forecast_horizon_minutes": TARGET_HORIZON_MINUTES,
        "available": False,
        "status": "UNAVAILABLE",
        "reason": "Sufficient pairs exist but no model has been trained yet — training was not run.",
        "data_quality": readiness.to_dict(),
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from forecasting.csv_validator import validate_and_repair

    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bengaluru_traffic_history.csv"
    )

    clean_rows, _val_report = validate_and_repair(src)
    pairs, readiness = build_forecast_pairs(clean_rows)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "forecast")
    save_pairs(pairs, os.path.join(out_dir, "forecast_pairs_t120.json"))
    save_readiness_report(readiness, os.path.join(out_dir, "data_readiness_report.json"))

    print(json.dumps(readiness.to_dict(), indent=2))
