"""
Ephemeral, session-scoped user location registry — for matching active,
consenting users to nearby unexpected-traffic incidents. NOT a tracking
system: locations live only in memory (never written to disk), are keyed
by an opaque session identifier the frontend generates itself (no user
account, no persistent identity), and expire automatically after
LOCATION_TTL_SECONDS of no update. Restarting the backend clears
everything. This is the minimum information needed for the *current*
alert session, per the privacy requirement — nothing more.

The frontend only calls this after the browser's own geolocation
permission prompt is explicitly granted by the user (see PART 5 of the
task) — this service has no opinion about that; it just stores whatever
(session_id, lat, lon) it's given and tells the caller when it's stale.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

LOCATION_TTL_SECONDS = 600  # a location not refreshed in 10 minutes is no longer "active"

_lock = threading.Lock()
_locations: dict[str, "UserLocation"] = {}


@dataclass
class UserLocation:
    session_id: str
    latitude: float
    longitude: float
    last_updated: datetime


def update_location(session_id: str, latitude: float, longitude: float) -> UserLocation:
    if not session_id:
        raise ValueError("session_id is required")
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"implausible coordinates: {latitude}, {longitude}")

    loc = UserLocation(session_id=session_id, latitude=latitude, longitude=longitude, last_updated=datetime.now())
    with _lock:
        _locations[session_id] = loc
    return loc


def remove_location(session_id: str) -> None:
    """Called when the user revokes location permission — removes them
    from the active registry immediately rather than waiting for TTL."""
    with _lock:
        _locations.pop(session_id, None)


def get_active_users(ttl_seconds: int = LOCATION_TTL_SECONDS) -> list[UserLocation]:
    """Returns only locations updated within ttl_seconds — a session that
    stops sending updates (tab closed, permission revoked, app closed)
    silently ages out rather than being tracked indefinitely."""
    cutoff = datetime.now() - timedelta(seconds=ttl_seconds)
    with _lock:
        return [loc for loc in _locations.values() if loc.last_updated >= cutoff]


def get_user_location(session_id: str, ttl_seconds: int = LOCATION_TTL_SECONDS) -> Optional[UserLocation]:
    with _lock:
        loc = _locations.get(session_id)
    if loc and loc.last_updated >= datetime.now() - timedelta(seconds=ttl_seconds):
        return loc
    return None


def active_user_count(ttl_seconds: int = LOCATION_TTL_SECONDS) -> int:
    return len(get_active_users(ttl_seconds))
