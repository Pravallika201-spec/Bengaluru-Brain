# Stage 3C — BHASHINI Hindi Translation

**Date:** 2026-09-30
**Scope:** Replace ONLY the Hindi fallback path in `citizen_alert_dispatch.py` with a real BHASHINI English→Hindi translation attempt that fails closed to the existing English fallback. No real BHASHINI request was made. No real SMS was sent. `CITIZEN_ALERTS_DEV_MODE` was never set to `false`.

---

## 1. Pre-edit inspection (what I read before writing anything)

- `citizen_alert_dispatch.py` (post Stage 3B) — confirmed `_resolve_delivery_language()` is the single place the old Hindi fallback (`"en", "hi_not_yet_supported_sent_en"`) was decided, and that `_record_delivery()` is where the canonical English text (from the `message` dict) actually becomes available — i.e. the only place a real translation attempt could correctly be inserted.
- `kannada_messages.py` and (from earlier stages) `integration/alerts.py` — reconfirmed both only ever produce `{"english": ..., "kannada": ...}` dicts. There is no "hindi" key anywhere to source from — Hindi text can only come from translating the English string.
- `citizen_sms_provider.py` (Stage 3B) — used as the direct structural template for the new module: same fail-closed contract shape (`status`/`error` dict, never raises), same `_env()`/placeholder-blank-value guard, same `try: from dotenv import load_dotenv...` pattern, same "never print credentials" discipline.
- `STAGE3_SMS_BHASHINI_AUDIT_2026-09-29.md` — reconfirmed §C.1's correction that Kannada does not need BHASHINI (already real, native content) and that BHASHINI's actual necessary role is English→Hindi only; reconfirmed §B.4's disclosed real API shape (a two-call Pipeline Config → Pipeline Compute pipeline, not one request) and its own disclosed documentation gaps (no public default pipeline id, auth/rate-limit specifics not fully documented) — this implementation requires `BHASHINI_PIPELINE_ID` as a mandatory, user-supplied env var rather than fabricating a default.
- Current Hindi fallback behavior — traced end to end: `dispatch_traffic_alerts()`/`dispatch_usi_alerts()` call `_resolve_delivery_language(citizen["preferred_language"])`, then `_record_delivery()`, which (pre-Stage-3C) hardcoded the text lookup from `message` using only `language_sent`.

**Files I stated I would touch (see my message to you before editing) and what I actually touched — identical:** created `bhashini_translator.py` and `tests/test_bhashini_translator.py`; modified `citizen_alert_dispatch.py` (Hindi path only) and `tests/test_citizen_alert_dispatch.py` (the two tests asserting the old behavior, plus new tests); modified `.env.example` (append-only). Nothing else.

---

## 2. Files created

| File | Purpose |
|---|---|
| `traffic_module/backend/bhashini_translator.py` (309 lines) | The sole EN→HI translation seam. One public function, `translate_to_hindi(english_text)`, plus `bhashini_configured()`. No FastAPI route, no knowledge of citizens/mobile numbers/the SMS provider. |
| `traffic_module/backend/tests/test_bhashini_translator.py` (446 lines, 25 tests) | Mocked-HTTP-only unit tests covering both real BHASHINI pipeline hops (Config, then Compute) — success, not-configured, empty/whitespace input, timeout, connection error, HTTP error, malformed JSON, missing fields, empty translation, an unanticipated exception, and a credential-leak guard (checked against both the returned dict and everything printed to stdout). |

## 3. Files modified

| File | Change | Diff stat (vs. backup) |
|---|---|---|
| `traffic_module/backend/citizen_alert_dispatch.py` | (a) `import bhashini_translator` added. (b) `_resolve_delivery_language()`: the `"hi"` branch now returns a provisional `("hi", None)` instead of immediately deciding English fallback. (c) New function `_prepare_message_text()`: pure pass-through for `en`/`kn` (byte-for-byte the same lookup as before); for `hi`, calls `bhashini_translator.translate_to_hindi()` on the canonical English text and returns either the real Hindi text (`language_sent="hi"`) or the original English text with a named fallback tag (`language_sent="en"`, `language_fallback="hi_bhashini_fallback_sent_en:<reason>"`). (d) `_record_delivery()`: now calls `_prepare_message_text()` instead of the old one-line text lookup, and persists the *final* resolved `language_sent`/`language_fallback` (which may differ from what was passed in, for Hindi) alongside `status`/`provider_message_id`/`provider_error` in the same `UPDATE`. (e) Docstring updated: the old "HINDI GAP" section is kept as history, followed by a "STAGE 3C ADDENDUM" explaining the new behavior. | +86 / −19 lines |
| `traffic_module/backend/tests/test_citizen_alert_dispatch.py` | Two existing tests whose assertions were the *exact* old behavior this stage deliberately replaces were updated (not weakened — their new assertions verify the new, deliberately-different contract): `test_resolve_delivery_language_hindi_falls_back_to_english_with_visible_flag` → `test_resolve_delivery_language_hindi_is_now_deferred_to_bhashini_attempt` (asserts `("hi", None)`); `test_hindi_citizen_gets_english_with_visible_fallback_flag` → `test_hindi_citizen_falls_back_to_english_when_bhashini_not_configured` (asserts the new fallback tag, exercised via a **real, unmocked** `bhashini_translator` call that genuinely takes the not-configured branch, since no test in this suite sets `BHASHINI_*` env vars — the same "real call, real branch" pattern already used for `integration_bridge.get_active_alerts()` in this same file). Added: `test_hindi_citizen_gets_real_hindi_when_bhashini_configured_and_succeeds`, `test_hindi_citizen_falls_back_with_named_reason_when_bhashini_call_fails`, `test_bhashini_never_called_for_english_or_kannada_citizens`, and three direct `_prepare_message_text()` unit tests. No other existing test was touched. | +115 / −5 lines |
| `traffic_module/.env.example` | Appended (not rewritten) a new `BHASHINI_*` section — `BHASHINI_ULCA_USER_ID`, `BHASHINI_ULCA_API_KEY`, `BHASHINI_PIPELINE_ID` (blank placeholders), plus optional `BHASHINI_PIPELINE_CONFIG_URL`/`BHASHINI_TIMEOUT_SECONDS` (commented, defaults shown). The existing Exotel/dev-mode section from Stage 3B is untouched. | append-only |

**Not touched, confirmed by byte-identical MD5 and/or unchanged mtime:** `traffic_module/backend/citizen_sms_provider.py`, `traffic_module/backend/app.py`, `traffic_module/backend/citizen_registry.py`, `traffic_module/backend/citizen_otp.py`, `traffic_module/backend/kannada_messages.py`, `traffic_module/backend/traffic_alert_eligibility.py`, `traffic_module/backend/integration_bridge.py`, `traffic_module/backend/ward_registry_service.py`, `integration/alerts.py`, `integration/alert_state.py`, the `friend_waste/` and `waste_module/` directories, and the real `data/citizen_alerts.sqlite` (mtime identical to its Stage 3B value — every test used a temp SQLite file). No new HTTP endpoint anywhere — `app.py` was not touched at all.

## 4. What `bhashini_translator.py` actually does

`translate_to_hindi(english_text)` never raises; it always returns `{"status", "text", "error"}`:

- **Empty/whitespace input:** `FALLBACK_ENGLISH`, `error="empty_source_text"`, no network call.
- **Not (fully) configured** (any of `BHASHINI_ULCA_USER_ID`/`BHASHINI_ULCA_API_KEY`/`BHASHINI_PIPELINE_ID` missing or an obvious placeholder): `FALLBACK_ENGLISH`, `error="bhashini_not_configured"`, no network call.
- **Configured:** performs the real, two-call BHASHINI pipeline exactly as documented in the Stage 3 audit — **Pipeline Config** (POST to `BHASHINI_PIPELINE_CONFIG_URL`, default the public Meity/ULCA endpoint, with `userID`/`ulcaApiKey` headers) to obtain a per-call `callbackUrl`, a short-lived `inferenceApiKey`, and the translation `serviceId`; then **Pipeline Compute** (POST to that `callbackUrl` with that `inferenceApiKey`) carrying the actual English text and receiving the Hindi translation. Either hop failing — timeout, connection error, non-2xx HTTP, unparseable JSON, or a response missing the fields this module needs — falls back to English with a specific, named error tag (e.g. `bhashini_config_timeout`, `bhashini_compute_http_500`, `bhashini_compute_response_missing_fields`). An empty/blank translated string is also treated as a failure (`bhashini_empty_translation`) rather than accepted. Both request timeouts use `BHASHINI_TIMEOUT_SECONDS` (default 10s) applied to each hop independently.
- Credentials are passed only via the `headers=` dict on each `requests.post` call, never interpolated into a printed string; every log line names only the failure category, never a key/token value (verified by `test_credentials_never_appear_in_printed_output`).

## 5. How the dispatch layer changed

Exactly as scoped — only the Hindi path:

- `_resolve_delivery_language("hi")` now returns `("hi", None)` (provisional) instead of `("en", "hi_not_yet_supported_sent_en")` (final). `"kn"` and everything else are byte-for-byte unchanged.
- `_record_delivery()` calls the new `_prepare_message_text(message, language_sent, language_fallback)` in place of the old one-line text lookup. For `en`/`kn` this function is a pure pass-through — same dict key, same values, same result. For `hi`, it calls `bhashini_translator.translate_to_hindi(message["english"])` and returns either the real Hindi text (kept as `"hi"`, no fallback) or the original English text (downgraded to `"en"`, with a fallback tag naming *why*).
- The resolved `language_sent`/`language_fallback` — which may now differ from what was passed in — are written into the delivery row alongside `status`/`provider_message_id`/`provider_error`, so a citizen's actual delivered language is always what's recorded, never the pre-translation guess.
- **Nothing else changed.** Eligibility (`dispatch_traffic_alerts`/`dispatch_usi_alerts`'s own matching), ward/location matching, cooldown (still entirely owned by the untouched alert engines), deduplication (the same `INSERT OR IGNORE` + `UNIQUE` constraint from Stage 2/3B, unchanged), and the call into `citizen_sms_provider.send_sms()` (still receiving an already-resolved language/text, still the only thing that decides SIMULATED/SENT/FAILED) are all identical to Stage 3B.

## 6. Testing

### 6.1 Methodology note (same disclosed limitation as Stages 2/3B)

This verification shell has `requests`/`pandas`/`numpy`/stdlib but no `pytest`/`fastapi`/`torch`. All test files are genuine, standard `pytest`-compatible files; I used the same dependency-free manual test runner from Stage 3B (extended this session to also support the standard `capsys` fixture, needed by one credential-leak test) to actually execute every test function here rather than just inspect them. The two tests requiring `fastapi.testclient.TestClient` cannot run in this shell for that reason — unrelated to this stage, called out explicitly rather than hidden.

### 6.2 Tests run and results

```
=== bhashini_translator_tests: 25 passed, 0 failed (of 25) ===
=== citizen_sms_provider_tests: 18 passed, 0 failed (of 18) ===
=== citizen_alert_dispatch_tests: 27 passed, 0 failed (of 27) ===
=== citizen_registry_tests: 15 passed, 2 failed (of 17) ===
```

**Total: 85 passed, 2 failed** (the 2 failures are the same pre-existing `ModuleNotFoundError: No module named 'fastapi'` limitation reported in the Stage 3B report — not a regression, unrelated to this stage. You confirmed in your last message that these two pass at 17/17 in your real Windows `pytest` environment; **please re-run all four files there** to get a full real-environment signal on this stage's new/changed tests too.)

**`bhashini_translator_tests` (25/25, new this stage):** not-configured / partially-configured / placeholder-value fail closed with zero network calls; empty and whitespace-only input fail closed without a network call; a fully mocked success round-trips through both pipeline hops correctly (URL, headers, body shape, and timeout all asserted per hop) and returns the mocked Hindi string; a custom `BHASHINI_PIPELINE_CONFIG_URL` is honored; every Config-hop failure mode (timeout, connection error, HTTP 401/500, malformed JSON, missing fields) and every Compute-hop failure mode (timeout, connection error, HTTP 503, malformed JSON, missing fields, empty translation) falls back to English with the correct named tag; a totally unanticipated exception is caught and still falls back rather than propagating; `bhashini_configured()` is true only with all three variables set; credentials never appear in the returned dict or in anything printed to stdout.

**`citizen_alert_dispatch_tests` (27/27 — 23 pre-existing Stage 2/3B tests, 2 of which were updated for this stage's deliberate behavior change, + 6 new):**
- All pre-existing traffic/USI matching, preference-gating, dedup, and SMS-provider-wiring tests from Stages 2/3B still pass unchanged.
- Updated: the two Hindi-fallback tests now assert the new, deliberately-changed contract (see §3 above) rather than the old one.
- New: `test_hindi_citizen_gets_real_hindi_when_bhashini_configured_and_succeeds` and `test_hindi_citizen_falls_back_with_named_reason_when_bhashini_call_fails` (both mock `bhashini_translator.translate_to_hindi` directly — never touch HTTP) confirm the dispatch layer correctly uses a successful translation or a named fallback.
- New: `test_bhashini_never_called_for_english_or_kannada_citizens` — proves English/Kannada citizens are completely unaffected by this stage; BHASHINI is invoked zero times for them.
- New: three direct `_prepare_message_text()` unit tests, isolating this stage's actual new logic from the full dispatch flow.

**`citizen_sms_provider_tests` (18/18) and `citizen_registry_tests` (15/17, 2 known fastapi-unavailable failures):** unchanged from Stage 3B — included here only to confirm this stage caused no regression in either.

### 6.3 Explicit checks from your requirements list

- **English/Kannada messages preserved exactly:** `test_prepare_message_text_english_and_kannada_are_pure_passthrough` plus every pre-existing non-Hindi test in the suite (traffic/USI matching, preference gating) passing unchanged.
- **Dispatch behavior, dedup, Exotel integration preserved:** all pre-existing Stage 2/3B tests pass unchanged; `citizen_sms_provider.py` is byte-identical (confirmed by MD5) to its Stage 3B state.
- **No real BHASHINI calls during tests, all HTTP mocked:** every "configured" test in `test_bhashini_translator.py` monkeypatches `bh.requests.post`; an autouse fixture additionally patches `socket.create_connection` to raise on any real connection attempt, as a second, independent guarantee.
- **Fail closed to English when unavailable/not configured:** exercised both as a mocked unit test and, in `test_citizen_alert_dispatch.py`, as a genuine real (unmocked) call that takes the not-configured branch, since this environment has no `BHASHINI_*` variables set.
- **No new public endpoint:** `app.py` untouched (confirmed by MD5).
- **No real SMS sent, `CITIZEN_ALERTS_DEV_MODE` never set to `false`:** confirmed — see §7.

## 7. Environment variables required

Add these (with real values) to `traffic_module/.env` — never commit that file; already excluded by `.gitignore`. `.env.example` (committed) documents these as blank placeholders only, appended after the existing Stage 3B Exotel section.

| Variable | Required for a real translation? | Notes |
|---|---|---|
| `BHASHINI_ULCA_USER_ID` | Yes | ULCA user id (Pipeline Config auth). |
| `BHASHINI_ULCA_API_KEY` | Yes | ULCA API key (Pipeline Config auth). |
| `BHASHINI_PIPELINE_ID` | Yes | Your own registered BHASHINI pipeline id — there is no working default; the Stage 3 audit's own research flagged this as something only obtainable from the BHASHINI portal, so none is fabricated here. |
| `BHASHINI_PIPELINE_CONFIG_URL` | No | Defaults to the public Meity/ULCA endpoint documented in the Stage 3 audit. |
| `BHASHINI_TIMEOUT_SECONDS` | No | Defaults to `10`, applied to each of the two pipeline calls independently. |

If any required variable is missing, `translate_to_hindi()` does not crash and does not fabricate a translation — it returns the original English text with `error="bhashini_not_configured"`, and `_prepare_message_text()` in turn records that as a visible `language_fallback` tag on the delivery row.

## 8. Was any real BHASHINI request made, and was any real SMS sent?

**No real BHASHINI request was made.** `BHASHINI_ULCA_USER_ID`/`BHASHINI_ULCA_API_KEY`/`BHASHINI_PIPELINE_ID` were never set to real values at any point in this session; every "configured" test path used fabricated strings like `"test-ulca-key-never-real"` against a mocked `requests.post`, with a socket-level block as a second, independent safety net.

**No real SMS was sent.** `CITIZEN_ALERTS_DEV_MODE` was never set to `false` in this session, and your real Exotel credentials were never entered, requested, or referenced anywhere in this work.
