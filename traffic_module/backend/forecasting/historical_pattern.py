"""
Real hour-of-day speed-ratio pattern, derived directly from the actual
TomTom observations in bengaluru_traffic_history.csv (via csv_validator).

This is NOT a trained model and does not claim to be one. It is a
straightforward aggregation: for each hour-of-day (0-23), the average
real speed_ratio (current_speed / free_flow_speed) across every valid
observation, of any real segment, that happened to fall in that hour —
citywide, not per-segment (per-segment history is too sparse: median
~2.5 observations per edge, see forecasting/README.md). Every number
here traces back to a real TomTom reading; nothing is interpolated for
a missing hour, and a missing hour is reported as missing, not filled
with a guess.

Known, disclosed limitation: the data currently spans ~24 hours of a
SINGLE calendar window (2026-09-08 -> 2026-09-09), so this pattern
conflates "hour of day" with "the one specific day it was observed on" —
it cannot yet distinguish a genuine day-of-week effect from a one-off.
That caveat is carried through into every consumer of this module.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass

MIN_SAMPLES_FOR_PATTERN = 10  # below this, an hour's bucket is "insufficient", not "zero"


@dataclass
class HourBucket:
    hour: int
    n: int
    avg_speed_ratio: float | None  # None if n == 0

    @property
    def sufficient(self) -> bool:
        return self.n >= MIN_SAMPLES_FOR_PATTERN


_cache: dict = {"mtime": None, "buckets": None}


def _load_buckets(csv_path: str) -> dict[int, HourBucket]:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from forecasting.csv_validator import validate_and_repair
    from datetime import datetime

    clean_rows, _report = validate_and_repair(csv_path)

    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)

    for r in clean_rows:
        if r.get("status") != "OK" or r.get("speed_ratio") is None:
            continue
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        h = ts.hour
        sums[h] += r["speed_ratio"]
        counts[h] += 1

    buckets: dict[int, HourBucket] = {}
    for h in range(24):
        n = counts.get(h, 0)
        avg = (sums[h] / n) if n > 0 else None
        buckets[h] = HourBucket(hour=h, n=n, avg_speed_ratio=avg)

    return buckets


def get_hourly_pattern(csv_path: str) -> dict[int, HourBucket]:
    """Cached (mtime-checked) — recomputes only when the CSV file changes."""
    try:
        mtime = os.path.getmtime(csv_path)
    except OSError:
        return {h: HourBucket(h, 0, None) for h in range(24)}

    if _cache["mtime"] != mtime:
        _cache["buckets"] = _load_buckets(csv_path)
        _cache["mtime"] = mtime

    return _cache["buckets"]


def get_temporal_ratio(csv_path: str, current_hour: int, forecast_hour: int) -> dict:
    """Returns the real ratio between the forecast hour's and the current
    hour's average speed_ratio — i.e. "how much MORE or LESS congested is
    this hour typically, relative to now, based on what was actually
    observed". Only returned when BOTH hours have sufficient real
    samples; otherwise available=False, and the caller must not apply a
    fabricated adjustment."""

    buckets = get_hourly_pattern(csv_path)
    cur = buckets.get(current_hour % 24)
    fut = buckets.get(forecast_hour % 24)

    if cur is None or fut is None or not cur.sufficient or not fut.sufficient:
        return {
            "available": False,
            "current_hour_samples": cur.n if cur else 0,
            "forecast_hour_samples": fut.n if fut else 0,
            "reason": (
                f"insufficient real historical observations for hour "
                f"{current_hour if not (cur and cur.sufficient) else forecast_hour} "
                f"(need >= {MIN_SAMPLES_FOR_PATTERN}, have "
                f"{cur.n if cur else 0} at current hour, {fut.n if fut else 0} at forecast hour)"
            ),
        }

    ratio = fut.avg_speed_ratio / cur.avg_speed_ratio if cur.avg_speed_ratio else None
    return {
        "available": ratio is not None,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "current_hour_avg_speed_ratio": round(cur.avg_speed_ratio, 3),
        "forecast_hour_avg_speed_ratio": round(fut.avg_speed_ratio, 3),
        "current_hour_samples": cur.n,
        "forecast_hour_samples": fut.n,
    }
