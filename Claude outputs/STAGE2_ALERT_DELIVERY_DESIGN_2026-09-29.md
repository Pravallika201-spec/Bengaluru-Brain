# Stage 2 — Alert Delivery to Registered Citizens — Audit + Design
**Date:** 2026-09-29
**Scope:** (1) audit the *current* state of the citizen registry (post Stage 1) and the existing alert architecture, as they actually stand on disk right now; (2) design — not yet build — how a fired alert (traffic incident or USI/waste band) reaches the citizens who registered for it, without modifying any existing alert/prediction file.
**Method:** direct inspection of source on the actual machine (`D:\major project\`, via the linked-device shell). No files were created, modified, deleted, or moved.

---

## Part 1 — Current-state audit (post Stage 1)

### 1.1 The registry is real but completely disconnected from delivery

`citizen_registry.py` and `citizen_otp.py` (built in Stage 1) are imported **only** by `app.py` — confirmed by a project-wide search (excluding `.venv`/`node_modules`/`.git`/`__pycache__`) for `citizen_registry|citizen_otp` across `traffic_module/backend`, `integration`, and `traffic_module/frontend/src`. The only hits are the two new modules themselves, `app.py`, the new test file, the new SQLite file, and the new `CitizenAlertRegistration.jsx`. Nothing in `traffic_alert_eligibility.py`, `integration/alerts.py`, `integration_bridge.py`, or anywhere else reads from the citizens table. This matches `citizen_registry.py`'s own docstring, which states outright that it does not import or touch the alert machinery. So today: a citizen can register, verify, and set preferences, but **no alert of any kind will ever reach them** — registering currently has no observable downstream effect.

### 1.2 The registry has no query surface for "who should get this alert"

`citizen_registry.py` currently exposes only `create_citizen`, `get_citizen`, `get_citizen_by_mobile`, `update_citizen`, `delete_citizen` — all single-row, id/mobile-keyed lookups. There is no `list_citizens_for_ward(...)`, no `list_active_citizens(...)`, nothing that returns "every verified, active citizen subscribed to traffic alerts in ward X." That query capability doesn't exist yet and has to be added before any dispatch logic can run.

### 1.3 Two independent alert sources, two independent state machines — both already have a safe *read-only* accessor

- **Traffic incidents:** `traffic_alert_eligibility.is_alert_eligible()` is the only writer of `_alert_state` (in-memory, per-segment). It is invoked from exactly one place — `GET /api/traffic/incidents` in `app.py`. `get_active_traffic_incident_alerts()` is the existing **read-only** accessor, and its own docstring is explicit about why: *"Deliberately never calls `is_alert_eligible()` itself... must only ever be driven by the Traffic module's own detection flow."*
- **USI/waste bands:** `alert_state.check_and_update()` is the only writer of `integration/alert_state.json`'s cooldown/escalation state, invoked from exactly one place — `integration/alerts.py`'s `maybe_alert_and_send()`, itself called from `integration_bridge.get_alert_for_area()` (i.e. every time `GET /api/alerts/{area}` is hit). `GET /api/alerts/active` instead reads the same file read-only via `get_active_alerts()`, never calling `maybe_alert_and_send()`.

**This is the load-bearing fact for the Stage 2 design below:** both alert sources already draw a hard line between "the one flow allowed to mutate cooldown state" and "everything else, which only reads what's already been recorded." Citizen dispatch has to land on the read-only side of that line in both cases, or it will double-fire escalation detection / corrupt cooldown timing for the *existing* dashboard the moment two things poll it.

### 1.4 Geo data needed for ward-based matching already exists and is usable

`integration/geo/ward_registry.json` (via `ward_registry_service.get_ward()`, already used and validated by `citizen_registry.resolve_ward()`) carries `centroid_lat`/`centroid_lon` per ward — e.g. R.T Nagar: `13.0254245, 77.5980335`. That's enough to do a distance check between a traffic incident's real segment coordinates and a citizen's registered ward centroid, using the exact same `haversine_km()` helper `traffic_alert_eligibility.py` already imports from `traffic_incident_service.py` — no new geo library needed.

`integration/area_mapping.json` shows USI's `area_name` and a ward's `ward_name` are the same string for many areas (`Hebbal` ↔ `Hebbal`, `Whitefield` ↔ `Whitefield`) but not all (`Silk Board` traffic location maps to `Madiwala` waste/USI area, 0.72 km apart, `match_type: spatial_nearest`). So **a citizen's `ward_name` cannot be assumed to equal a USI `area_name` string-for-string** — matching has to go through this existing mapping (or the shared ward id/centroid), not a naive string comparison.

### 1.5 A real content gap: Hindi is accepted at registration but doesn't exist anywhere downstream

`citizen_registry.normalize_language()` accepts and stores `'hi'` (Hindi) as a valid `preferred_language`, with `LANGUAGE_LABELS = {"en": "English", "kn": "Kannada", "hi": "Hindi"}`. But a search of both message-generating modules — `kannada_messages.py` and `integration/alerts.py` — for `hindi`/`Hindi`/`'hi'` returns **zero matches in either file**. Every alert message this project can currently generate is English or Kannada only. A citizen who registers with Hindi as their preference today would, under any naive "send in `preferred_language`" logic, receive nothing, or silently receive the wrong language. This has to be an explicit decision in the dispatch design, not an oversight discovered later.

### 1.6 Storage engineering note carried forward

`citizen_registry._connect()` already runs with `PRAGMA journal_mode=MEMORY` because the mounted drive doesn't support SQLite's default rollback-journal locking (documented in Stage 1). Any new table added to this same database inherits that same constraint automatically — no new fix needed, just something to keep in mind (a hard crash mid-write to the new delivery-log table isn't crash-safe, same as the citizens table today).

---

## Part 2 — Stage 2 design: connecting the registry to both alert sources

### 2.1 Non-negotiables carried over from Stage 1's own rules

- No real SMS provider, no real send, anywhere — every delivery in this design is a `SIMULATED_NOT_SENT`-style record, same shape as the existing ones.
- `traffic_incident_service.py`, `traffic_alert_eligibility.py`, `user_location_service.py`, `integration/usi_engine.py`, `integration/alerts.py`, `integration/alert_state.py`, `integration_bridge.py`, `ward_stress.py`, `kannada_messages.py` stay **untouched** — Stage 2 only ever *imports and reads* from them, exactly like Stage 1 did with `ward_registry_service.py`.
- Additive only: new functions get appended to `citizen_registry.py` (Stage 2's own prior work, not project-original code, so extending it in place is fine) and one new module; `app.py` gets one more clean insertion block, same pattern as Stage 1's diff.

### 2.2 New read functions to add to `citizen_registry.py`

```python
def list_active_citizens_for_ward(ward_id: str, alert_type: str) -> list[dict]:
    """alert_type: 'traffic' or 'waste'. Returns verified, active citizens
    whose ward_id matches and whose corresponding *_alerts_enabled is true."""

def list_active_citizens_with_location_consent() -> list[dict]:
    """For traffic-incident radius matching against a citizen's ward
    centroid, independent of the ephemeral browser-location mechanism."""
```

Both are pure `SELECT`s against the existing `citizens` table (`status='active' AND mobile_verified=1 AND ...`) — no schema change needed for these two.

### 2.3 New module: `traffic_module/backend/citizen_alert_dispatch.py`

Two entry points, one per alert source, both **read-only** with respect to the existing modules' own state:

**`dispatch_traffic_alerts()`**
1. Calls the existing `traffic_alert_eligibility.get_active_traffic_incident_alerts()` — the read-only accessor from §1.3. Never calls `is_alert_eligible()` itself.
2. For each already-recorded eligible incident, resolves its real segment lat/lon (already present on the incident dict).
3. Calls `citizen_registry.list_active_citizens_with_location_consent()`, then for each citizen, looks up their ward's `centroid_lat`/`centroid_lon` via `ward_registry_service.get_ward(citizen["ward_id"])`, and reuses `traffic_incident_service.haversine_km()` to check it's within a radius (reuse `traffic_alert_eligibility.DEFAULT_MATCH_RADIUS_KM = 2.0` as the default, imported not duplicated).
4. Builds the message via the existing `traffic_alert_eligibility.build_bilingual_alert_message()` — already returns `{english, kannada}`.
5. Hands off to the dedup + simulated-send step (§2.5).

**`dispatch_usi_alerts(area_name: str)`** — called once per area, same trigger points that already call `get_alert_for_area()` today would eventually call this too (wiring that call site is the one place `app.py` gets touched — see §2.6), but the function itself never calls `maybe_alert_and_send()`:
1. Calls `integration.alert_state.get_active_alerts()` (existing read-only accessor from §1.3) to find out if `area_name` currently has an active, alert-band record, and what band/timestamp it's at.
2. If so, resolves `area_name` → the matching ward(s) using `integration/area_mapping.json`'s existing mapping (not a string match — see §1.4), to get the real `ward_id`(s) to query citizens against.
3. Calls `citizen_registry.list_active_citizens_for_ward(ward_id, "waste")` (and separately `"traffic"` if the alert_type from `classify_alert_type()` is `URGENT_COMBINED`).
4. Builds the message by calling the existing, pure `integration.alerts.generate_alert(usi_result)` — safe to call repeatedly since it has no side effects itself (only `maybe_alert_and_send` mutates state, and this design never calls it).
5. Hands off to §2.5.

### 2.4 The Hindi gap, resolved explicitly (not silently)

Per §1.5, until Hindi templates exist in `kannada_messages.py`/`integration/alerts.py`, dispatch will: send English to a `preferred_language='hi'` citizen, and stamp the delivery record with `"language_fallback": "hi_not_yet_supported_sent_en"`. This keeps the gap visible in the data rather than pretending Hindi delivery works. Building real Hindi templates is flagged as separate follow-on work, not silently bundled into this design.

### 2.5 Per-citizen dedup and the simulated send — new table

Because both `get_active_traffic_incident_alerts()` and `get_active_alerts()` return "whatever is *currently* recorded as eligible," and that record persists unchanged across many reads until the next escalation/cooldown-expiry, dispatch has to avoid re-notifying the same citizen every time it runs while the same alert instance is still active. Each existing alert record already carries a timestamp of when *that instance* became eligible (`_AlertRecord.last_alert_time` / `alert_state.json`'s own stored timestamp) — that timestamp is the natural instance id.

New table, same database (`data/citizen_alerts.sqlite`), same `journal_mode=MEMORY` connection helper already in `citizen_registry.py`:

```sql
CREATE TABLE citizen_alert_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citizen_id INTEGER NOT NULL,
    alert_source TEXT NOT NULL,       -- 'traffic' | 'waste'
    alert_key TEXT NOT NULL,          -- segment_id (traffic) or area_name (waste)
    alert_instance_ts TEXT NOT NULL,  -- the existing module's own eligibility timestamp
    language_sent TEXT NOT NULL,
    language_fallback TEXT,           -- set only per §2.4
    status TEXT NOT NULL,             -- 'SIMULATED_NOT_SENT' (mirrors existing send_sms_simulated shape)
    delivered_at TEXT NOT NULL,
    FOREIGN KEY (citizen_id) REFERENCES citizens (id)
);
```

Before sending, dispatch checks `(citizen_id, alert_source, alert_key, alert_instance_ts)` for an existing row — if found, skip (already notified for this exact instance); if not, record a simulated send (reusing the *pattern* of `send_sms_simulated`/`[SIMULATED SMS]` console logging, generalized to take a citizen's real mobile number from the registry instead of the hardcoded `"+91-SIMULATED"`) and insert the row.

### 2.6 The one touch point in `app.py`

A single new, additive endpoint — same style as Stage 1's insertion block, added once, nothing existing edited:

```
POST /api/citizens/dispatch/run
```
Runs both `dispatch_traffic_alerts()` and, for every area with a currently-active alert per `get_active_alerts()`, `dispatch_usi_alerts(area_name)`; returns a summary (`citizens_matched`, `citizens_notified`, `citizens_skipped_dedup`, per source). This is deliberately a manually/externally triggerable endpoint (or wire-able to a scheduler later) rather than being folded into the existing `GET /api/traffic/incidents` / `GET /api/alerts/{area}` handlers — folding it in would mean every citizen-facing dashboard page load also triggers a dispatch pass, which is a product decision (and a rate-limiting concern) that belongs in a later, explicit follow-on, not silently decided here.

### 2.7 What Stage 2 still does not do (by design, same posture as Stage 1)

No real SMS provider connection, no BHASHINI, no USSD, no Hindi content (flagged, not built), and it does not touch the ephemeral browser-location mechanism (`user_location_service.py`) — ward-centroid matching is used for registered citizens instead, exactly as Stage 1's docstring already flagged as the deferred item.

---

## What this covers and what it doesn't

This is a design, not a build — no code has been written yet under this task. Everything above was checked against the real files on `D:\major project\` as they exist right now (not from memory of the Stage 1 build). The next step, if you want it built, is implementing `citizen_alert_dispatch.py` + the two new `citizen_registry.py` functions + the one new table + the one new endpoint, exactly as scoped above, with the same before/after diff verification and untouched-file mtime proof Stage 1 used.
