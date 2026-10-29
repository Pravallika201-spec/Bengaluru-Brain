# Stage 3B — Safe SMS Provider Integration (Exotel)

**Date:** 2026-09-29
**Scope:** Wire a real (but never-yet-called) SMS provider seam into the existing Stage 2 citizen dispatch pipeline, behind the existing `CITIZEN_ALERTS_DEV_MODE` toggle. No real SMS was sent. No Traffic ML, USI, friend_waste, or existing alert-engine code was touched.

---

## 1. Pre-edit inspection (what I read before writing anything)

- `STAGE3_SMS_BHASHINI_AUDIT_2026-09-29.md` — the Stage 3 audit's own §C.6 proposed exactly a `traffic_module/backend/citizen_sms_provider.py` module exposing one `send_sms()` function, config-gated the same way `app.py` already gates TomTom/OpenWeather (`bool(os.getenv(...))`). This implementation follows that design.
- `traffic_module/backend/citizen_otp.py` — confirmed the existing `CITIZEN_ALERTS_DEV_MODE` convention exactly: `os.getenv("CITIZEN_ALERTS_DEV_MODE", "true").strip().lower() != "false"`. Reused verbatim rather than inventing a second toggle.
- `traffic_module/backend/citizen_alert_dispatch.py` (Stage 2, full file) — confirmed `_record_delivery()` is the single point where a delivery row is written, and that it currently hardcodes `status='SIMULATED_NOT_SENT'` at insert time. This is the only function Stage 3B needed to change.
- `traffic_module/backend/citizen_registry.py` — confirmed `validate_mobile_number()` always stores numbers as `+91XXXXXXXXXX`, which is the exact "To" format Exotel's Send SMS API expects — no reformatting needed in the new module.
- `traffic_module/backend/app.py`, `routing_service.py`, `tomtom_traffic_service.py`, `weather_logic.py` — confirmed the project's existing, consistent pattern for loading secrets: `os.getenv("X_API_KEY")` plus a guarded `try: from dotenv import load_dotenv; load_dotenv(); load_dotenv(<two-levels-up>/.env) except Exception: pass`. Reused this exact pattern in the new module.
- `.gitignore` — confirmed `.env`, `.env.*`, `*.env` are already excluded, and read the existing comments documenting a real prior secret-leak incident (rotated OpenWeatherMap key) that motivated that rule. No `.env` file existed anywhere in the project before this stage; none was created — only `.env.example` (placeholders only).
- `requirements.txt` — confirmed `requests==2.31.0` and `python-dotenv==1.0.0` are already dependencies. No new package was needed or installed.
- `integration/alerts.py` — confirmed the existing `send_sms_simulated()` / `SIMULATED_NOT_SENT` convention this stage's `STATUS_SIMULATED` constant stays consistent with.

**Files I intended to touch, stated before editing:** create `citizen_sms_provider.py` and `traffic_module/.env.example`; modify `citizen_alert_dispatch.py` (import + schema + `_record_delivery`); add `tests/test_citizen_sms_provider.py`; extend `tests/test_citizen_alert_dispatch.py`. Nothing else. This is exactly what was done — see §2/§3.

---

## 2. Files created

| File | Purpose |
|---|---|
| `traffic_module/backend/citizen_sms_provider.py` (222 lines) | The single seam for real SMS sending. Exposes one public function, `send_sms(mobile_number, text, language)`, plus `sms_provider_configured()`. No FastAPI route, no way to send to an arbitrary number from outside the dispatch layer. |
| `traffic_module/.env.example` (35 lines) | Placeholder-only env var names (existing keys + new `CITIZEN_ALERTS_DEV_MODE`/`EXOTEL_*` names). No real values. |
| `traffic_module/backend/tests/test_citizen_sms_provider.py` (325 lines, 18 tests) | Unit tests for the new module — DEV mode, unconfigured production mode, mocked-success, mocked-failure, timeout, connection error, malformed response, credential-leak guard. Every test mocks `requests.post`; an autouse fixture additionally patches `socket.create_connection` to raise, as a second, independent guarantee that no test can reach the real network even if the `requests` mock were ever bypassed by a future edit. |

## 3. Files modified

| File | Change | Diff stat (vs. backup) |
|---|---|---|
| `traffic_module/backend/citizen_alert_dispatch.py` | (a) `import citizen_sms_provider` added. (b) `_ensure_schema()`: `citizen_alert_deliveries` gains two nullable columns, `provider_message_id` and `provider_error`, with an in-place `ALTER TABLE ... ADD COLUMN` migration for any database created by an earlier Stage 2 run (verified — see §6.4). (c) `_record_delivery()` rewritten as a two-phase operation (see §4). (d) A "STAGE 3B ADDENDUM" paragraph appended to the module docstring explaining the change; no existing docstring text removed. | +94 / −16 lines |
| `traffic_module/backend/tests/test_citizen_alert_dispatch.py` | 4 new tests appended (see §3 of the test list in §6.2). No existing test was changed, weakened, or removed. | +108 / −1 lines (the one removed line was my own typo introduced and caught during this same edit, not a change to Stage 2's original tests) |

**Not touched, confirmed by byte-identical MD5 and unchanged mtimes:** `traffic_module/backend/app.py`, `traffic_module/backend/citizen_registry.py`, `traffic_module/backend/citizen_otp.py`, `traffic_module/backend/traffic_alert_eligibility.py`, `traffic_module/backend/integration_bridge.py`, `traffic_module/backend/ward_registry_service.py`, `integration/alerts.py`, `integration/alert_state.py`, `traffic_module/backend/gnn_model.py`, `traffic_module/backend/gnn_prediction_service.py`, `traffic_module/backend/real_gnn_service.py`, the `friend_waste/` and `waste_module/` directories (mtime identical, top-level, to the baseline captured immediately before any edit in this session), and the real `data/citizen_alerts.sqlite` (mtime from an earlier session, untouched — every test in this stage used a temp SQLite file via monkeypatched `DB_PATH`, never the real one). **No new public HTTP endpoint was added anywhere** — `app.py` was not modified at all in this stage.

## 4. What `citizen_sms_provider.py` actually does

`send_sms(mobile_number, text, language)` never raises for an ordinary failure; it always returns `{"status", "provider_message_id", "error"}`:

- **`CITIZEN_ALERTS_DEV_MODE` on (default, unchanged):** returns `SIMULATED_NOT_SENT` immediately. **Zero network calls are made** — not a mocked call, an actual absence of one.
- **Dev mode off, but not fully configured** (any of `EXOTEL_ACCOUNT_SID` / `EXOTEL_API_KEY` / `EXOTEL_API_TOKEN` / `EXOTEL_SENDER_ID` missing or left as an obvious placeholder like `"changeme"`): returns `FAILED`, `error="sms_provider_not_configured"`. This is a deliberate fail-closed choice — a real send that was explicitly requested but can't be attempted must never silently masquerade as `SIMULATED_NOT_SENT` or as a success.
- **Dev mode off and configured:** issues one `requests.post` to `https://<subdomain>/v1/Accounts/<sid>/Sms/send` with an explicit timeout (default 10s, configurable), Basic Auth credentials passed only via the `auth=` kwarg (never interpolated into any printed/logged string), and `From`/`To`/`Body` in the POST body. The response is parsed defensively: a non-2xx HTTP status, a timeout, a connection error, an unparseable JSON body, or a provider-reported `failed`/`expired`/`rejected`/`blacklisted` status all map to `FAILED` with a short, credential-free error tag; a normal success captures the provider's own `SMSMessage.Sid` as `provider_message_id` and returns `SENT`. Any *unanticipated* exception is caught by a last-resort `except Exception` and also converted to a `FAILED` result — this function is designed to never crash its caller.

## 5. How the dispatch layer changed (and how eligibility/dedup stayed untouched)

`citizen_alert_dispatch.py`'s `_record_delivery()` is the **only** function that changed, and only its own internal mechanics — `dispatch_traffic_alerts()` and `dispatch_usi_alerts()` still decide eligibility, ward/location matching, and which citizens qualify exactly as Stage 2 built them, and still call `_record_delivery()` the same way with the same arguments.

`_record_delivery()` is now two-phase, specifically so a duplicate dispatch run can never trigger a duplicate *real* send, not just a duplicate database row:

1. **Phase 1 (inside the existing `_lock`):** `INSERT OR IGNORE` a row with a transient `status='PENDING'`, using the same `UNIQUE(citizen_id, alert_source, alert_key, alert_instance_ts)` constraint Stage 2 already relies on. If this is a repeat of an already-recorded alert instance, `rowcount` is 0 and the function returns immediately — **no send is attempted at all**.
2. **Phase 2 (only when phase 1 actually inserted a new row):** calls `citizen_sms_provider.send_sms()` with the citizen's mobile number and the already-composed message text (English or Kannada, per Stage 2's existing `_resolve_delivery_language()` — completely unchanged), then `UPDATE`s that same row from `PENDING` to the real outcome (`status`, `provider_message_id`, `provider_error`).

The network call itself runs **outside** `_lock`, so one citizen's send attempt can't block unrelated inserts for other citizens.

## 6. Testing

### 6.1 Methodology note (same disclosed limitation as Stage 2)

The verification shell available to me here has `requests`, `pandas`, `numpy`, and the stdlib, but — like the sandbox used for Stage 2's original implementation — **no `pytest`, `fastapi`, or `torch`**. All test files are written as genuine, standard `pytest`-compatible files (using real `monkeypatch`, `setup_function`/`teardown_function`, etc.) so they run unmodified under your real Windows `pytest` environment. To actually execute them here rather than just eyeball them, I used the same kind of dependency-free manual test runner used in Stage 2's bug-fix round — it genuinely imports each test module and calls every test function (with a real monkeypatch-equivalent and fixture/setup support), it does not reimplement or simplify any test's logic. The two tests requiring `fastapi.testclient.TestClient` cannot run here for that reason (same as previously) and are called out explicitly rather than skipped silently.

### 6.2 Tests run and results

```
=== citizen_sms_provider_tests: 18 passed, 0 failed (of 18) ===
=== citizen_alert_dispatch_tests: 21 passed, 0 failed (of 21) ===
=== citizen_registry_tests: 15 passed, 2 failed (of 17) ===
```

**citizen_sms_provider_tests (18/18, new this stage)** — DEV mode default/explicit-true never call `requests.post`; DEV mode wins even if Exotel credentials happen to be present; unconfigured and partially-configured production mode both fail closed without any network attempt; placeholder values (`"changeme"`, etc.) count as unconfigured; a mocked success correctly captures the provider message id and posts the expected URL/auth/body/timeout; a custom subdomain and timeout are honored; provider-reported `failed` status, HTTP 401/500, malformed JSON, timeout, connection error, and a totally unexpected exception all resolve to `FAILED` without raising; `sms_provider_configured()` is true only when all four variables are set; the Exotel API key/token never appear anywhere in a returned result.

**citizen_alert_dispatch_tests (21/21 — 17 pre-existing Stage 2 tests + 4 new Stage 3B integration tests):**
- All 17 Stage 2 tests pass unchanged — ward resolution, Hindi fallback, traffic/USI matching and preference gating, dual-subscriber dedup, and both duplicate-dispatch dedup tests all still pass exactly as before.
- New: `test_dispatch_records_sent_status_and_provider_message_id_from_provider` — a mocked `SENT` result from the provider is correctly persisted with its `provider_message_id`.
- New: `test_dispatch_records_failed_status_and_provider_error_from_provider` — a mocked `FAILED` result is correctly persisted with its `provider_error`; the delivery is still recorded (a failed attempt is a real attempt, not silently dropped).
- New: `test_dispatch_never_calls_provider_twice_for_the_same_alert_instance` — runs dispatch twice for one alert instance and asserts the provider's `send_sms` was called **exactly once**, proving a duplicate dispatch run cannot trigger a duplicate real send.
- New: `test_dispatch_default_dev_mode_never_reaches_real_requests_post` — an extra, independent safety net at the *dispatch* level (not just the provider-module level): with `CITIZEN_ALERTS_DEV_MODE` unset, a full `dispatch_traffic_alerts()` run is proven to never call `requests.post`, by monkeypatching it to raise if invoked.

**citizen_registry_tests (15/17 — unchanged from Stage 2's last verified state):** the 2 failures are `test_http_existing_endpoints_still_respond` and `test_http_register_verify_patch_delete_round_trip`, both failing only with `ModuleNotFoundError: No module named 'fastapi'` in this verification shell — not a regression, not related to this stage's changes, and the same known limitation already documented in the Stage 2 report. **Please re-run these two specifically in your real Windows `pytest` environment** (where `fastapi` is installed) to get a real pass/fail signal on them, per your own established practice from the Stage 2 bug-fix round.

### 6.3 Explicit checks from your requirements list

- **Traffic/Waste/USI/citizen registration/Stage 2 dispatch behavior preserved:** all 17 original Stage 2 dispatch tests and 15/15 non-HTTP registry tests pass unchanged; `friend_waste`, `waste_module`, and every ML/alert-engine file are confirmed byte-for-byte/mtime untouched (§3).
- **`CITIZEN_ALERTS_DEV_MODE` still works, dev = no real SMS:** confirmed by `test_dispatch_default_dev_mode_never_reaches_real_requests_post` and all DEV-mode tests in the provider suite — zero network calls, `SIMULATED_NOT_SENT` recorded.
- **Explicit timeout, clear error handling, no credential logging, provider message id captured:** see §4; verified by dedicated tests (`test_production_mode_honors_custom_subdomain_and_timeout`, `test_credentials_never_appear_in_returned_dict`, `test_production_mode_success_captures_message_id`).
- **No new public "send arbitrary SMS" endpoint:** `app.py` was not modified at all in this stage — confirmed by unchanged MD5/mtime.
- **Existing dispatch logic remains the sole source of eligibility/matching/cooldown/dedup:** unchanged — only `_record_delivery()`'s internals changed; see §5.
- **Provider only receives an already-approved alert:** `send_sms()` takes a mobile number and pre-composed text; it has no access to, and never calls, any eligibility/matching function.
- **Migration safety for the real database:** verified separately (not part of the pytest suite, a standalone check) — a database built with Stage 2's original schema (no `provider_message_id`/`provider_error` columns) was created, then `citizen_alert_dispatch._connect()` was called against it: the two new columns were added via `ALTER TABLE`, the pre-existing row survived unchanged, and no error occurred. This matters because your real `data/citizen_alerts.sqlite` already has the pre-Stage-3B schema from earlier real runs.
- **No real SMS was sent:** confirmed — see §7.

### 6.4 BHASHINI

Not implemented, per your instruction. No new translation interface/seam was added either: the existing `_resolve_delivery_language()` in `citizen_alert_dispatch.py` already fully separates "which language to compose in" from "how to deliver it" (`citizen_sms_provider.send_sms()` takes already-composed text and never does translation itself) — that existing separation already is the seam BHASHINI would plug into later, so adding a second, currently-empty translation interface on top of it would have been an unrelated speculative addition rather than something this stage's architecture required.

---

## 7. Environment variables required

Add these (with real values) to `traffic_module/.env` — **never commit that file**; `.gitignore` already excludes it. `traffic_module/.env.example` (committed) documents these as blank placeholders only.

| Variable | Required for a real send? | Notes |
|---|---|---|
| `CITIZEN_ALERTS_DEV_MODE` | — | Already existed (Stage 1). `true`/unset = simulated only (default). Set to `false` to allow real sends to be attempted. |
| `EXOTEL_ACCOUNT_SID` | Yes | Exotel Account SID. |
| `EXOTEL_API_KEY` | Yes | Exotel API Key (Basic Auth username). |
| `EXOTEL_API_TOKEN` | Yes | Exotel API Token (Basic Auth password). |
| `EXOTEL_SENDER_ID` | Yes | DLT-approved sender id / ExoPhone used as the SMS "From". |
| `EXOTEL_SUBDOMAIN` | No | Defaults to `api.exotel.com`; override only if your account is provisioned on a region-specific subdomain. |
| `CITIZEN_ALERTS_SMS_TIMEOUT_SECONDS` | No | Defaults to `10`. |

If `CITIZEN_ALERTS_DEV_MODE=false` and any of the four required Exotel variables is missing, dispatch does not crash and does not silently simulate — every matching delivery is recorded with `status=FAILED`, `provider_error=sms_provider_not_configured`, so the gap is visible in the data rather than hidden.

## 8. Was any real SMS sent during this implementation or testing?

**No.** DEV_MODE was never set to `false` against a real, configured Exotel account at any point in this session. Every "production mode" test exercised mocks `requests.post` (or, in the dispatch-integration tests, mocks `citizen_sms_provider.send_sms` itself) with fabricated Exotel-shaped responses; the credential values used in tests are literal strings like `"test-key-never-real"`, never anything resembling a real key. An autouse fixture in `test_citizen_sms_provider.py` additionally patches `socket.create_connection` to raise on any real connection attempt, as a second, independent guarantee. The real Exotel credentials you generated were never entered into any file, prompt, environment variable, or command in this session.
