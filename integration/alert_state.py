"""
Persistent per-area alert state — enables:
  1. Rapid-escalation detection (compare current USI to the last recorded
     one for that area).
  2. Deduplication/cooldown (don't re-fire the same-band alert for the same
     area more than once per COOLDOWN_MINUTES).

Plain JSON file, no external service — matches the project's "don't build
an unnecessarily complicated distributed system" guidance while still being
real, working state (not simulated).
"""
import json
import os
import threading
from datetime import datetime, timedelta

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_state.json")
COOLDOWN_MINUTES = 30
ESCALATION_THRESHOLD = 15.0  # USI points jumped since the last check = "rapid escalation"

_lock = threading.Lock()


def _load():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def check_and_update(area_name, usi_value, band):
    """Returns (should_alert: bool, alert_reason_tags: list[str], is_escalation: bool)
    and records this observation for next time. Called once per USI
    computation that reaches an alertable band."""
    with _lock:
        state = _load()
        prev = state.get(area_name)
        now = datetime.now()

        is_escalation = False
        if prev and usi_value is not None and prev.get("usi") is not None:
            if usi_value - prev["usi"] >= ESCALATION_THRESHOLD:
                is_escalation = True

        should_alert = True
        reason_tags = []
        if prev:
            last_time = datetime.fromisoformat(prev["last_alert_time"])
            same_band = prev.get("band") == band
            within_cooldown = (now - last_time) < timedelta(minutes=COOLDOWN_MINUTES)
            if same_band and within_cooldown and not is_escalation:
                should_alert = False
                reason_tags.append("deduplicated: same band within cooldown window")

        if is_escalation:
            reason_tags.append(f"rapid escalation: USI rose {usi_value - prev['usi']:.1f} points since last check")

        if should_alert:
            state[area_name] = {"usi": usi_value, "band": band, "last_alert_time": now.isoformat()}
            _save(state)

        return should_alert, reason_tags, is_escalation


def get_all_state():
    return _load()
