"""
Robust validator/repairer for bengaluru_traffic_history.csv (the real TomTom
observation log written by collect_bengaluru_traffic_production.py).

WHY THIS EXISTS (found by actually inspecting the file, not assumed):
Loading the file with pandas' default C parser fails outright with
"Expected 23 fields ... saw 24" — a handful of physical rows have more
fields than the header. Two distinct, root-caused patterns exist:

  1. STATUS=ERROR rows whose network exception text was written into the
     row without accounting for the header's fixed column set — the
     get_traffic() exception path returns {"status", "http_status",
     "error"} and "error" is not one of the 23 header columns, so it
     lands as a stray extra field. These ARE safely repairable: columns
     0-11 (timestamp through http_status) are still exactly where they
     should be and are trustworthy; every traffic-measurement column from
     "frc" onward is genuinely absent for an ERROR row (there was no
     successful TomTom response), so nulling them is not fabrication —
     it is the same "no data" a clean ERROR row would already show.

  2. STATUS=OK rows with an unexplained field-count shift (frc reads
     empty, a plausible speed_ratio-shaped number appears where
     current_speed_kmh should be, "FRC2" appears three columns later
     than expected, etc.). For these there is no way to tell which
     value belongs in which column without guessing — so per the "never
     invent/never misattribute a value" rule, these are REJECTED, not
     repaired.

Never invents a value. Every accepted number came from the file as-is;
every repaired row only sets already-genuinely-missing fields to null.
"""
from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

EXPECTED_COLUMNS = [
    "timestamp", "osm_u", "osm_v", "osm_key", "sample_latitude", "sample_longitude",
    "osm_road_name", "osm_highway", "edge_length_m", "osm_base_speed_kph",
    "status", "http_status", "frc", "current_speed_kmh", "free_flow_speed_kmh",
    "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
    "road_closure", "segment_geometry", "tomtom_segment_id", "speed_ratio",
    "delay_percent",
]

# Second REAL known schema — the fixed-8-segment forecasting collector's
# own output (collect_forecast_segments.py -> forecast_segments_history.csv).
# Genuinely different column set (data_mode instead of frc/segment_geometry,
# latitude/longitude/road_name/highway/base_speed_kph instead of the
# sample_/osm_ prefixed names) — not a malformed citywide file, a second
# real, deliberately-separate dataset. Supporting it here (rather than a
# parallel copy of this whole module) is the minimal change needed to
# run this existing validator against it, per this task's requirement.
FORECAST_SEGMENTS_COLUMNS = [
    "timestamp", "data_mode", "osm_u", "osm_v", "osm_key", "latitude", "longitude",
    "road_name", "highway", "edge_length_m", "base_speed_kph",
    "status", "http_status", "current_speed_kmh", "free_flow_speed_kmh",
    "current_travel_time_sec", "free_flow_travel_time_sec", "confidence",
    "road_closure", "tomtom_segment_id", "speed_ratio", "delay_percent",
]

_KNOWN_SCHEMAS = {
    "citywide": EXPECTED_COLUMNS,
    "forecast_segments": FORECAST_SEGMENTS_COLUMNS,
}


def _schema_indices(columns: list[str]) -> tuple[int, int, int]:
    """(status_idx, http_status_idx, trailing_from_idx) for whichever
    schema's column list is passed — replaces the old module-level
    constants so the same repair logic works for either real schema."""
    status_idx = columns.index("status")
    http_status_idx = columns.index("http_status")
    return status_idx, http_status_idx, http_status_idx + 1


# Kept for backward compatibility with any existing caller that imported
# these directly — still describe the default/citywide schema.
_STATUS_IDX, _HTTP_STATUS_IDX, _TRAILING_FROM_IDX = _schema_indices(EXPECTED_COLUMNS)

# Real OSM identifiers — must stay integers (or strings), never
# float-formatted ("4845178134.0"), even though they're numeric-looking.
_INTEGER_ID_COLUMNS = {"osm_u", "osm_v", "osm_key"}

# Genuine continuous measurements — safe to store as float once validated.
# Union of both known schemas' numeric column names: harmless for either
# schema individually (a name from the other schema simply never appears
# in that file's rows, .get() returns None, nothing breaks).
_NUMERIC_COLUMNS = {
    "sample_latitude", "sample_longitude", "latitude", "longitude",
    "edge_length_m", "osm_base_speed_kph", "base_speed_kph", "current_speed_kmh",
    "free_flow_speed_kmh", "current_travel_time_sec", "free_flow_travel_time_sec",
    "confidence", "speed_ratio", "delay_percent",
} | _INTEGER_ID_COLUMNS  # still checked for numeric-ness by _is_plausible_row


@dataclass
class ValidationReport:
    source_file: str
    total_data_rows: int = 0
    valid_rows: int = 0
    repaired_rows: int = 0
    rejected_rows: int = 0
    reject_reasons: dict = field(default_factory=dict)
    repair_reasons: dict = field(default_factory=dict)
    unique_timestamps: int = 0
    unique_osm_edges: int = 0
    unique_tomtom_segment_ids: int = 0
    status_counts: dict = field(default_factory=dict)
    time_span_start: str | None = None
    time_span_end: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "total_data_rows": self.total_data_rows,
            "valid_rows": self.valid_rows,
            "repaired_rows": self.repaired_rows,
            "rejected_rows": self.rejected_rows,
            "reject_reasons": self.reject_reasons,
            "repair_reasons": self.repair_reasons,
            "unique_timestamps": self.unique_timestamps,
            "unique_osm_edges": self.unique_osm_edges,
            "unique_tomtom_segment_ids": self.unique_tomtom_segment_ids,
            "status_counts": self.status_counts,
            "time_span_start": self.time_span_start,
            "time_span_end": self.time_span_end,
        }


def _try_float(v: str):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_numeric_fields(row: dict) -> dict:
    """Converts already-validated numeric columns from raw CSV strings to
    float (empty stays None). This is not inventing a value — every
    number here already passed _is_plausible_row's numeric-parse check;
    this only fixes the TYPE so downstream code compares 20.0 to 20.0
    instead of '20.0' to 20.0."""

    out = dict(row)
    for col in _NUMERIC_COLUMNS:
        if col not in out:
            continue  # this column doesn't belong to this row's own schema — never inject it
        v = out.get(col)
        if v in (None, ""):
            out[col] = None
        elif col in _INTEGER_ID_COLUMNS:
            f = _try_float(v)
            out[col] = int(f) if f is not None else None
        else:
            out[col] = _try_float(v)
    return out


def _is_plausible_row(row: dict) -> tuple[bool, str | None]:
    """Basic sanity checks on an otherwise structurally-valid row. Returns
    (ok, reason). Never corrects a value — only accepts or rejects."""

    # Two real, genuinely different timestamp formats exist across the
    # project's two collectors: the citywide collector's naive
    # "YYYY-MM-DD HH:MM:SS" (no timezone — a real, disclosed limitation
    # of that older format), and the forecasting collector's precise,
    # timezone-aware ISO-8601 ("...+05:30"). Both are accepted here;
    # neither is fabricated or reinterpreted as the other.
    ts = row.get("timestamp")
    parsed = None
    try:
        parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        try:
            parsed = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            parsed = None
    if parsed is None:
        return False, "unparseable timestamp"

    if row["status"] not in ("OK", "ERROR"):
        return False, f"unexpected status value: {row['status']!r}"

    if row["status"] == "OK":
        cs = _try_float(row.get("current_speed_kmh"))
        ff = _try_float(row.get("free_flow_speed_kmh"))
        if cs is not None and (cs < 0 or cs > 200):
            return False, f"implausible current_speed_kmh: {cs}"
        if ff is not None and (ff < 0 or ff > 200):
            return False, f"implausible free_flow_speed_kmh: {ff}"

    for col in _NUMERIC_COLUMNS:
        val = row.get(col)
        if val not in (None, "") and _try_float(val) is None:
            return False, f"non-numeric value in numeric column '{col}': {val!r}"

    return True, None


def validate_and_repair(csv_path: str) -> tuple[list[dict], ValidationReport]:
    """Reads csv_path leniently (csv.reader handles proper quoting/embedded
    commas correctly — this is not the source of the malformed rows).
    Returns (clean_rows, report). clean_rows is a list of dicts, containing
    only ACCEPTED + REPAIRED rows.

    Accepts either of the two known REAL schemas (EXPECTED_COLUMNS —
    citywide bengaluru_traffic_history.csv, or FORECAST_SEGMENTS_COLUMNS —
    the fixed-8-segment forecasting collector's output) and refuses
    (raises ValueError) on anything else — still never guesses a mapping
    for an unrecognized file."""

    report = ValidationReport(source_file=csv_path)
    clean_rows: list[dict] = []

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        active_columns = None
        for name, columns in _KNOWN_SCHEMAS.items():
            if header == columns:
                active_columns = columns
                break

        if active_columns is None:
            raise ValueError(
                f"CSV header matches neither known schema. "
                f"Known schemas: {list(_KNOWN_SCHEMAS.keys())}. Got header: {header}. "
                f"Refusing to guess a mapping — fix the schema mismatch first."
            )

        status_idx, http_status_idx, trailing_from_idx = _schema_indices(active_columns)

        for line_num, raw_row in enumerate(reader, start=2):  # 1 = header

            report.total_data_rows += 1

            if len(raw_row) == len(active_columns):

                row = dict(zip(active_columns, raw_row))
                ok, reason = _is_plausible_row(row)

                if ok:
                    clean_rows.append(_coerce_numeric_fields(row))
                    report.valid_rows += 1
                else:
                    report.rejected_rows += 1
                    report.reject_reasons[reason] = report.reject_reasons.get(reason, 0) + 1

                continue

            # ---- Repairable case: ERROR row with a stray extra field ----
            # Columns 0..http_status must still align (they are written
            # before the exception path even runs), and status must read
            # "ERROR" for this specific repair to be justified.
            if (
                len(raw_row) > len(active_columns)
                and len(raw_row) > http_status_idx
                and raw_row[status_idx] == "ERROR"
            ):
                repaired = dict(zip(active_columns[:trailing_from_idx], raw_row[:trailing_from_idx]))
                for col in active_columns[trailing_from_idx:]:
                    repaired[col] = None  # genuinely absent for an ERROR row — not invented

                ok, reason = _is_plausible_row(repaired)
                if ok:
                    clean_rows.append(_coerce_numeric_fields(repaired))
                    report.repaired_rows += 1
                    reason_key = "ERROR row: stray exception-text field beyond http_status; nulled unmeasured traffic fields"
                    report.repair_reasons[reason_key] = report.repair_reasons.get(reason_key, 0) + 1
                else:
                    report.rejected_rows += 1
                    report.reject_reasons[f"repair attempted but still implausible: {reason}"] = (
                        report.reject_reasons.get(f"repair attempted but still implausible: {reason}", 0) + 1
                    )

                continue

            # ---- Everything else: field-count mismatch with no safe,
            # unambiguous way to realign columns. Reject, do not guess. ----
            reason = f"field count mismatch (expected {len(active_columns)}, got {len(raw_row)}), cannot safely determine column alignment"
            report.rejected_rows += 1
            report.reject_reasons[reason] = report.reject_reasons.get(reason, 0) + 1

    # ---- summary stats over the CLEAN rows only ----
    timestamps = {r["timestamp"] for r in clean_rows if r.get("timestamp")}
    osm_edges = {(r["osm_u"], r["osm_v"], r["osm_key"]) for r in clean_rows}
    tomtom_ids = {r["tomtom_segment_id"] for r in clean_rows if r.get("tomtom_segment_id")}
    status_counts: dict[str, int] = {}
    for r in clean_rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    report.unique_timestamps = len(timestamps)
    report.unique_osm_edges = len(osm_edges)
    report.unique_tomtom_segment_ids = len(tomtom_ids)
    report.status_counts = status_counts

    if timestamps:
        sorted_ts = sorted(timestamps)
        report.time_span_start = sorted_ts[0]
        report.time_span_end = sorted_ts[-1]

    return clean_rows, report


def save_clean_dataset(clean_rows: list[dict], out_csv_path: str, columns: list[str] = EXPECTED_COLUMNS) -> None:
    """Writes the validated/repaired rows back out as a clean CSV — a
    separate artifact, the original raw file is never modified/deleted.
    Pass columns=FORECAST_SEGMENTS_COLUMNS when cleaning that schema;
    defaults to the citywide schema for backward compatibility."""

    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)

    with open(out_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in clean_rows:
            writer.writerow(row)


def save_report(report: ValidationReport, out_json_path: str) -> None:

    os.makedirs(os.path.dirname(out_json_path), exist_ok=True)

    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bengaluru_traffic_history.csv"
    )

    rows, rpt = validate_and_repair(src)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "forecast")
    save_clean_dataset(rows, os.path.join(out_dir, "bengaluru_traffic_history_clean.csv"))
    save_report(rpt, os.path.join(out_dir, "csv_validation_report.json"))

    print(json.dumps(rpt.to_dict(), indent=2))
