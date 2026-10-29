# Bengaluru Brain — Citizen Alert System Audit (Read-Only)
**Date:** 2026-09-29
**Scope:** the existing registration, location, Alerts, Traffic/Waste alert-source, SMS, BHASHINI, USSD, and storage implementation, as it exists today — checked before anything new gets built on top of it.
**Method:** direct inspection of source files on the actual machine (`D:\major project\`, via the linked-device shell), including a keyword search of the whole project tree for `bhashini`, `ussd`, `sms`, `citizen`, and `registration`. No files were created, modified, deleted, moved, renamed, or overwritten.

---

## 0. Top-line answer

There is no user registration, no BHASHINI integration, and no USSD channel anywhere in this codebase — a project-wide search for `bhashini`/`ussd` across every `.py`/`.js`/`.jsx`/`.md` file (excluding `node_modules`/`.venv`/`.git`) returned zero real matches (one `package-lock.json` hash string happened to contain the substring "ussd" — not code). What *does* exist is real and more substantial than "just a mockup": a working, event-driven, bilingual (English + Kannada) alert pipeline with genuine cooldown/deduplication/escalation logic and genuine ephemeral location-based matching — but SMS delivery itself is simulated end-to-end (logged, never sent), "registration" is a session-scoped browser permission grant rather than an account, and there are three separate, non-shared implementations of the Kannada alert text.

| Piece | Status |
|---|---|
| Registration (accounts) | ❌ does not exist — no user accounts, no phone-number opt-in list anywhere |
| Location | ✅ real, but ephemeral/in-memory, session-scoped, not persisted |
| Alerts (Traffic) | ✅ real detector + real eligibility/cooldown logic |
| Alerts (Waste, via USI) | ✅ real fusion + real cooldown/escalation, persisted to disk |
| SMS | ⚠️ real message *generation*, simulated *send* — no provider connected anywhere |
| BHASHINI | ❌ not present anywhere in the codebase |
| USSD | ❌ not present anywhere in the codebase |
| Storage | ⚠️ three different mechanisms, one in-memory/non-persistent, two JSON-file-based |

---

## 1. Registration

**Finding: there is no registration system.** No user accounts, sign-up flow, phone-number database, or subscriber list exists anywhere in `traffic_module`, `waste_module`, or `integration`. What the code calls "registering" a user (`POST /api/traffic/location`'s own docstring: *"Registers/refreshes a browser-consented user's current location"*, `backend/app.py` line 1620) is not an identity registration — it's a session posting its current GPS coordinates under a client-generated `session_id` string, re-sent periodically. There is no login, no name, no email, and (on the traffic side) no phone number collected at all.

The only place a phone number is ever stored is on the **waste** side, and only as a free-text field on a citizen *report*, not a subscription: `citizen_reports_store.add_report()` (`waste_module/waste_module/backend/citizen_reports_store.py`, lines 42–58) accepts an optional `phone_number` string per report and writes it into `waste_module/waste_module/data/citizen_reports.json`. Nothing in the codebase reads that field back out to contact anyone — it's stored, never used for delivery.

## 2. Location

**File:** `traffic_module/backend/user_location_service.py`.

- `update_location(session_id, latitude, longitude)` (lines 33–41) validates coordinates and stores a `UserLocation(session_id, latitude, longitude, last_updated)` in a module-level dict (`_locations`, line 24), guarded by a `threading.Lock`.
- **Never written to disk** — the module's own docstring (lines 1–9) states this explicitly: "locations live only in memory... Restarting the backend clears everything."
- **TTL-based expiry, not deletion on read:** `LOCATION_TTL_SECONDS = 600` (line 22) — `get_active_users()` (lines 55–60) filters to entries updated in the last 10 minutes; a session that stops posting silently ages out rather than being purged or tracked indefinitely.
- **Explicit revoke path:** `remove_location(session_id)` (lines 48–51), wired to `DELETE /api/traffic/location/{session_id}` (`app.py` line 1681) — called when the user revokes browser location permission.
- **API surface:** `POST /api/traffic/location` (`app.py` line 1620) accepts `{session_id, latitude, longitude}`, calls `update_location()`, then immediately matches that one session against currently-open traffic incidents (see §3) and returns only *that session's own* nearby-incident matches — the code and its comments are explicit that one session is never shown another session's location or matches.

This is a real, working mechanism, but it is not what "registration" usually implies — there's no way to alert someone who doesn't currently have a browser tab open sending location pings.

## 3. Alerts — architecture

Two independent alert *sources* feed into the same citizen-facing Alerts tab (`AlertsPanel.jsx`), and the code is explicit that they are kept structurally separate:

```
Traffic module:  detect (traffic_incident_service.py)
                    -> determine eligibility (traffic_alert_eligibility.py)
                    -> record (in-memory, per-segment)
Alerts module:   read what's already been recorded -> display
                    (GET /api/alerts/active -> traffic_alert_eligibility.get_active_traffic_incident_alerts())

Waste+Traffic
combined (USI):  compute_usi() (integration/usi_engine.py)
                    -> generate_alert() + maybe_alert_and_send() (integration/alerts.py)
                    -> record (integration/alert_state.json, on disk)
                    -> GET /api/alerts/{area_name}, GET /api/alerts/active
```

`traffic_alert_eligibility.py`'s own docstring (lines 1–17) is explicit that its eligibility logic "**mirrors the style of** `integration/alert_state.py` — a separate file, that existing module is untouched" — i.e. this is a deliberately duplicated pattern (cooldown + escalation-detection), not a shared library, implemented twice with different persistence choices (in-memory vs. JSON file — see §7).

## 4. Traffic alert source

**File:** `traffic_module/backend/traffic_incident_service.py` (detector) + `traffic_alert_eligibility.py` (eligibility).

- **Classification hierarchy** (`traffic_incident_service.py` lines 104–110): `NORMAL_CONGESTION → HEAVY_CONGESTION → TRAFFIC_ANOMALY → POSSIBLE_TRAFFIC_BLOCKAGE → PROVIDER_CONFIRMED_INCIDENT`. Only the last three (`_ESCALATED_STATES`, line 110) are ever alert-eligible. The module's docstring documents that a road being slow is never itself "an incident" — it compares each observation to a road- and time-of-day-specific baseline, not a global speed threshold.
- **`PROVIDER_CONFIRMED_INCIDENT` is dormant by construction** — the docstring and `GET /api/traffic/incidents`'s own docstring (`app.py` line 1556) both state the TomTom integration has no incident-confirmation endpoint wired up, so this tier never fires; this is disclosed in every API response, not hidden.
- **Eligibility, cooldown, escalation, and location-matching** all live in `traffic_alert_eligibility.py`:
  - `is_alert_eligible()` (lines 65–105): 30-minute cooldown (`COOLDOWN_SECONDS = 1800`), but fires anyway on first detection, severity increase, or the incident's location moving ≥1 km (`LOCATION_CHANGE_KM`).
  - `match_users_to_incident()` (lines 108–144): matches active sessions from `user_location_service.py` to the nearest affected road segment within 2 km (`DEFAULT_MATCH_RADIUS_KM`), returning only distance + matched segment — never another user's raw location.
  - `build_bilingual_alert_message()` (lines 172–181) delegates to `kannada_messages.py`'s `generate_incident_alert()` (see §6) for the English+Kannada text.
- **Wired to two endpoints:** `GET /api/traffic/incidents` (`app.py` line 1556) runs the detector and calls `is_alert_eligible()` per incident on every request; `POST /api/traffic/location` (line 1620) additionally runs `match_users_to_incident()` for the posting session.
- **State is in-memory only:** `traffic_alert_eligibility.py`'s own `_alert_state` dict (line 51) is a module-level dict, not persisted — unlike the USI/waste alert cooldown, which is (see §7).

## 5. Waste alert source (via USI)

Waste doesn't have alert-eligibility logic of its own the way traffic does — waste severity is fused into a single Urban Severity Index per area, and *that* composite score is what actually triggers a citizen alert.

- **`integration/usi_engine.py`**: `compute_usi(area_name)` blends `traffic_signal.get_traffic_severity()` and `waste_signal.get_waste_severity()` into one 0–100 score (weights and band cutoffs in `usi_config.json`, default 50/50 blend, bands Green/Yellow/Orange/Red at 40/60/80). A documented "compounding bonus" (+10, capped at 100) is added when *both* components independently score ≥60 — the code frames this as heavy traffic impeding waste-truck access, not an arbitrary multiplier.
- **`integration/alerts.py`**: `generate_alert(usi_result)` (lines 89–110) turns a USI result into a band-appropriate bilingual message using its own `_TEMPLATES` dict (lines 24–39) — a **separate** template set from `kannada_messages.py` (see §6). `classify_alert_type()` (lines 65–77) additionally flags `URGENT_COMBINED` when both traffic and waste are independently high.
- **Only Yellow/Orange/Red trigger a citizen alert** — `ALERT_BANDS = {"Yellow", "Orange", "Red"}` (line 132); Green is explicitly informational-only and never alerts.
- **Wired to the API via `integration_bridge.py`**: `GET /api/alerts/{area_name}` → `get_alert_for_area()` (`integration_bridge.py` line 149) → `compute_usi()` + `generate_alert()`, and — notably — **also calls `maybe_alert_and_send()`** (the real dedup/cooldown/escalation path, not a raw send) on every hit, with the code comment explaining this is deliberate so that "the real dedup/cooldown and rapid-escalation logic... actually applies to API-triggered alerts too, not just the CLI demo script." In other words: **loading the Alerts tab for an area in the live dashboard genuinely exercises the same cooldown-tracked alert path as the standalone demo script**, and does write to `alert_state.json` (see §7).
- `GET /api/alerts/active` (`app.py` line 1334) is read-only by contrast — it reads `alert_state.json` via `get_active_alerts()` (`integration_bridge.py` line 169) and does not call `maybe_alert_and_send()`.

## 6. SMS

**No SMS provider is connected anywhere in this codebase.** There are, in fact, **three separate, independent implementations** of "the citizen alert message," none of which share code:

1. **`traffic_module/backend/kannada_messages.py`** — `KannadaMessagesService`, template-keyed by route-level status (`LOW/MODERATE/HIGH/SEVERE`) plus a separate `INCIDENT_MESSAGES` dict keyed by the detector's `TRAFFIC_ANOMALY`/`POSSIBLE_TRAFFIC_BLOCKAGE`/`PROVIDER_CONFIRMED_INCIDENT` vocabulary. Used by `traffic_alert_eligibility.build_bilingual_alert_message()` (§4).
2. **`integration/alerts.py`**'s own inline `_TEMPLATES` dict, keyed by USI band (Green/Yellow/Orange/Red), with Kannada composed as a natural sentence via `_compose_reason_kn()` rather than translated word-for-word. Used by `generate_alert()` (§5).
3. **`traffic_module/frontend/src/components/SMSPreview.jsx`** — a third, purely client-side implementation (`generateKannadaSMS`/`generateEnglishSMS`, lines 20–43), with its own hardcoded 10-entry `KANNADA_PLACE_NAMES` lookup (lines 8–18), entirely disconnected from either backend module. This one previews a message for whatever route the user just predicted (`TrafficPredictionPanel`'s `prediction` object), not an area-level USI or incident alert.

**Actual sending, in every case, is simulated:**
- `integration/alerts.py`'s `send_sms_simulated(phone_number, alert)` (lines 122–133) prints a `[SIMULATED SMS]` line to the console and returns `{"status": "SIMULATED_NOT_SENT", ...}`. Its own docstring (lines 1–15) states plainly: *"No real SMS provider is connected (per project rules: never send real SMS or spend money on a provider unless explicitly requested)"* and sketches (as a comment, not working code) where a `twilio_client.messages.create(...)` call would plug in later.
- The `phone_number` passed to it is **never a real, registered number** — every caller (`demo_usi_pipeline.py` line 40, `integration_bridge.get_alert_for_area()` line 149) defaults to the literal string `"+91-SIMULATED"`. There is no code path anywhere that looks up a real citizen's phone number to send to (consistent with §1 — there's nothing to look up).
- **`AlertsPanel.jsx`** labels this correctly in the UI: `"SMS Preview — delivery not configured"` (line ~46) and shows the simulated send log (`to`, `band`, `timestamp`, `status`) or the suppression reason if cooldown blocked it.
- **`SMSPreview.jsx`** also labels itself `"Preview — not sent"` (line ~53), but additionally displays a hardcoded `"Recipients: ~50,000"` and `"Channel: SMS + WhatsApp"` (lines 78–86) — these are **static placeholder numbers baked into the component**, not derived from any real subscriber count (there is no subscriber count anywhere in the codebase — see §1) and not reflecting any actual WhatsApp integration (none exists). Worth flagging explicitly since a "~50,000 recipients" figure reads like a real metric at a glance.

## 7. BHASHINI

**Not present anywhere in the codebase.** A case-insensitive search for `bhashini` across every `.py`, `.js`, `.jsx`, and `.md` file in the project (excluding `node_modules`, `.venv`, `.git`) returned zero matches. All bilingual (English/Kannada) text in this project is hand-written static string templates (three separate implementations — see §6), not machine translation and not India's BHASHINI API. If BHASHINI integration is something to build, it would be new work with no existing scaffold to build on — not a matter of wiring up something partially there.

## 8. USSD

**Not present anywhere in the codebase.** Same search method as §7, same result: one incidental substring match inside a `package-lock.json` integrity hash (not code, not a reference to USSD). There is no USSD gateway, no feature-phone-oriented delivery channel, and no code that assumes a non-smartphone client anywhere in this project. This too would be entirely new work.

## 9. Storage — summary across all of the above

| Data | Mechanism | File | Persisted? | Notes |
|---|---|---|---|---|
| User location (traffic) | In-memory dict + lock | `user_location_service.py` `_locations` | ❌ No — cleared on backend restart | TTL 600s; explicit delete on revoke |
| Traffic-incident alert cooldown/escalation state | In-memory dict + lock | `traffic_alert_eligibility.py` `_alert_state` | ❌ No — cleared on backend restart | Per-segment; independent of #3 below despite near-identical logic |
| USI/waste-band alert cooldown/escalation state | Plain JSON file | `integration/alert_state.json` | ✅ Yes | Per-area; read/written by `alert_state.py`'s `_load()`/`_save()`; 9 areas currently recorded |
| Waste citizen reports (incl. optional phone number) | Plain JSON file | `waste_module/waste_module/data/citizen_reports.json` | ✅ Yes | Append-only via `citizen_reports_store.add_report()`; genuinely read back by the USI engine's citizen-escalation bonus |
| Simulated SMS log | Console `print()` only | — | ❌ No | Not written to any file or database — exists only in process stdout at send time |

There is no database (SQL or otherwise) anywhere in the live path. A **Flask + SQLite** citizen-reporting backend does exist (`waste_module/waste_module/backend/citizen_reporting_backend.py`, with real `/api/reports` POST/GET endpoints and a `ReportValidator`/`ReportProcessor` structure) but `citizen_reports_store.py`'s own docstring states it plainly: that file "cannot even import on this machine (`flask_cors` is not installed) and nothing calls it" — it's dead code, superseded by the plain-JSON-file approach that's actually wired in.

---

## What this audit did not check

I did not exercise any of this at runtime (no server was started) — every finding above comes from static reading of the source on the actual machine. I did not review `traffic_signal.py`/`waste_signal.py` (the two USI input functions) in detail beyond confirming they're what `usi_engine.compute_usi()` calls — their own internal data sourcing wasn't re-audited here since it was outside what was asked. I did not check `waste_module`'s Streamlit dashboard (`enhanced_dashboard.py`) for any alert-related UI beyond what the September 22 Waste Module Audit already covered.
