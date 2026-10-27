"""
Citizen registration + alert-preference storage — Stage 1 foundation only.

This module is deliberately self-contained. It does NOT import, read, or
write any of the existing alert/prediction/USI machinery:
  - traffic_incident_service.py / traffic_alert_eligibility.py (untouched)
  - user_location_service.py (untouched — the existing ephemeral browser
    location mechanism keeps working exactly as it does today)
  - integration/usi_engine.py / integration/alerts.py / alert_state.py
    (untouched)
  - ward_stress.py (untouched)
It only reads (never writes) ward_registry_service.py, to validate that a
citizen-submitted ward_id refers to a real Bengaluru ward — the same
canonical 369-ward registry the rest of this project already uses.

STORAGE: a dedicated SQLite database, data/citizen_alerts.sqlite, owned
exclusively by this module and citizen_otp.py. It is NOT the same file as
any existing JSON store (alert_state.json, citizen_reports.json) and no
existing Traffic/Waste data is read from or written to it.

PRIVACY NOTE (per project instruction): a mobile number never implies a
GPS location. This module stores two separate, optional things:
  - ward_id / ward_name: an explicit, citizen-chosen "my alert area",
    validated against the real ward registry — never fabricated.
  - location_consent: a boolean PREFERENCE the citizen has expressed
    ("I'm willing to share my browser location for alerts"). It does NOT
    store any latitude/longitude. Wiring this preference up to the
    existing ephemeral browser-location mechanism (user_location_service.py)
    is explicitly future work, not done here.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from datetime import datetime
from typing import Optional

import ward_registry_service

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "data", "citizen_alerts.sqlite")

_lock = threading.Lock()
_schema_ready = False

_UPDATABLE_COLUMNS = {
    "preferred_language",
    "traffic_alerts_enabled",
    "waste_alerts_enabled",
    "location_consent",
    "ward_id",
    "ward_name",
    "mobile_verified",
    "status",
}

_MOBILE_RE = re.compile(r"^(?:\+91|91)?([6-9]\d{9})$")

_LANGUAGE_MAP = {
    "en": "en", "english": "en",
    "kn": "kn", "kannada": "kn",
    "hi": "hi", "hindi": "hi",
}
LANGUAGE_LABELS = {"en": "English", "kn": "Kannada", "hi": "Hindi"}


class MobileAlreadyRegistered(Exception):
    """Raised when create_citizen() is called for a mobile number that
    already has a record. Carries the existing citizen dict so the caller
    can decide what to do (e.g. return it in a 409 response)."""

    def __init__(self, existing: dict):
        self.existing = existing
        super().__init__(f"mobile_number already registered as citizen id {existing['id']}")


# ---------------- validation helpers ----------------

def validate_mobile_number(raw: Optional[str]) -> str:
    """Real format validation for an Indian mobile number. Returns the
    normalized +91XXXXXXXXXX form. Raises ValueError with a user-facing
    message on failure."""
    if not raw or not isinstance(raw, str):
        raise ValueError("mobile_number is required")
    cleaned = raw.strip().replace(" ", "").replace("-", "")
    match = _MOBILE_RE.match(cleaned)
    if not match:
        raise ValueError(
            "mobile_number must be a valid 10-digit Indian mobile number, "
            "optionally prefixed with +91 (e.g. +919876543210)"
        )
    return "+91" + match.group(1)


def normalize_language(raw: Optional[str]) -> str:
    """Accepts 'English'/'Kannada'/'Hindi' or 'en'/'kn'/'hi' (any case).
    Returns the internal 'en'/'kn'/'hi' code. Raises ValueError otherwise."""
    if not raw or not isinstance(raw, str):
        raise ValueError("preferred_language is required")
    key = raw.strip().lower()
    if key not in _LANGUAGE_MAP:
        raise ValueError("preferred_language must be one of: English, Kannada, Hindi")
    return _LANGUAGE_MAP[key]


def resolve_ward(ward_id):
    """Validates ward_id against the REAL ward registry
    (ward_registry_service.get_ward(), the same 369-ward canonical source
    ward_stress.py and /api/wards/* already use). Returns (ward_id_str,
    ward_name) or (None, None) if no ward was given (None or ""). Raises
    ValueError if a ward_id was given but doesn't match a real ward — this
    function never fabricates a ward name for an unrecognized id."""
    if ward_id is None:
        return None, None
    ward_id_str = str(ward_id).strip()
    if ward_id_str == "":
        return None, None
    result = ward_registry_service.get_ward(ward_id_str)
    if not result.get("available"):
        raise ValueError(f"'{ward_id_str}' is not a recognized Bengaluru ward id")
    return ward_id_str, result.get("ward_name")


# ---------------- storage ----------------

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # journal_mode=MEMORY (not the sqlite3 default, "DELETE") deliberately
    # avoids ever creating an on-disk rollback-journal file. Some network/
    # virtualized mounts of a project folder don't support the POSIX
    # byte-range locking SQLite's default journal needs, which otherwise
    # surfaces as "disk I/O error" on the very first write -- confirmed
    # while testing this module. Trade-off: a hard crash mid-transaction
    # is not crash-safe the way a real on-disk journal would be; acceptable
    # here (citizen preferences, not financial/critical data) and easy to
    # revisit later if this file ends up on a filesystem that handles
    # locking normally.
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS citizens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile_number TEXT NOT NULL UNIQUE,
            preferred_language TEXT NOT NULL DEFAULT 'en',
            traffic_alerts_enabled INTEGER NOT NULL DEFAULT 0,
            waste_alerts_enabled INTEGER NOT NULL DEFAULT 0,
            location_consent INTEGER NOT NULL DEFAULT 0,
            ward_id TEXT,
            ward_name TEXT,
            mobile_verified INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending_verification',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS citizen_otp_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL,
            mobile_number TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (citizen_id) REFERENCES citizens (id)
        )
        """
    )
    conn.commit()
    _schema_ready = True


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    for key in ("traffic_alerts_enabled", "waste_alerts_enabled", "location_consent", "mobile_verified"):
        d[key] = bool(d[key])
    return d


def create_citizen(
    mobile_number: str,
    preferred_language: str,
    traffic_alerts_enabled: bool,
    waste_alerts_enabled: bool,
    location_consent: bool,
    ward_id: Optional[str],
    ward_name: Optional[str],
) -> dict:
    """Inserts a new citizen row, status='pending_verification',
    mobile_verified=False. Raises MobileAlreadyRegistered if this mobile
    number already has a record (never silently overwrites)."""
    existing = get_citizen_by_mobile(mobile_number)
    if existing is not None:
        raise MobileAlreadyRegistered(existing)

    now = datetime.now().isoformat()
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO citizens (
                    mobile_number, preferred_language, traffic_alerts_enabled,
                    waste_alerts_enabled, location_consent, ward_id, ward_name,
                    mobile_verified, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending_verification', ?, ?)
                """,
                (
                    mobile_number, preferred_language, int(traffic_alerts_enabled),
                    int(waste_alerts_enabled), int(location_consent), ward_id, ward_name,
                    now, now,
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
    return get_citizen(new_id)


def get_citizen(citizen_id) -> Optional[dict]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM citizens WHERE id = ?", (citizen_id,)).fetchone()
        finally:
            conn.close()
    return _row_to_dict(row)


def get_citizen_by_mobile(mobile_number: str) -> Optional[dict]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM citizens WHERE mobile_number = ?", (mobile_number,)
            ).fetchone()
        finally:
            conn.close()
    return _row_to_dict(row)


def update_citizen(citizen_id, **fields) -> Optional[dict]:
    """Partial update. Keys must be a subset of _UPDATABLE_COLUMNS (an
    app.py bug that tried to update anything else raises immediately
    rather than silently doing the wrong thing). Always bumps updated_at."""
    unknown = set(fields) - _UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"cannot update unknown column(s): {sorted(unknown)}")
    if not fields:
        return get_citizen(citizen_id)

    bool_columns = {"traffic_alerts_enabled", "waste_alerts_enabled", "location_consent", "mobile_verified"}
    set_clauses = []
    values = []
    for key, value in fields.items():
        set_clauses.append(f"{key} = ?")
        values.append(int(value) if key in bool_columns else value)
    set_clauses.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(citizen_id)

    with _lock:
        conn = _connect()
        try:
            conn.execute(
                f"UPDATE citizens SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()
    return get_citizen(citizen_id)


def delete_citizen(citizen_id) -> bool:
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM citizens WHERE id = ?", (citizen_id,))
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
    return deleted


# ---------------------------------------------------------------------
# Stage 2 additions -- query functions for citizen_alert_dispatch.py.
# Pure SELECTs only: no new table, no write path, nothing here touches
# cooldown/eligibility state anywhere. Appended after Stage 1's original
# content; nothing above this point was changed.
# ---------------------------------------------------------------------

def list_active_citizens_for_ward(ward_id: str, alert_type: str) -> list[dict]:
    """Verified, active citizens registered to a given real ward_id,
    filtered to those with the matching preference enabled. alert_type
    must be 'traffic' or 'waste' (matches the two preference columns)."""
    if alert_type not in ("traffic", "waste"):
        raise ValueError("alert_type must be 'traffic' or 'waste'")
    if not ward_id:
        return []
    column = "traffic_alerts_enabled" if alert_type == "traffic" else "waste_alerts_enabled"
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM citizens
                WHERE ward_id = ? AND status = 'active' AND mobile_verified = 1 AND {column} = 1
                """,
                (str(ward_id),),
            ).fetchall()
        finally:
            conn.close()
    return [_row_to_dict(r) for r in rows]


def list_active_citizens_with_location_consent() -> list[dict]:
    """Verified, active citizens who have traffic_alerts_enabled, have
    given location_consent (the stored PREFERENCE -- see module
    docstring; no lat/lon is ever stored here), and have a registered
    ward. This is the population traffic-incident dispatch radius-
    matches against, via that ward's real centroid -- never a GPS guess
    from a phone number."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM citizens
                WHERE status = 'active' AND mobile_verified = 1
                  AND traffic_alerts_enabled = 1 AND location_consent = 1
                  AND ward_id IS NOT NULL
                """
            ).fetchall()
        finally:
            conn.close()
    return [_row_to_dict(r) for r in rows]
