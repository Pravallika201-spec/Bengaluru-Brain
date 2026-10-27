"""
Real-time data freshness/status reporting — the backbone for the
dashboard's "Last Updated" / "Live vs Simulated" badges (per the
architecture: collectors -> storage -> ... -> API exposing latest
observation + timestamp -> dashboard polling).

Everything here is read from real files on disk; nothing is invented. If a
file is missing/stale, that is reported plainly (STALE/MISSING), never
silently treated as fresh.
"""
import os
from datetime import datetime, timedelta

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LIVE_HISTORY_CSV = os.path.join(DATA_DIR, "live_traffic_history.csv")
MAPPING_CSV = os.path.join(DATA_DIR, "traffic_location_mapping.csv")

# If the most recent collector snapshot is older than this, the feed is
# reported STALE rather than LIVE — collection has evidently stopped.
STALE_AFTER_MINUTES = 30


def get_traffic_data_status():
    """feed_status is always exactly one of:
      LIVE         — a real observation exists and is within STALE_AFTER_MINUTES.
      STALE        — real observations exist on disk, but the newest one is
                     older than that window (collection has evidently stopped).
      NO_LIVE_FEED — no TOMTOM_API_KEY is configured and/or the collector has
                     never produced a file — there is nothing to be stale.
      ERROR        — the collector's output file exists but could not be
                     read/parsed (corrupt CSV, missing expected column, etc.)
                     — distinct from NO_LIVE_FEED because data IS present,
                     just not trustworthy.
    Never LIVE unless a real, freshly-timestamped observation was just read.
    """
    collector_configured = bool(os.environ.get("TOMTOM_API_KEY"))
    status = {
        "collector_configured": collector_configured,
        "mapping_targets": None,
        "mapping_matched": None,
        "history_rows": None,
        "history_unique_snapshots": None,
        "last_observation_timestamp": None,
        "minutes_since_last_observation": None,
        "feed_status": "NO_LIVE_FEED",
    }

    if os.path.exists(MAPPING_CSV):
        try:
            mapping = pd.read_csv(MAPPING_CSV)
            status["mapping_targets"] = int(len(mapping))
            status["mapping_matched"] = int((mapping["status"] == "MATCHED").sum())
        except Exception as e:
            status["mapping_error"] = str(e)

    if not os.path.exists(LIVE_HISTORY_CSV):
        status["reason"] = ("TOMTOM_API_KEY is not set and the collector has never produced a file."
                              if not collector_configured else
                              "live_traffic_history.csv not found — collector has never been run.")
        return status

    try:
        df = pd.read_csv(LIVE_HISTORY_CSV, usecols=["timestamp"])
        if df.empty:
            status["reason"] = "live_traffic_history.csv exists but is empty."
            return status
        status["history_rows"] = int(len(df))
        status["history_unique_snapshots"] = int(df["timestamp"].nunique())
        last_ts = pd.to_datetime(df["timestamp"]).max()
        status["last_observation_timestamp"] = last_ts.isoformat()
        age = datetime.now() - last_ts.to_pydatetime()
        status["minutes_since_last_observation"] = round(age.total_seconds() / 60.0, 1)
        status["feed_status"] = "LIVE" if age <= timedelta(minutes=STALE_AFTER_MINUTES) else "STALE"
    except Exception as e:
        status["feed_status"] = "ERROR"
        status["reason"] = f"Failed to read live_traffic_history.csv: {e}"

    return status
