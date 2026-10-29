# Stage 1 — Citizen Registration & Alert Preferences — Build Report
**Date:** 2026-09-29
**Scope:** foundation only — citizen subscription storage, mobile validation, dev-only OTP, and the `/api/citizens/*` API + a citizen-facing registration/preferences panel. No SMS provider, BHASHINI, or USSD implemented, as instructed.

---

## 1. Guardrails — confirmed untouched

Every file this task said not to modify keeps its original modification time from before this session started (verified with `stat` after the build, not just assumed):

| File/folder | Last modified (unchanged) |
|---|---|
| `friend_waste/` (whole directory) | 2026-09-22 |
| `waste_module/` (whole directory) | 2026-09-22 |
| `traffic_module/backend/gnn_model.py` | 2026-08-30 |
| `traffic_module/backend/real_gnn_service.py` | 2026-09-03 |
| `traffic_module/backend/routing_service.py` | 2026-09-02 |
| `traffic_module/backend/traffic_incident_service.py` | 2026-09-11 |
| `traffic_module/backend/traffic_alert_eligibility.py` | 2026-09-11 |
| `traffic_module/backend/user_location_service.py` | 2026-09-10 |
| `traffic_module/backend/ward_stress.py` | 2026-09-03 |
| `integration/usi_engine.py` | 2026-09-03 |
| `integration/alerts.py` | 2026-09-03 |
| `integration/alert_state.py` / `alert_state.json` | 2026-09-03 / earlier today (before this task) |
| `integration/waste_signal.py` | 2026-09-03 |

No ML/model file, no Traffic or Waste prediction code, no USI calculation code, and no existing alert-detection module was opened for editing at any point in this build. `ward_registry_service.py` was only ever **imported and read** (to validate a citizen's chosen ward against the real registry) — never modified.

---

## 2. Files created (new)

| File | Lines | Purpose |
|---|---|---|
| `traffic_module/backend/citizen_registry.py` | 304 | SQLite storage, mobile/language/ward validation, CRUD (create/get/update/delete) |
| `traffic_module/backend/citizen_otp.py` | 121 | Dev-only OTP generation/verification (no real SMS) |
| `traffic_module/backend/tests/test_citizen_registry.py` | 283 | Pytest suite: storage, validation, OTP, and full HTTP round-trip |
| `traffic_module/frontend/src/components/CitizenAlertRegistration.jsx` | 569 | Citizen-facing registration/preferences panel |
| `traffic_module/backend/data/citizen_alerts.sqlite` | — | The new database file itself (schema created, currently empty — no test data left in it) |

## 3. Files modified (existing)

All three were backed up **before** any edit (see §4), and every diff below was verified against that backup — not just described from memory.

| File | Change | Verified diff |
|---|---|---|
| `traffic_module/backend/app.py` | +188 lines, 0 removed/changed. Added: 3 import lines + a single new block (6 endpoints + request models) inserted right before the `if __name__ == "__main__":` block. | `diff` against backup: 0 lines on the `<` side, 188 on the `>` side |
| `traffic_module/frontend/src/App.js` | +4 lines, 0 removed/changed. Added: 1 import, 1 `TABS` entry (`my-alerts`), 1 render line for the new tab. | `diff` against backup: 0 lines removed, 4 added |
| `traffic_module/frontend/src/components/SMSPreview.jsx` | Removed the "Recipients: ~50,000" and "Channel: SMS + WhatsApp" tiles (placeholder numbers with nothing real behind them); kept the real "Route" tile; added an explanatory comment. Nothing else in the file touched. | `diff` against backup: an isolated 5-line-old → 6-line-new block replacement, rest of file identical |

## 4. Files backed up (before editing)

- `traffic_module/backend/_pre_citizen_registration_backup/app.py.orig`
- `traffic_module/frontend/src/components/_pre_citizen_registration_backup/App.js.orig`
- `traffic_module/frontend/src/components/_pre_citizen_registration_backup/SMSPreview.jsx.orig`

(Naming matches this project's own existing convention, e.g. `_pre_traffic_redesign_backup/`.)

**Housekeeping note:** while first getting SQLite working against this mounted drive (see §5), an initial attempt left a corrupted 0-byte `citizen_alerts.sqlite` + a stale `-journal` file. Delete permission for the whole project folder was requested once, declined, and **not requested again** — per your correction, those two files were instead moved (not deleted) into `traffic_module/backend/_to_delete/` (as `.broken` files) so you can remove them yourself whenever you like; nothing else was touched by that cleanup.

---

## 5. Database / storage design

**Engine:** SQLite (stdlib `sqlite3`, no new dependency). **File:** `traffic_module/backend/data/citizen_alerts.sqlite` — new, separate from every existing store (`integration/alert_state.json`, `waste_module/.../citizen_reports.json`, `logs/predictions.sqlite`). No existing Traffic/Waste data was migrated into it or read from it.

```sql
CREATE TABLE citizens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mobile_number TEXT NOT NULL UNIQUE,      -- normalized +91XXXXXXXXXX
    preferred_language TEXT NOT NULL,        -- 'en' | 'kn' | 'hi'
    traffic_alerts_enabled INTEGER NOT NULL,
    waste_alerts_enabled INTEGER NOT NULL,
    location_consent INTEGER NOT NULL,       -- preference only, NEVER lat/lon
    ward_id TEXT,                            -- validated against the real ward registry, nullable
    ward_name TEXT,                          -- denormalized at write time
    mobile_verified INTEGER NOT NULL,
    status TEXT NOT NULL,                    -- 'pending_verification' | 'active' | 'inactive'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE citizen_otp_requests (
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
);
```

**A real environment issue found and fixed:** the first attempt to open this database over your mounted project drive failed with `sqlite3.OperationalError: disk I/O error` on the very first write — a known symptom of SQLite's default rollback-journal locking not being fully supported on some network/virtualized mounts. Fixed by setting `PRAGMA journal_mode=MEMORY` (plus `PRAGMA busy_timeout=5000`) on every connection in `citizen_registry._connect()`, which avoids ever creating an on-disk journal file. Trade-off, documented in the code: a hard crash mid-write isn't as crash-safe as a real on-disk journal would be — an acceptable trade for citizen preference data, and easy to revisit if this file ever sits on a filesystem that handles locking normally (e.g. running the backend natively on Windows against the D: drive directly, rather than through this remote-shell's mount).

**Privacy rule honored:** a mobile number never implies a location. `ward_id`/`ward_name` is an explicit, citizen-chosen "my alert area," validated against the same real 369-ward registry (`ward_registry_service.get_ward()`) the rest of the app already uses — an unrecognized id is rejected, never fabricated. `location_consent` is a boolean preference only; no latitude/longitude is ever accepted or stored by this new module. The existing ephemeral browser-location mechanism (`user_location_service.py`) is untouched and unconnected to this table — wiring the two together is explicitly future work, not done here.

---

## 6. API endpoints

All new, all additive, none replacing anything:

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/citizens/register` | Validates mobile/language/ward, creates a `pending_verification` citizen, issues an OTP. 409 (with the existing citizen's id) if the mobile number is already registered — never silently overwrites. |
| POST | `/api/citizens/verify-otp` | Checks the code, activates the citizen (`mobile_verified=true`, `status=active`) on success. |
| POST | `/api/citizens/{id}/resend-otp` | Issues a fresh code for an unverified citizen. |
| GET | `/api/citizens/{id}` | Returns the citizen's profile. |
| PATCH | `/api/citizens/{id}` | Partial update of language / traffic / waste / location-consent / ward / status. Mobile number is intentionally **not** editable here. |
| DELETE | `/api/citizens/{id}` | Hard-deletes the record. |

**OTP / no real SMS:** `citizen_otp.py` generates a real 6-digit code (via `secrets`, not `random`) and really persists/checks it (5-minute expiry, 5-attempt lockout, single-use). It is never sent anywhere. While `CITIZEN_ALERTS_DEV_MODE` is on (the default — there is currently no SMS provider to turn it off in favor of), `/api/citizens/register` and the resend endpoint include `dev_otp` + a `dev_notice` string directly in the JSON response, and every generated code is also printed to the console as `[DEV OTP - NOT SENT VIA SMS] ...`. Nothing in the code or its responses claims a code was sent to a real phone.

---

## 7. Frontend changes

**New:** `CitizenAlertRegistration.jsx` — a three-step panel (register → verify → manage), reachable from a new **"My Alerts"** tab appended after the existing tabs in `App.js` (existing tab order/behavior untouched). It:
- collects a mobile number (client + server validated) and English/Kannada/Hindi preference,
- has explicit ON/OFF toggles for Traffic alerts, Waste alerts, and location-alert consent (labeled as a preference, not a GPS grant),
- offers an optional real-ward picker sourced from the existing `/api/wards/list` endpoint (no new ward data, no fabricated list),
- shows the OTP step with a clearly labeled amber "Development Mode — not sent by SMS" banner when in dev mode,
- lets a verified citizen edit any preference, activate/deactivate, or permanently remove their registration.

It shows **no** subscriber counts, delivery counts, SMS success indicators, WhatsApp status, GPS tracking, or BHASHINI status anywhere — none of that exists yet, and the panel doesn't pretend otherwise.

**Modified:** `SMSPreview.jsx` — removed the "Recipients: ~50,000" and "Channel: SMS + WhatsApp" placeholder tiles per your instruction; the real Route tile stays.

---

## 8. Tests performed

Full FastAPI-level execution wasn't possible **from this remote shell specifically**: `device_bash` runs in an isolated Linux VM separate from your Windows Python environment (the one with FastAPI/torch/pandas installed in `traffic_module/backend/.venv`), and this VM has no network access to `pip install` those packages either. Rather than skip testing, I tested what's genuinely testable from here — the new modules are pure Python (stdlib + your existing `ward_registry_service.py`), so I ran real, executable checks against them directly:

| # | Test point (from your list) | Result |
|---|---|---|
| 1 | New citizen can be registered | ✅ `create_citizen()` round-trip verified |
| 2 | Mobile number is validated | ✅ accepts `+91XXXXXXXXXX`/bare 10-digit/91-prefixed; rejects short/wrong-leading-digit/empty |
| 3 | Language is stored | ✅ English/Kannada/Hindi (case-insensitive) → en/kn/hi, round-tripped |
| 4 | Traffic preference is stored | ✅ |
| 5 | Waste preference is stored | ✅ |
| 6 | Location consent is stored | ✅ (boolean only, confirmed no lat/lon field exists) |
| 7 | Ward/area association is stored | ✅ validated against your real, live `ward_registry.json` (369 wards) — a fake ward id is rejected, a real one (e.g. "R.T Nagar") resolves and stores correctly |
| 8 | Citizen remains after backend restart | ✅ simulated via a brand-new Python process re-importing the module (fresh module-level state) and re-reading the same DB file — record and all fields intact |
| 9 | Citizen can deactivate subscription | ✅ `status` → `inactive` via update, confirmed |
| 10 | Existing Traffic alert engine still works | Not re-executed (needs the full venv — see above), but confirmed **not imported, read, or modified** by any new code — see §1 |
| 11 | Existing Waste/USI alert engine still works | Same as #10 |
| 12 | Existing Traffic prediction still works | Same as #10 |
| 13 | Existing Waste dashboard still works | Same as #10 |
| 14 | No `friend_waste` files changed | ✅ confirmed via mtime check, §1 |
| 15 | No ML/model files changed | ✅ confirmed via mtime check, §1 |
| 16 | No real SMS is sent | ✅ confirmed by reading `citizen_otp.py` end-to-end — there is no send call, no provider import, no credential anywhere in this Stage 1 code |

Additionally verified: OTP full flow (wrong code rejected, correct code verified, consumed code can't be reused, 5-attempt lockout logic present), duplicate-mobile registration correctly rejected (409, original record untouched), `PATCH` rejects any attempt to change `mobile_number` (defensive column allowlist), and `app.py` still **compiles** cleanly (`python -m py_compile`) with the new block inserted, with every `citizen_registry.*`/`citizen_otp.*` reference in `app.py` cross-checked against what those two modules actually define (all resolve).

**What I could not run from here, and recommend you run once, in your own venv:**
```
cd traffic_module/backend
.venv\Scripts\pytest tests\test_citizen_registry.py -v
```
This exercises the full HTTP layer (`fastapi.testclient.TestClient` against the real `app`) including the two tests I could only write, not execute, here: a full register→verify→patch→delete round-trip over HTTP, and a sanity check that `/api/ward-stress`, `/api/alerts/active`, and `/api/health` still respond after the new routes were added. I'd also recommend running your existing suite (`pytest tests/`) once, the same way, purely as a belt-and-suspenders confirmation alongside the mtime evidence in §1 — I'm confident in that evidence, but an actual green test run costs you two minutes and removes all doubt.

---

## 9. Confirmation

Traffic ML/prediction code, Waste prediction code, `friend_waste/`, USI calculation code, and the existing Traffic/Waste alert-detection modules were not opened for editing, not imported for anything beyond a read-only ward lookup, and their file-modification timestamps confirm none were touched during this build. Everything built today is additive: three new files, one new database, and three existing files changed only by clean, isolated, diff-verified insertions/removals with zero unrelated lines touched.

Stopping here per your instruction — no SMS provider, no BHASHINI, no USSD implemented.
