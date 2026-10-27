"""
Stage 2 -- connects the (Stage 1) citizen registry to the two EXISTING,
already-firing alert sources, and records a per-citizen SIMULATED
delivery for each newly-eligible alert instance.

Deliberately self-contained, same posture as citizen_registry.py /
citizen_otp.py:

  - Never calls is_alert_eligible() (traffic) or maybe_alert_and_send()/
    check_and_update() (USI/waste) -- those are the sole state-mutating
    writers of their own alert engines and, per those modules' own
    docstrings, must only ever be driven by the Traffic module's own
    detection flow / the existing GET /api/alerts/{area} flow. This
    module reads ONLY from their existing read-only accessors:
      - traffic_alert_eligibility.get_active_traffic_incident_alerts()
      - integration_bridge.get_active_alerts() (wraps
        integration/alert_state.py's get_all_state(), itself a pure
        _load() with no write)
    plus integration/usi_engine.compute_usi() and integration/alerts.py's
    generate_alert() / classify_alert_type() -- all PURE functions with
    no side effects (verified by reading them: none writes to
    alert_state.json or anywhere else), safe to call as many times as
    needed purely to build display text.

  - Never sends a real SMS/WhatsApp/BHASHINI/USSD message anywhere --
    every "delivery" recorded here is SIMULATED_NOT_SENT, logged the
    same way the existing send_sms_simulated() already does, generalized
    to a real (registered, consented) citizen's own mobile number
    instead of the hardcoded "+91-SIMULATED" placeholder.

  - Never infers a citizen's GPS location from their phone number.
    Traffic-incident matching uses ONLY a citizen's explicit, registered
    ward_id (resolved to that ward's real centroid via
    ward_registry_service, the same registry citizen_registry.py already
    validates against) compared to the incident's own real segment
    coordinates. USI/waste matching resolves a USI area_name to a ward
    via the existing integration/area_mapping.json join plus the ward
    registry's own waste_area_name / traffic_named_locations fields --
    never a GPS guess, never a raw string equality assumption (area_name
    and ward/waste-area names are NOT always the same string -- see the
    Stage 2 audit, section 1.4).

  - Does not modify traffic_incident_service.py, traffic_alert_
    eligibility.py, user_location_service.py, integration/usi_engine.py,
    integration/alerts.py, integration/alert_state.py,
    integration_bridge.py, ward_stress.py, ward_registry_service.py, or
    any ML/prediction file -- imports and reads only, everywhere.

HINDI GAP, Stage 2 (superseded by Stage 3C below): citizen_registry.py
accepts 'hi' as a preferred_language, but no Hindi message templates
exist anywhere in kannada_messages.py or integration/alerts.py -- only
English and Kannada. Stage 2's original answer was to never silently
send nothing or silently send the wrong language: a Hindi-preferring
citizen was sent the English text with the delivery row stamped
language_fallback="hi_not_yet_supported_sent_en".

STAGE 3C ADDENDUM (BHASHINI translation): a Hindi-preferring citizen's
alert text is now actually run through bhashini_translator.
translate_to_hindi() (the new module; never called for English/Kannada
citizens, which are entirely unaffected by this stage) before falling
back. _resolve_delivery_language() no longer decides the hi case
immediately -- it defers to _record_delivery(), which is the first
place the canonical English text is actually available to translate.
Concretely: language_sent starts as "hi" for a Hindi-preferring citizen;
if BHASHINI is configured and the real translation succeeds, the
delivery is sent in real Hindi with language_sent="hi" and
language_fallback=None; if BHASHINI is not configured, unreachable,
times out, or returns something unusable, the delivery falls back to
English with language_sent="en" and a language_fallback tag that
NAMES the reason (e.g. "hi_bhashini_fallback_sent_en:bhashini_not_configured"),
distinct from Stage 2's old tag because a real attempt is now actually
made, not skipped outright. This is the ONLY behavioral change in this
stage -- eligibility, ward/location matching, cooldown, deduplication,
and the citizen_sms_provider.send_sms() call are all exactly as Stage 3B
left them; bhashini_translator.py has no knowledge of citizens, mobile
numbers, or the SMS provider, and BHASHINI is never called for English
or Kannada citizens.

STORAGE: one new table, citizen_alert_deliveries, in the SAME database
citizen_registry.py already owns (data/citizen_alerts.sqlite) -- same
journal_mode=MEMORY connection pattern citizen_registry.py already uses,
for the same documented reason (this mounted drive doesn't support
SQLite's default rollback-journal locking).

DEDUPLICATION: a citizen is only ever notified once per *alert
instance* -- identified by (citizen_id, alert_source, alert_key,
alert_instance_ts), where alert_instance_ts is the EXISTING alert
engine's own recorded timestamp for that instance (traffic:
get_active_traffic_incident_alerts()'s own last_alert_time; USI: the
same last_alert_time integration/alert_state.json already stores).
citizen_alert_deliveries has a UNIQUE constraint on that 4-tuple and
every insert uses INSERT OR IGNORE, so re-running dispatch while the
same instance is still active can never create a second delivery row
for the same citizen, even under concurrent calls.

STAGE 3B ADDENDUM (SMS provider wiring): _record_delivery() below now
attempts an actual send -- via the new citizen_sms_provider.send_sms()
seam -- but ONLY for a delivery that is genuinely new (i.e. only after
the UNIQUE-constrained INSERT OR IGNORE above proves this citizen has
not already been recorded for this exact alert instance). This
ordering is deliberate: it guarantees a duplicate dispatch run can
never trigger a second real SMS send, not just a second database row.
Nothing about eligibility, ward/location matching, cooldown, or
deduplication changes in this stage -- citizen_sms_provider.py only
decides HOW an already-approved message gets delivered (simulated,
sent, or failed), never WHETHER a citizen is alerted. While
CITIZEN_ALERTS_DEV_MODE is on (the default, unchanged from Stage 1/2),
every delivery is still exactly SIMULATED_NOT_SENT with zero network
calls -- byte-for-byte the same observable behavior as before this
stage.


FINAL FEATURE ADDENDUM (live browser geolocation, SUPPLEMENTS ward
matching -- never replaces it): a registered, consenting citizen's
browser may periodically report their current coordinates to
/api/citizens/{id}/location (app.py), which stores them via the
EXISTING, untouched user_location_service.py -- the same ephemeral,
in-memory, TTL-bound (10 minutes), session-keyed store the pre-
existing /api/traffic/location endpoint already uses for anonymous
browser sessions. Here the "session_id" is simply a deterministic
"citizen:<id>" key (see citizen_location_session_id() below) so a
registered citizen's latest reported position can be looked up by
their citizen_id. Nothing is written to disk; nothing is kept once
it goes stale (no refresh for 10 minutes) or once it is explicitly
removed (consent turned off, citizen deactivated/deleted -- see
remove_live_location_for_citizen() and its callers in app.py).

dispatch_traffic_alerts() is the ONLY place this is consulted: for
each already-qualified citizen (verified, active, traffic_alerts_
enabled, location_consent, registered ward -- exactly
list_active_citizens_with_location_consent()'s existing filter,
unchanged), it now prefers that citizen's fresh live coordinate (if
any) over their ward centroid for the SAME haversine-distance-to-
incident radius check Stage 2 already performed; if no fresh live
coordinate exists (never reported, stale, permission denied/
unavailable, or the browser tab is closed), it falls back to the
EXACT pre-existing ward-centroid behavior, byte-for-byte. USI/waste
dispatch (dispatch_usi_alerts()) is NOT touched by this addendum: it
matches citizens to a USI area via their registered ward_id, not a
radius, so there is nothing for a live coordinate to supplement
there without inventing a new lat/lon-to-ward lookup -- the real
ward registry only has per-ward centroids, not full boundary
polygons for every ward, so any such lookup would risk guessing a
ward rather than reading one, which this project does not do
anywhere else either. Eligibility, cooldown, deduplication, and the
citizen_sms_provider.send_sms() call are all exactly as Stage 3B/3C
left them.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional

import bhashini_translator
import citizen_registry
import citizen_sms_provider
import user_location_service
import ward_registry_service

_lock = threading.Lock()
_schema_ready = False

_AREA_MAPPING_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "integration", "area_mapping.json")
)

_TRAFFIC_HISTORY_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bengaluru_traffic_history.csv")

# Mirrors traffic_alert_eligibility.DEFAULT_MATCH_RADIUS_KM -- imported at
# call time (see dispatch_traffic_alerts) rather than duplicated as a
# literal, so the two can never silently drift apart.
DEFAULT_TRAFFIC_MATCH_RADIUS_KM = 2.0

_LANG_TO_MESSAGE_KEY = {"en": "english", "kn": "kannada"}

# ---------------------------------------------------------------------
# FINAL FEATURE: live browser geolocation lookup (reads ONLY --
# user_location_service.py itself is untouched). See the module
# docstring's "FINAL FEATURE ADDENDUM" above for the full contract.
# ---------------------------------------------------------------------

_LOCATION_SESSION_PREFIX = "citizen:"


def citizen_location_session_id(citizen_id) -> str:
    """The deterministic user_location_service session key for a given
    registered citizen_id. Single source of truth -- app.py's location
    endpoints and this module's own live-location lookup both call this
    rather than each formatting the string themselves."""
    return f"{_LOCATION_SESSION_PREFIX}{citizen_id}"


def _live_location_for_citizen(citizen_id) -> Optional[tuple[float, float]]:
    """Returns (latitude, longitude) from the citizen's most recent
    browser geolocation report, or None if they have never reported one,
    it has gone stale (no refresh within user_location_service's own
    LOCATION_TTL_SECONDS), or the browser permission was denied/
    unavailable. Never fabricates a coordinate -- a None here means
    dispatch_traffic_alerts() falls back to the existing ward-centroid
    behavior, unchanged."""
    loc = user_location_service.get_user_location(citizen_location_session_id(citizen_id))
    if loc is None:
        return None
    return loc.latitude, loc.longitude


def remove_live_location_for_citizen(citizen_id) -> None:
    """Explicit opt-out helper for app.py: called when a citizen turns
    location_consent off, is deactivated/deleted, so the browser's last
    reported position does not linger in memory until the TTL expires on
    its own. A no-op if nothing was stored for this citizen."""
    user_location_service.remove_location(citizen_location_session_id(citizen_id))


# ---------------------------------------------------------------------
# Storage -- own connection to citizen_registry's existing DB file
# ---------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Own connection to citizen_registry.DB_PATH (read dynamically off
    the module, not copied at import time, so tests that monkeypatch
    citizen_registry.DB_PATH transparently redirect this module too).
    Same PRAGMA settings as citizen_registry._connect(), for the same
    reason documented there."""
    conn = sqlite3.connect(citizen_registry.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
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
        CREATE TABLE IF NOT EXISTS citizen_alert_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL,
            alert_source TEXT NOT NULL,        -- 'traffic' | 'usi'
            alert_key TEXT NOT NULL,           -- segment_id (traffic) or area_name (usi)
            alert_instance_ts TEXT NOT NULL,   -- the EXISTING engine's own eligibility timestamp
            language_sent TEXT NOT NULL,       -- 'en' | 'kn'
            language_fallback TEXT,            -- set only for the Hindi gap (see module docstring)
            status TEXT NOT NULL,              -- 'PENDING' | 'SIMULATED_NOT_SENT' | 'SENT' | 'FAILED'
            provider_message_id TEXT,          -- Stage 3B: provider's own message id, when available
            provider_error TEXT,               -- Stage 3B: short error tag on FAILED, else NULL
            delivered_at TEXT NOT NULL,
            FOREIGN KEY (citizen_id) REFERENCES citizens (id),
            UNIQUE (citizen_id, alert_source, alert_key, alert_instance_ts)
        )
        """
    )
    conn.commit()

    # Stage 3B migration: a citizen_alert_deliveries table created by
    # Stage 2 (before provider_message_id/provider_error existed) gets
    # those two nullable columns added in place -- existing rows are
    # untouched (they simply read back with NULL in the new columns),
    # nothing is dropped or rewritten.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(citizen_alert_deliveries)").fetchall()}
    if "provider_message_id" not in existing_cols:
        conn.execute("ALTER TABLE citizen_alert_deliveries ADD COLUMN provider_message_id TEXT")
    if "provider_error" not in existing_cols:
        conn.execute("ALTER TABLE citizen_alert_deliveries ADD COLUMN provider_error TEXT")
    conn.commit()

    _schema_ready = True


def reset_schema_cache() -> None:
    """Test-only helper: forces the next _connect() to re-run CREATE
    TABLE IF NOT EXISTS (needed after a test points citizen_registry.
    DB_PATH at a fresh temp file)."""
    global _schema_ready
    _schema_ready = False


def _resolve_delivery_language(preferred_language: str) -> tuple[str, Optional[str]]:
    """Returns (language_code_used, language_fallback_note) -- the FIRST
    pass, before any BHASHINI attempt. For 'en'/'kn' this is final and
    unchanged from Stage 2: pure pass-through, no fallback. For 'hi' this
    is now only a PROVISIONAL answer ("hi", None) -- the real decision
    (real Hindi via BHASHINI vs. an English fallback) is made by
    _prepare_message_text() below, called from _record_delivery(), which
    is the first point the canonical English text to translate is
    actually available. Only English and Kannada content exists anywhere
    else in this project (kannada_messages.py, integration/alerts.py);
    this is still made visible on every delivery record, never silently
    mis-sent or silently dropped."""
    if preferred_language == "kn":
        return "kn", None
    if preferred_language == "hi":
        return "hi", None
    return "en", None


def _prepare_message_text(
    message: dict, language_sent: str, language_fallback: Optional[str],
) -> tuple[str, str, Optional[str]]:
    """Returns (text_to_send, final_language_sent, final_language_fallback).

    For 'en'/'kn': a pure pass-through, byte-for-byte the same as Stage 2/
    3B -- pulls the matching key out of `message` via _LANG_TO_MESSAGE_KEY
    and returns language_sent/language_fallback unchanged.

    For 'hi' (Stage 3C): the canonical English text is handed to
    bhashini_translator.translate_to_hindi(). A real translation is used
    verbatim, with language_sent staying "hi" and no fallback note. Any
    failure/unavailability (not configured, timeout, connection error,
    bad response -- bhashini_translator itself decides which and never
    raises) falls back to the ORIGINAL English text with language_sent
    downgraded to "en" and a language_fallback tag that names the reason,
    so the gap stays visible in the data exactly like Stage 2's original
    tag did, just now distinguishing "we tried BHASHINI and it didn't
    work" from Stage 2's old "we never even tried"."""
    if language_sent == "hi":
        english_text = message.get("english", "")
        result = bhashini_translator.translate_to_hindi(english_text)
        if result.get("status") == bhashini_translator.STATUS_TRANSLATED:
            return result["text"], "hi", None
        fallback_reason = result.get("error") or "bhashini_unavailable"
        return english_text, "en", f"hi_bhashini_fallback_sent_en:{fallback_reason}"

    text = message.get(_LANG_TO_MESSAGE_KEY.get(language_sent, "english"), "")
    return text, language_sent, language_fallback


def _record_delivery(
    conn: sqlite3.Connection,
    citizen: dict,
    alert_source: str,
    alert_key: str,
    alert_instance_ts: str,
    message: dict,
    language_sent: str,
    language_fallback: Optional[str],
) -> bool:
    """Two-phase, so a real send can never happen for a duplicate:

    Phase 1 (under _lock): INSERT OR IGNORE a row with a transient
    'PENDING' status. The UNIQUE constraint on (citizen_id, alert_source,
    alert_key, alert_instance_ts) means this only actually inserts a row
    the FIRST time this exact alert instance is recorded for this
    citizen; a repeat call (duplicate dispatch) is a true no-op here --
    rowcount is 0, nothing else in this function runs, and no send is
    ever attempted for it.

    Phase 2 (only when phase 1 inserted a new row): attempt delivery via
    citizen_sms_provider.send_sms() -- simulated, real, or failed,
    entirely that module's decision -- then UPDATE this same row from
    'PENDING' to the real outcome. The network call (when one happens)
    deliberately runs OUTSIDE _lock, so one citizen's send can't block
    unrelated inserts for other citizens.

    Returns True only for an actually-new delivery (whatever its final
    status ends up being)."""
    with _lock:
        now = datetime.now().isoformat()
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO citizen_alert_deliveries
                (citizen_id, alert_source, alert_key, alert_instance_ts,
                 language_sent, language_fallback, status, delivered_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (citizen["id"], alert_source, alert_key, alert_instance_ts,
             language_sent, language_fallback, now),
        )
        conn.commit()
        is_new = cur.rowcount > 0
        row_id = cur.lastrowid if is_new else None

    if not is_new:
        return False

    # Stage 3C: this is the first point the canonical English text is
    # available, so this is where a Hindi-preferring citizen's real
    # translate-or-fallback decision actually happens (see
    # _prepare_message_text's own docstring). For 'en'/'kn' this is a
    # pure pass-through, unchanged from Stage 2/3B.
    text, final_language, final_fallback = _prepare_message_text(message, language_sent, language_fallback)

    try:
        send_result = citizen_sms_provider.send_sms(citizen["mobile_number"], text, final_language)
    except Exception as exc:
        # citizen_sms_provider.send_sms() already catches its own
        # expected failure modes and returns a FAILED dict for them --
        # this is only a last-resort safety net so a truly unexpected
        # error there can never leave this row stuck at 'PENDING' or
        # crash the whole dispatch run.
        send_result = {
            "status": citizen_sms_provider.STATUS_FAILED,
            "provider_message_id": None,
            "error": f"unexpected_error:{type(exc).__name__}",
        }

    status = send_result.get("status") or citizen_sms_provider.STATUS_FAILED
    provider_message_id = send_result.get("provider_message_id")
    provider_error = send_result.get("error")

    with _lock:
        conn.execute(
            """
            UPDATE citizen_alert_deliveries
            SET status = ?, provider_message_id = ?, provider_error = ?,
                language_sent = ?, language_fallback = ?
            WHERE id = ?
            """,
            (status, provider_message_id, provider_error, final_language, final_fallback, row_id),
        )
        conn.commit()

    fallback_note = f" (fallback: {final_fallback})" if final_fallback else ""
    print(
        f"[CITIZEN ALERT DELIVERY] to={citizen['mobile_number']} citizen_id={citizen['id']} "
        f"source={alert_source} key={alert_key} lang={final_language}{fallback_note} status={status}\n  {text}"
    )
    return True


# ---------------------------------------------------------------------
# Ward resolution -- real data only, never fabricated
# ---------------------------------------------------------------------

_ward_index_cache = {"by_waste_area": None, "by_traffic_location": None}


def _ward_lookup_indexes():
    """Reverse indexes built from the REAL ward registry (the same
    source citizen_registry.resolve_ward() already validates against):
    waste_area_name -> ward_id, and each of a ward's own real
    traffic_named_locations -> ward_id. Built once per process, from
    real data only."""
    if _ward_index_cache["by_waste_area"] is not None:
        return _ward_index_cache["by_waste_area"], _ward_index_cache["by_traffic_location"]

    by_waste_area: dict[str, str] = {}
    by_traffic_location: dict[str, str] = {}
    all_wards = ward_registry_service.get_all_wards()
    if all_wards.get("available"):
        for w in all_wards["wards"]:
            if w.get("waste_area_name"):
                by_waste_area[w["waste_area_name"]] = str(w["ward_id"])
            for loc in (w.get("traffic_named_locations") or []):
                by_traffic_location[loc] = str(w["ward_id"])

    _ward_index_cache["by_waste_area"] = by_waste_area
    _ward_index_cache["by_traffic_location"] = by_traffic_location
    return by_waste_area, by_traffic_location


def reset_ward_index_cache() -> None:
    """Test-only helper."""
    _ward_index_cache["by_waste_area"] = None
    _ward_index_cache["by_traffic_location"] = None


def _load_area_mapping() -> dict:
    """The REAL traffic-location -> waste-area join, exactly as
    instructed -- integration/area_mapping.json, never re-derived or
    approximated here."""
    if not os.path.exists(_AREA_MAPPING_PATH):
        return {}
    try:
        with open(_AREA_MAPPING_PATH, encoding="utf-8") as f:
            return json.load(f).get("mapping", {})
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_ward_ids_for_usi_area(area_name: str) -> list[str]:
    """area_name here is whatever GET /api/alerts/{area_name} (and
    therefore usi_engine.compute_usi) was called with -- typically a
    traffic-location-style name, per usi_engine.compute_usi's own area_
    mapping lookup. A citizen's ward_name is NOT assumed to equal a USI
    area_name (see Stage 2 audit, section 1.4: e.g. the traffic location
    "Silk Board" maps to the "Madiwala" waste/USI area, 0.72km apart).
    Resolution order, all from real, already-existing data:
      1. area_name matches a ward's own real traffic_named_locations.
      2. area_mapping.json's real join gives a waste_area_name, matched
         against a ward's real waste_area_name.
      3. area_name matches a ward's waste_area_name directly (covers the
         exact-name case, e.g. area_name == 'Hebbal').
    Returns [] -- never a guess -- if none apply."""
    by_waste_area, by_traffic_location = _ward_lookup_indexes()
    ward_ids: set[str] = set()

    if area_name in by_traffic_location:
        ward_ids.add(by_traffic_location[area_name])

    mapping = _load_area_mapping()
    entry = mapping.get(area_name)
    if entry and entry.get("waste_area_name") in by_waste_area:
        ward_ids.add(by_waste_area[entry["waste_area_name"]])

    if area_name in by_waste_area:
        ward_ids.add(by_waste_area[area_name])

    return sorted(ward_ids)


# ---------------------------------------------------------------------
# Dispatch: traffic incidents
# ---------------------------------------------------------------------

def dispatch_traffic_alerts() -> dict:
    """Reads ALREADY-recorded traffic-incident alert eligibility (never
    computes it -- see module docstring) and simulated-delivers to every
    verified, active citizen who (a) has traffic_alerts_enabled, (b) has
    given location_consent, and (c) is within DEFAULT_TRAFFIC_MATCH_RADIUS_KM
    of the nearest affected segment's REAL coordinates -- using a fresh
    live browser coordinate when the citizen has reported one (FINAL
    FEATURE addendum, see module docstring), otherwise falling back to
    their registered ward's real centroid, exactly as before. Never a
    phone-number-inferred location, never a fabricated coordinate."""
    from traffic_alert_eligibility import get_active_traffic_incident_alerts, DEFAULT_MATCH_RADIUS_KM
    from traffic_incident_service import haversine_km, analyze_all_segments, load_recent_observations_from_csv

    result = {
        "incidents_checked": 0, "citizens_matched": 0,
        "citizens_notified": 0, "citizens_skipped_dedup": 0, "details": [],
    }

    incidents = get_active_traffic_incident_alerts()  # read-only
    result["incidents_checked"] = len(incidents)
    if not incidents:
        return result

    # get_active_traffic_incident_alerts() doesn't itself return lat/lon
    # -- re-derive real segment coordinates from the same real detector
    # output it was built from (never fabricated, never guessed).
    coords_by_segment = {}
    if os.path.exists(_TRAFFIC_HISTORY_CSV):
        by_segment = load_recent_observations_from_csv(_TRAFFIC_HISTORY_CSV)
        for r in analyze_all_segments(by_segment):
            if r.get("latitude") is not None and r.get("longitude") is not None:
                coords_by_segment[r["segment_id"]] = (r["latitude"], r["longitude"])

    citizens = citizen_registry.list_active_citizens_with_location_consent()
    if not citizens:
        return result

    conn = _connect()
    try:
        for incident in incidents:
            seg_id = incident["segment_id"]
            loc = coords_by_segment.get(seg_id)
            if loc is None:
                continue  # no real coordinates for this segment -- never guess

            for citizen in citizens:
                # FINAL FEATURE: prefer a fresh live browser coordinate
                # over the ward centroid when one is available (see
                # _live_location_for_citizen()'s docstring) -- the ward-
                # centroid path below is otherwise completely unchanged
                # from Stage 2, including when live_location is None.
                live_location = _live_location_for_citizen(citizen["id"])
                if live_location is not None:
                    citizen_lat, citizen_lon = live_location
                    location_source = "live_gps"
                else:
                    ward = ward_registry_service.get_ward(citizen["ward_id"])
                    if not ward.get("available"):
                        continue
                    citizen_lat, citizen_lon = ward["centroid_lat"], ward["centroid_lon"]
                    location_source = "ward_centroid"

                dist = haversine_km(loc[0], loc[1], citizen_lat, citizen_lon)
                if dist > DEFAULT_MATCH_RADIUS_KM:
                    continue

                result["citizens_matched"] += 1
                lang, fallback = _resolve_delivery_language(citizen["preferred_language"])
                is_new = _record_delivery(
                    conn, citizen, "traffic", seg_id, incident["last_alert_time"],
                    {"english": incident["english"], "kannada": incident["kannada"]},
                    lang, fallback,
                )
                result["citizens_notified" if is_new else "citizens_skipped_dedup"] += 1
                result["details"].append({
                    "citizen_id": citizen["id"], "segment_id": seg_id,
                    "distance_km": round(dist, 2), "new_delivery": is_new,
                    "location_source": location_source,
                })
    finally:
        conn.close()
    return result


# ---------------------------------------------------------------------
# Dispatch: USI / waste bands
# ---------------------------------------------------------------------

def dispatch_usi_alerts() -> dict:
    """Reads ALREADY-active USI/waste-band alerts via the existing
    read-only accessor (integration_bridge.get_active_alerts(), which
    itself only reads alert_state.get_all_state() -- never calls
    check_and_update() or maybe_alert_and_send()). Recomputes the full
    USI result via compute_usi() (pure, no side effects -- the exact
    same call get_active_alerts() itself already makes, purely for its
    own "reason" text) only to build the citizen-facing message via the
    existing generate_alert()/classify_alert_type()."""
    import integration_bridge  # importing this also puts integration/ on sys.path, as it already does for its own use

    result = {
        "areas_checked": 0, "citizens_matched": 0,
        "citizens_notified": 0, "citizens_skipped_dedup": 0, "details": [],
    }

    active = integration_bridge.get_active_alerts()  # read-only
    if not active.get("available"):
        # Same graceful-degradation contract integration_bridge itself
        # uses (e.g. a missing optional dependency on this machine) --
        # never a crash, never a fabricated result.
        result["unavailable_reason"] = active.get("reason")
        return result

    # Only imported once we know integration_bridge already loaded these
    # successfully (get_active_alerts() returned available=True implies
    # integration_bridge._ensure_loaded() already succeeded) -- these two
    # module-level imports are then guaranteed cache hits, never a second
    # real import attempt that could fail independently.
    import usi_engine
    import alerts as usi_alerts_module

    conn = _connect()
    try:
        for area in active["alerts"]:
            area_name = area["area_name"]
            instance_ts = area.get("last_alert_time")
            result["areas_checked"] += 1
            if not instance_ts:
                continue

            ward_ids = resolve_ward_ids_for_usi_area(area_name)
            if not ward_ids:
                continue

            usi_result = usi_engine.compute_usi(area_name)  # pure, no side effects
            alert_type = usi_alerts_module.classify_alert_type(usi_result)
            message = usi_alerts_module.generate_alert(usi_result)

            for ward_id in ward_ids:
                traffic_recipients = (
                    citizen_registry.list_active_citizens_for_ward(ward_id, "traffic")
                    if alert_type in ("TRAFFIC_ONLY", "URGENT_COMBINED", "GENERAL") else []
                )
                waste_recipients = (
                    citizen_registry.list_active_citizens_for_ward(ward_id, "waste")
                    if alert_type in ("WASTE_ONLY", "URGENT_COMBINED", "GENERAL") else []
                )

                seen_citizen_ids: set = set()
                for citizen, matched_because in (
                    [(c, "traffic_alerts_enabled") for c in traffic_recipients]
                    + [(c, "waste_alerts_enabled") for c in waste_recipients]
                ):
                    if citizen["id"] in seen_citizen_ids:
                        continue  # subscribed to both signals -- one delivery, not two
                    seen_citizen_ids.add(citizen["id"])

                    result["citizens_matched"] += 1
                    lang, fallback = _resolve_delivery_language(citizen["preferred_language"])
                    is_new = _record_delivery(
                        conn, citizen, "usi", area_name, instance_ts, message, lang, fallback,
                    )
                    result["citizens_notified" if is_new else "citizens_skipped_dedup"] += 1
                    result["details"].append({
                        "citizen_id": citizen["id"], "area_name": area_name, "ward_id": ward_id,
                        "alert_type": alert_type, "matched_because": matched_because, "new_delivery": is_new,
                    })
    finally:
        conn.close()
    return result


# ---------------------------------------------------------------------
# Orchestration + per-citizen read for the My Alerts panel
# ---------------------------------------------------------------------

def run_dispatch() -> dict:
    """The single state-mutating entry point Stage 2 exposes over HTTP
    (POST /api/citizens/dispatch/run calls only this)."""
    traffic_result = dispatch_traffic_alerts()
    usi_result = dispatch_usi_alerts()
    return {
        "traffic": traffic_result,
        "usi": usi_result,
        "citizens_notified_total": traffic_result["citizens_notified"] + usi_result["citizens_notified"],
        "run_at": datetime.now().isoformat(),
    }


def get_deliveries_for_citizen(citizen_id: int, limit: int = 20) -> list[dict]:
    """Pure read of this citizen's own simulated-delivery history --
    truthful status for the My Alerts panel. Never another citizen's
    data, never a fabricated aggregate subscriber/delivery count."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM citizen_alert_deliveries
            WHERE citizen_id = ?
            ORDER BY delivered_at DESC
            LIMIT ?
            """,
            (citizen_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
