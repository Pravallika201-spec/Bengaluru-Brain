# Stage 3 — Real SMS + BHASHINI — Audit and Design (Read-Only)
**Date:** 2026-09-29
**Scope:** audit-and-design only, as instructed. No files were created, modified, deleted, or moved. No packages were installed. No external service was called. No SMS was sent. No BHASHINI call was made. No account was created. This document is the only output.
**Method:** direct inspection of source files on the actual machine (`D:\major project\`, via the linked-device shell) for section A; web research for section B, clearly separated and cited; design reasoning built on both for sections C–G.

---

## A. Facts found in the current project

### A.1 Current SMS state (item 1)

**Every existing SMS/message-generation implementation, and what's simulated vs. real:**

| Implementation | File | Generates real text? | Sends real SMS? |
|---|---|---|---|
| `send_sms_simulated(phone_number, alert)` | `integration/alerts.py` (lines ~119–133) | ✅ real bilingual (English/Kannada) text via `generate_alert()` | ❌ `print()`s a `[SIMULATED SMS]` line and returns `{"status": "SIMULATED_NOT_SENT", ...}` — never a network call |
| `KannadaMessagesService` (route-status + incident templates) | `traffic_module/backend/kannada_messages.py` | ✅ real bilingual text | N/A — this module only builds text, never sends anything, by design |
| `citizen_otp.generate_otp()` | `traffic_module/backend/citizen_otp.py` | ✅ real 6-digit code (via `secrets`, not `random`) | ❌ printed to console as `[DEV OTP - NOT SENT VIA SMS] ...`, never sent |
| `_record_delivery()` (Stage 2) | `traffic_module/backend/citizen_alert_dispatch.py` | ✅ reuses whichever of the above two generators produced the alert's text | ❌ prints `[SIMULATED CITIZEN ALERT] ...` and writes a `status='SIMULATED_NOT_SENT'` row — never a network call |

**Where Stage 2 currently records `SIMULATED_NOT_SENT`, exactly:** `citizen_alert_dispatch.py`'s `_record_delivery()` function, in the `INSERT OR IGNORE INTO citizen_alert_deliveries (..., status, ...) VALUES (..., 'SIMULATED_NOT_SENT', ...)` statement — the literal string `'SIMULATED_NOT_SENT'` is hardcoded into that one SQL statement (it is not a column value passed in from a caller). This is the single seam a real send would need to update: after a real provider call, the row's `status` needs to reflect the real outcome (`SENT`/`FAILED`/etc., see §C.7) instead of always being that one literal.

**Existing SMS-related endpoints/functions — the complete list:**
- `integration/alerts.py`: `send_sms_simulated()`, `maybe_alert_and_send()` (the cooldown-gated caller)
- `traffic_module/backend/citizen_alert_dispatch.py`: `_record_delivery()` (the Stage 2 equivalent, generalized to a real citizen's own number instead of the hardcoded `"+91-SIMULATED"` placeholder `alerts.py` uses)
- `traffic_module/backend/app.py`: `POST /api/citizens/dispatch/run` (triggers the above), `GET /api/citizens/{id}/alert-deliveries` (reads the above)
- No endpoint anywhere accepts or exposes a phone number for anything other than registration/preferences — confirmed no endpoint takes an arbitrary `to` number and sends free-form text (i.e., there's no exploitable "send anything to anyone" surface to account for when wiring a real provider in).

**Whether any real SMS provider is already configured anywhere: no.** No `.env` file exists anywhere in the project (checked explicitly — `find . -iname "*.env*"` returns nothing). `requirements.txt` (`traffic_module/backend/`) already lists `requests==2.31.0` and `python-dotenv==1.0.0` — both already usable for a real provider integration with zero new dependencies, but neither is currently pointed at any SMS vendor. `integration/alerts.py`'s own docstring sketches, **as a comment only, never executable code**, where a real provider call would go:
```python
def send_sms_real(phone_number, message):
    return twilio_client.messages.create(to=phone_number, body=message, from_=...)
```
This is illustrative shorthand, not a decision — see §B for why Twilio specifically deserves scrutiny rather than being the default just because it's the name already typed into a comment.

### A.2 OTP flow (item 2)

**Exactly how Stage 1 currently generates and verifies OTPs** (`citizen_otp.py`, read in full):
- `generate_otp(citizen_id, mobile_number, purpose)`: generates a 6-digit code with `secrets.randbelow(1_000_000)` (cryptographically strong, not `random`), inserts a row into `citizen_otp_requests` (columns: `citizen_id, mobile_number, otp_code, purpose, created_at, expires_at, consumed=0, attempts=0`), and returns `{"code", "expires_at"}`.
- `verify_otp(citizen_id, mobile_number, submitted_code, purpose)`: fetches the most recent **unconsumed** row for that `(citizen_id, purpose)`, rejects if none exists, rejects if `attempts >= 5` (`MAX_OTP_ATTEMPTS`), rejects if past `expires_at` (`OTP_TTL_SECONDS = 300`, i.e. 5 minutes), compares with `secrets.compare_digest` (constant-time, avoids a timing side-channel), increments `attempts` on a wrong code, and marks `consumed=1` on success — a consumed code can never be reused (confirmed by both Stage 1's and Stage 2's own test suites).
- **`DEV_MODE`** (`CITIZEN_ALERTS_DEV_MODE` env var, defaults to `"true"` — i.e. on unless explicitly set to `"false"`): while on, `generate_otp`'s caller (`app.py`'s `/api/citizens/register` and `/resend-otp` endpoints) attaches `dev_otp`/`dev_notice` directly to the JSON HTTP response, and every generated code is printed to the console prefixed `[DEV OTP - NOT SENT VIA SMS]`. The module's own docstring is explicit about why this currently defaults on: *"This project currently has no SMS provider at all... there is no other way to complete registration right now. Turning it off does not add a real send path; it only stops exposing the code, which would make verification impossible until a real provider is wired in."*

**How real OTP SMS could replace the current dev-only path, and how dev mode stays a safe fallback (design, not yet built — see §C.6 for the exact mechanics):** the generation/verification logic above needs **zero changes** — it already produces a real, securely-generated, correctly-expiring, attempt-limited code; the only thing missing is a delivery step. The natural seam is exactly where Stage 2's `_record_delivery()` seam is: a new function (e.g. `citizen_sms_provider.send_otp_sms(mobile_number, code, language)`) called from `app.py`'s two OTP endpoints, guarded by whether a provider is actually configured (`CITIZEN_ALERTS_SMS_PROVIDER_CONFIGURED`, derived from whether the provider's API key env var is set — mirroring the exact `tomtom_configured = bool(os.getenv("TOMTOM_API_KEY") ...)` pattern `app.py` already uses in two other places). **Preserving dev mode as a fallback** means: if a real provider is configured, send for real AND stop including `dev_otp` in the response; if not configured, keep exactly today's behavior unchanged. This is a config-driven branch, not a rewrite — `DEV_MODE` already exists as exactly the right toggle, it just currently has no "else" branch with anything to do.

**"Do not expose OTPs in production responses"** — already how the code frames its own contract: `_dev_otp_fields()` in `app.py` (the only place `dev_otp` is ever attached to a response) is unconditionally gated on `citizen_otp.DEV_MODE`. Stage 3's job here isn't to add a guard that doesn't exist — it's to make sure `CITIZEN_ALERTS_DEV_MODE` actually gets set to `false` in whatever counts as this project's "production" (there isn't one yet — this is a college project with no deployed environment), and to make the SMS-provider-configured check and the dev-mode-off check travel together deliberately (see §D) rather than assuming one implies the other.

### A.3 BHASHINI presence (item 4, audit half)

**Not present anywhere in the codebase — re-confirmed for Stage 3.** A case-insensitive search across `traffic_module` and `integration` (excluding `.venv`/`node_modules`/`.git`/`__pycache__`) for `bhashini` returns matches **only** in comments/docstrings that explicitly say it is *not* present (`app.py`, `citizen_alert_dispatch.py`, `CitizenAlertRegistration.jsx` — all Stage 1/2's own "we didn't build this" disclosures). Same result as the original Citizen Alert System Audit. There is no BHASHINI client, no API key handling, no translation-caching table, nothing to build on top of — Stage 3's BHASHINI piece is entirely new work.

### A.4 Two facts specific to this project that materially affect the Stage 3 security design

- **`.gitignore` already excludes `.env`, `.env.*`, `*.env`, `**/credentials.json`, `**/secrets.json`, `**/*_credentials.*`, `**/*_secret*.json`** — the convention Stage 3 needs (secrets never committed) is already established project-wide, not something to introduce from scratch.
- **This project has a real prior secret-leak incident**, documented in `.gitignore`'s own comments: *"the OLD exposed key in its original commit blob"* (an OpenWeatherMap API key, per a second comment: *"realtime_data.py copies previously held a hardcoded OpenWeatherMap key (the same one exposed in the initial commit — since rotated)"*), which required a git-history rewrite on 2026-09-03 (`_security_backups/` holds the pre-rewrite bundle, itself gitignored). This is not a hypothetical risk to caveat generically — it is precedent from this exact repository, and it is the strongest possible argument for Stage 3 to follow the existing `os.getenv("X_API_KEY")` + `.env` pattern exactly, never a hardcoded fallback "for convenience," even temporarily.

---

## B. Current external provider / BHASHINI information (web research — clearly separated from §A)

Everything in this section came from web search/fetch during this session, not from the project's own files. Sources are cited inline and listed at the end of each subsection. Where public documentation was thin or inconsistent, that is stated explicitly rather than filled in with a guess.

### B.1 India SMS delivery — regulatory baseline (applies to every provider, not a vendor-specific fact)

Transactional/OTP SMS to Indian mobile numbers is governed by TRAI's DLT (Distributed Ledger Technology) framework: the sending entity and its message templates must be registered on a DLT platform, and a **sender ID** (an alphanumeric identifier shown as the sender, e.g. `BLRBRN`) must be approved per-template before that exact template can be sent — a mismatched or unregistered template is typically blocked at the carrier level regardless of which API provider is used ([SpringEdge: How to Choose an SMS API Provider in India](https://www.springedge.com/how-to-choose-sms-api-provider-india)). Good providers handle DLT entity registration, sender ID approval, and template scrubbing on the customer's behalf, with roughly a 24–48 hour template-approval turnaround once DLT entity registration itself is complete (entity registration itself is a separate, slower one-time step). This DLT/sender-ID requirement is a **regulatory** fact, not a per-vendor feature — it applies however Stage 3 eventually sends real SMS domestically.

### B.2 Twilio, specifically (already the name in this project's own placeholder comment — checked on its own merits, not assumed)

Twilio's own published guidelines describe **two distinct pathways** for India ([Twilio: India SMS Guidelines](https://www.twilio.com/en-us/guidelines/in/sms)):
- **International gateway** — no DLT registration required, messages route through international operators using "random ILDO-approved short codes" (format `5NNNN`–`5NNNNNNNN`), bypasses India's Do-Not-Disturb registry restrictions. This is usable **without** DLT paperwork.
- **Domestic gateway** — requires the sender to complete DLT company + sender-ID registration on the relevant mobile operators' DLT portal first, then submit that registration to Twilio; Twilio states only DLT-registered **alphanumeric** sender IDs are supported domestically, with a typical ~10-business-day provisioning timeline.

This means the common belief that "Twilio doesn't work for India" is an oversimplification — sending is possible without DLT via the international route, but a domestically-routed, properly-branded sender ID still needs the same DLT process as every other provider. Twilio's SMS API is well-documented, globally Unicode-capable (a general, long-established platform capability, not India-specific — the sources checked in this pass did not include India-specific Kannada/Hindi Unicode confirmation from Twilio's own docs, so that specific claim is left unconfirmed rather than assumed).

### B.3 India-specific aggregators (MSG91 used as the concrete example — one of several similar options, not a recommendation to sign up)

MSG91's own product pages ([msg91.com/in/otp](https://msg91.com/in/otp), [docs.msg91.com/overview](https://docs.msg91.com/overview)) confirm dedicated **Send OTP / Resend OTP / Verify OTP** API endpoints (i.e. OTP delivery+verification can optionally be handled provider-side instead of this project's own `citizen_otp.py` logic — a design choice, not a requirement, see §C.6) and signup framed as free-to-start ("Get Started For Free"). **What the public pages did *not* concretely confirm during this pass:** the exact authentication header/scheme, Kannada/Hindi Unicode SMS support specifically, or whether MSG91 handles DLT registration on the customer's behalf — the pages redirect to gated/account-specific documentation for those specifics. This is disclosed honestly rather than assumed from the provider's general India-market positioning.

More broadly, multiple India-focused comparison sources ([SpringEdge](https://www.springedge.com/how-to-choose-sms-api-provider-india), [SMSCountry](https://www.smscountry.com/blog/best-sms-apis-in-india/), [MessageBot](https://messagebot.in/blog/best-otp-sms-providers-in-india/)) consistently describe this category of provider (SpringEdge, MSG91, SMSCountry, Fast2SMS, Kaleyra/Karix, and others) as: India-registered, DLT-registration-assistance included, native Unicode (UCS-2) support for major Indian languages "auto-detected from message body," typical transactional pricing **₹0.10–0.20 per SMS** depending on volume (a price below ₹0.10 is flagged in one source as likely unreliable "aggregator routing"), and free test credits at signup that work against the same production API (so integration code doesn't need to change between testing and going live).

### B.4 BHASHINI — what the public documentation actually shows

**API shape** ([Bhashini APIs — GitBook](https://bhashini.gitbook.io/bhashini-apis)): a three-step call flow — an optional **Pipeline Search** call, a mandatory **Pipeline Config** call, and a mandatory **Pipeline Compute** call to actually get output. Bhashini follows **ISO-639 language codes** (`hi` = Hindi, `en` = English; Kannada is `kn` under this scheme, consistent with the rest of the ISO-639 series though not explicitly spelled out on the page fetched). The platform supports ASR (speech-to-text), NMT (machine translation — the relevant task for this project), and TTS (text-to-speech), usable individually or chained.

**Language-pair confirmation** ([Available Models — GitBook](https://dibd-bhashini.gitbook.io/bhashini-apis/available-models-for-usage)): multiple named models support the exact pairs Stage 3 needs, bidirectionally — e.g. `bhashini/iiith/nmt-all` (Hindi, English, Kannada + 30 other languages, any-to-any among them), `ai4bharat/indictrans-v2-all-gpu--t4` (English↔Kannada, English↔Hindi both confirmed present), `bhashini/cdac-pune/nmt` (explicitly lists "English, Kannada, Gujarati, Malayalam" both directions), and `bhashini/bodhan/Indic-trans-v4`. So **English→Kannada and English→Hindi translation models genuinely exist and are named in Bhashini's own public model catalog** — this is a confirmed fact, not an assumption.

**What the public documentation checked during this pass did *not* clearly show, and this is disclosed rather than papered over:**
- Authentication mechanics (API key format, header name, where a key is issued) — not shown on the general overview pages fetched; the GitBook mentions a downloadable Postman collection which likely documents this, but that collection itself was not opened in this pass (would require following an additional link/possibly signing in).
- Concrete request/response JSON examples for the translation (NMT) task specifically.
- Documented rate limits or usage quotas.
- Documented error-response shape/retry guidance.
- **Production access path**: the GitBook overview states PoC-level usage is available, but scaling beyond PoC ("paid version") requires directly contacting the Bhashini team — i.e. this is not a fully self-serve API-key-and-go platform the way a commercial SaaS API typically is, at least not per what was found in this pass.

This thinness in public technical documentation is itself an important input to §G (risks) — a realistic Stage 3 BHASHINI integration should budget time for direct outreach/registration with the Bhashini team and for exploratory, sandboxed API calls (which this task was explicitly told not to make) before committing to exact request/response handling code.

### B.5 Sources consulted

- [SpringEdge — How to Choose an SMS API Provider in India](https://www.springedge.com/how-to-choose-sms-api-provider-india)
- [SMSCountry — 10 Best SMS APIs in India for OTP & Bulk SMS](https://www.smscountry.com/blog/best-sms-apis-in-india/)
- [MessageBot — Best Enterprise OTP SMS API Providers in India](https://messagebot.in/blog/best-otp-sms-providers-in-india/)
- [Twilio — India: SMS Guidelines](https://www.twilio.com/en-us/guidelines/in/sms)
- [MSG91 — OTP Authentication API](https://msg91.com/in/otp)
- [MSG91 — API Docs Overview](https://docs.msg91.com/overview)
- [Bhashini APIs — GitBook, Overall Understanding of the API Calls](https://bhashini.gitbook.io/bhashini-apis)
- [Bhashini APIs — GitBook, Available Models for Usage](https://dibd-bhashini.gitbook.io/bhashini-apis/available-models-for-usage)
- [Bhashini official site — API documentation](https://bhashini.gov.in/api-documentation)

---

## C. Proposed Stage 3 architecture

### C.1 Canonical message pipeline (item 5)

```
Existing Traffic alert  ──┐
  (traffic_alert_eligibility,          Canonical English message
   UNCHANGED)              ├──────►    (already produced today by
Existing USI/Waste alert  ─┘            kannada_messages.py /
  (usi_engine + alerts.py,               integration/alerts.py's
   UNCHANGED)                            generate_alert() — no change
                                          needed, both already build
                                          an English string first)
                                                   │
                                                   ▼
                                   citizen_alert_dispatch.py
                                   (Stage 2 — dispatch/matching/dedup,
                                    UNCHANGED logic; new step added:
                                    resolve target language per citizen)
                                                   │
                              citizen preferred_language == 'en'? ──► use canonical English directly, skip BHASHINI
                                                   │
                              citizen preferred_language == 'kn'? ──► ALREADY have real Kannada text today
                                                                       (both existing generators already produce
                                                                       it natively) — BHASHINI not even needed
                                                                       for this direction; see note below.
                                                   │
                              citizen preferred_language == 'hi'? ──► NEW: bhashini_translator.translate(
                                                                             text, source='en', target='hi')
                                                                       success ──► real Hindi text
                                                                       failure ──► English + explicit status
                                                                                   (see §C.6)
                                                   │
                                                   ▼
                                   citizen_sms_provider.py (NEW)
                                   send_sms(mobile_number, text, language)
                                                   │
                                                   ▼
                                              Citizen's phone
```

**Important correction to the pipeline as literally diagrammed in the request:** the existing engines do **not** need BHASHINI in the middle for Kannada — `kannada_messages.py` and `integration/alerts.py` already generate real, hand-composed Kannada text today (confirmed in the Stage 2 audit: natural-sentence Kannada, not word-for-word translation). Routing that existing Kannada text through BHASHINI would be redundant work and a needless new failure point for a language this project already handles correctly. **BHASHINI's actual job in Stage 3 is narrower and more precise than "translate every message": translate the canonical English message to Hindi only** — the one language this project has never had real content for (confirmed gap, Stage 2 audit §1.5 and this document's §A.3/A.4 lineage). This keeps BHASHINI's blast radius small: one new call site, one new language, one new failure mode to design around — not a rewrite of a translation layer that already works for Kannada.

### C.2 Language rule (item 6)

Replacing Stage 2's current unconditional Hindi→English fallback with a real attempt, honestly reported:

| `preferred_language` | Stage 2 (today) | Stage 3 (proposed) |
|---|---|---|
| `en` | English | English (unchanged) |
| `kn` | Kannada (real, native) | Kannada (unchanged — no BHASHINI involved, see §C.1) |
| `hi` | English + `language_fallback = "hi_not_yet_supported_sent_en"` (always) | **Attempt** BHASHINI EN→HI translation. On success: real Hindi text, `language_sent = "hi"`, a new field e.g. `translation_source = "bhashini"`. On failure (timeout, error response, BHASHINI unavailable/unconfigured): fall back to English, **keep** `language_fallback` but with a more specific reason than today's blanket string — e.g. `"hi_bhashini_unavailable"` / `"hi_bhashini_call_failed"` / `"hi_bhashini_not_configured"` — so a failed *attempt* is distinguishable from "we never tried" (today's state) in the audit trail. |

**"Do not pretend Hindi is supported until BHASHINI is actually connected and tested"** — this rule is enforced structurally, not just by convention: the language-rule table above is not reachable at all until a `BHASHINI_API_KEY`-equivalent env var is actually set (mirroring the exact `tomtom_configured = bool(os.getenv(...))` pattern already in `app.py`). Absent that, Stage 3's code should fall through to *exactly* Stage 2's current behavior (unconditional `"hi_not_yet_supported_sent_en"`) — i.e. Stage 3 must not change what happens for Hindi citizens in an unconfigured/untested environment; it only adds a new, better path that only activates once it's real.

### C.3 SMS delivery safety (item 7)

Design only — no new tables yet, per instruction; described here as columns a *future* migration would add to Stage 2's existing `citizen_alert_deliveries` table (extending it, not replacing it), plus behavior:

- **Duplicate prevention**: already solved at the dispatch layer by Stage 2's `UNIQUE(citizen_id, alert_source, alert_key, alert_instance_ts)` constraint — that logic doesn't need to change. What Stage 3 adds is scoped to *within* one already-deduplicated delivery attempt: if the real send itself needs to be retried (network blip), the retry must reuse the same delivery row rather than the dedup logic re-deciding "should we alert this citizen" a second time. This argues for separating "was this citizen chosen for this alert instance" (Stage 2, unchanged) from "did the SMS for that chosen delivery actually go out" (new, Stage 3) as two different concerns on the same row.
- **Retry policy**: a small bounded retry (e.g. 2–3 attempts) with backoff, only for *transient* provider errors (timeout, 5xx, rate-limited) — never retried for a *permanent* rejection (invalid number, DLT template rejected, opted-out number) or the retry would just repeat the same failure. This mirrors the distinction the project already draws elsewhere between recoverable/expected states and hard failures (e.g. `traffic_incident_service.py`'s explicit severity tiers rather than a single pass/fail).
- **Provider timeout handling**: a real HTTP call needs an explicit timeout (the project's own `requests` usage elsewhere, e.g. `weather_logic.py`/TomTom calls, already sets timeouts rather than blocking indefinitely — Stage 3 should follow that existing convention) so one slow provider response can't stall the whole dispatch run.
- **Rate limiting**: two different rate limits matter and should not be conflated — (a) the *provider's* own rate limit (respect whatever MSG91/Twilio/etc. document, likely requests/second), independent of (b) this project's own per-citizen cooldown, which is already fully handled by Stage 2's dedup and needs no change.
- **Cooldown interaction**: explicitly **no change** to Stage 2's cooldown/eligibility logic (guardrail honored) — a real send failure must never cause Stage 2 to re-fire `is_alert_eligible()`/`maybe_alert_and_send()` again; a failed *delivery* and a failed *alert eligibility decision* are different layers and must stay different layers.
- **Delivery status / failed delivery status**: today's single hardcoded `'SIMULATED_NOT_SENT'` needs to become a small closed set of real states once a provider exists, e.g. `SIMULATED_NOT_SENT` (dev/no provider configured — unchanged default), `SENT` (provider accepted it), `FAILED` (provider rejected or all retries exhausted), `DELIVERED`/`UNDELIVERED` (only if the chosen provider offers delivery-status callbacks/webhooks — not all do, see §B; this is optional, not assumed available).
- **Provider message ID**: whatever id the provider's API returns for a successful send should be stored on the delivery row — needed to correlate a later delivery-status webhook (if the provider offers one) back to the right row, and useful for support/debugging without ever storing message content differently than today.
- **Audit trail**: Stage 2's `citizen_alert_deliveries` table already *is* the audit trail (one row per citizen per alert instance); Stage 3 extends its meaning (adds real status/provider-id columns to an existing table concept) rather than inventing a second, parallel logging mechanism.
- **Unsubscribe/deactivation behavior**: already fully solved by Stage 1 — `PATCH /api/citizens/{id}` with `status: "inactive"` already removes a citizen from every dispatch query (`list_active_citizens_for_ward`/`list_active_citizens_with_location_consent` both filter on `status='active'`). Stage 3 adds nothing here **except** one honest addition: an SMS provider's own opt-out signal (many require honoring a citizen who replies "STOP", separate from this app's own toggle) should, if the chosen provider surfaces it, feed back into setting that same `status='inactive'` — not a second, disconnected opt-out mechanism.

### C.4 Security (item 8)

- **Where provider API keys live**: environment variables only, loaded exactly the way `app.py` already loads `ORS_API_KEY`/`TOMTOM_API_KEY`/`OPENWEATHER_API_KEY` today (`os.getenv(...)`) — no new pattern needed, the existing one is correct and this project has already paid the cost of learning why (§A.4).
- **`.env` handling**: `python-dotenv` is already a dependency and already wired up in `app.py` (`load_dotenv()` for both cwd and project-root `.env`) — a new provider key is just another line in the same, already-gitignored `.env` file. No new loading mechanism needed.
- **Secrets must never be committed**: already enforced by the existing `.gitignore` (§A.4) — Stage 3 just needs to keep using it, and specifically must **not** repeat the exact prior incident's shape (a key hardcoded as a Python literal "temporarily" and forgotten) for the SMS or BHASHINI key.
- **Production/dev separation**: this project has no deployed "production" — "production" here practically means "an environment where `CITIZEN_ALERTS_DEV_MODE=false` and a real provider key is set," vs. today's dev/demo state. The two should be **independent** env vars (a provider key existing doesn't have to force dev mode off, and dev mode being off without a configured provider must degrade safely, not crash — see §C.6's "not configured" branch) rather than one flag implying the other.
- **Should OTP codes ever appear in API responses**: no, once a real provider is configured and dev mode is off — already the code's own stated intent (§A.2); Stage 3's job is to make sure the "once a real provider is configured" half of that sentence actually becomes reachable, and to treat "provider configured" and "dev mode off" as a state that should be set together operationally even though they're independent flags technically (a misconfiguration where dev mode is left on with a real provider active would mean OTP codes are both sent for real *and* exposed in the API response — worth an explicit startup-time warning log if that combination is ever detected, not a hard block, since this is a college project and a hard block could be more disruptive than helpful during development).

### C.5 Cost / practicality (item 9)

| | Needs an external account? | Costs money? | Can stay simulated for dev? | Demonstrable without spending? |
|---|---|---|---|---|
| SMS sending | Yes (any real provider) | Yes (₹0.10–0.20/SMS typical, §B.3) | Yes — today's `SIMULATED_NOT_SENT` path stays the default whenever no provider key is configured | Yes — a demo can show the exact same dispatch/dedup/matching logic running live, with the delivery log showing what *would* have been sent to whom, in which language, with which status; this is genuinely most of the engineering value and needs zero spend |
| DLT registration (domestic sender ID) | Yes, separate from the SMS provider account | Registration itself is typically free-to-low-cost per source material in §B, but is slow (days) and entity-verification-heavy | N/A — orthogonal to development, only needed for a real domestic send | Not really — this is paperwork, not something to demo |
| BHASHINI (PoC tier) | Likely yes, per §B.4 (even PoC access appears to need registering with Bhashini) | PoC tier appears free; scaling requires contacting Bhashini directly (§B.4) | Yes — `hi_not_yet_supported_sent_en`/its more specific Stage 3 variants (§C.2) stay the honest default until a real key is obtained and tested | Partially — the *pipeline* (canonical English → target-language slot → SMS) can be fully demoed with Kannada (already real, no BHASHINI needed) and with a documented "Hindi via BHASHINI: designed, pending API access" note, without ever calling the real endpoint |

**Recommendation for a college project**, plainly: build and demonstrate the entire Stage 3 architecture (provider abstraction, retry/timeout handling, delivery-status columns, BHASHINI call site with its failure-fallback) in **fully simulated form first** — same posture Stage 1/2 already used successfully — so the whole system is provably correct via tests before a single rupee or a single real API registration is involved. Real SMS sending and a real BHASHINI key are then each a narrow, isolated, optional "turn it on" step (a provider module behind one `if configured:` branch each) rather than a prerequisite for finishing the project. This also directly serves the "no fabricated behavior" rule elsewhere in this project's own conventions — nothing has to be *claimed* as sent for real until it genuinely is.

### C.6 Exact architecture (item 10)

**New modules (proposed, not created):**
- `traffic_module/backend/citizen_sms_provider.py` — single seam for real sending. Exposes one function, e.g. `send_sms(mobile_number, text, language) -> {"status", "provider_message_id", "raw_response_summary"}`, internally branching on which provider (if any) is configured; returns a `NOT_CONFIGURED` status (not an exception) when no provider key is set, so callers never need a try/except just to stay in today's simulated mode. Owns provider-specific timeout/retry logic (§C.3) so `citizen_alert_dispatch.py` doesn't need to know which vendor is behind it.
- `traffic_module/backend/bhashini_translator.py` — single seam for translation. Exposes e.g. `translate_to_hindi(english_text) -> {"status", "text_hi"}`, returns `NOT_CONFIGURED`/`UNAVAILABLE`/`FAILED` (never raises) so the language-rule fallback in §C.2 is a simple status check, not exception handling scattered through dispatch code. Optionally memoizes/caches a translation per distinct English string within a process run (see caching note below) — never persisted as a new table in this design (per instruction), an in-memory cache only, and only worth it because Stage 2's own message templates are already a small, mostly-fixed set of strings (per-band, per-incident-type), not free-form text — so the same English sentence recurs often and re-translating it identically every dispatch run would be wasted calls, not wasted correctness.

**Modules that would need modification (additive only, same posture as Stage 1/2 — no rewrite):**
- `traffic_module/backend/citizen_alert_dispatch.py` — `_resolve_delivery_language()` gains the BHASHINI branch for `'hi'` (currently an unconditional fallback); `_record_delivery()` gains the new status values and provider-message-id field; **no change** to the matching/dedup/ward-resolution logic itself.
- `traffic_module/backend/citizen_otp.py` — `generate_otp()` gains an optional real-send call via `citizen_sms_provider.send_sms()`; `DEV_MODE`'s existing meaning is preserved exactly, just given something to do when off.
- `traffic_module/backend/app.py` — the OTP endpoints (`/api/citizens/register`, `/resend-otp`) call the new send step; no other existing route changes.
- `traffic_module/frontend/src/components/CitizenAlertRegistration.jsx` — the OTP step's "Development Mode" banner becomes conditional on whether the backend reports dev mode is actually on (it already receives `dev_mode` in the API response — no new endpoint needed, just stop assuming it's always true); the "Alert delivery status" panel (Stage 2) gains real status labels (`Sent`/`Failed`/`Simulated`) instead of always showing "Simulated."

**API endpoints that would need changes:** none new required structurally — `POST /api/citizens/dispatch/run` and `GET /api/citizens/{id}/alert-deliveries` (both Stage 2) already exist and already return a `status` per delivery; Stage 3 just widens the set of values `status` can hold and adds 1–2 optional fields (`provider_message_id`, a more specific `language_fallback` reason). `/api/citizens/register` and `/resend-otp` keep their existing shapes; `dev_mode`/`dev_otp` simply become conditionally absent once real sending is live.

**Database changes:** **none proposed yet, per instruction.** For a future stage, the natural (not-yet-created) change would be additive columns on Stage 2's existing `citizen_alert_deliveries` table (`provider_message_id`, a widened `status` value set, possibly `delivery_confirmed_at` if a provider's callback is used) — not a new table, and not a schema change to the `citizens` table itself.

**Frontend changes:** described above (dev-mode banner becomes conditional; delivery-status panel shows real states) — both are display-only changes to a component that already fetches this data; no new API calls needed beyond what Stage 2 already added.

**Environment variables required (proposed names, following the project's existing `X_API_KEY` convention exactly):**
- `CITIZEN_ALERTS_SMS_PROVIDER` (e.g. `"none"` default / a provider identifier once chosen)
- `CITIZEN_ALERTS_SMS_API_KEY` (or provider-specific name once a specific vendor is chosen — see §B for why that choice needs its own follow-up, not a default here)
- `CITIZEN_ALERTS_SMS_SENDER_ID` (the DLT-approved sender id, once domestic sending is set up)
- `BHASHINI_API_KEY` (and whatever companion identifier Bhashini's actual auth scheme turns out to require — left open per §B.4's disclosed documentation gap)
- `CITIZEN_ALERTS_DEV_MODE` — **already exists**, unchanged; Stage 3 doesn't add a new flag for this, it makes the existing one's "off" branch meaningful.

**Testing strategy** (mirroring Stage 1/2's own already-proven pattern — real logic, simulated network boundary): unit-test `citizen_sms_provider.send_sms()` and `bhashini_translator.translate_to_hindi()` against a mocked HTTP layer (`requests`-mocking, or dependency-injecting a fake transport) covering success, timeout, 4xx/5xx, and malformed-response cases — never a real network call in the test suite, matching this project's own explicit rule. Unit-test `_resolve_delivery_language()`'s new branching (configured+success, configured+failure, not-configured) the same deterministic-monkeypatch way Stage 2's own test suite already does for `integration_bridge.get_active_alerts()`. Integration-test the full dispatch path with both providers mocked, confirming a delivery row ends up with the right `status`/`language_sent`/`language_fallback` combination for each of the matrix in §C.2. A real, opt-in, manually-triggered "smoke test" against the real provider/BHASHINI sandbox (once credentials exist) would be a separate, explicitly-labeled script — never part of the default automated suite, so the test suite never accidentally sends a real SMS or spends real BHASHINI quota just by being run.

---

## D. Security considerations

Consolidated from §C.4 and §A.4: use environment variables exclusively (matches the project's own established, already-gitignored pattern), never commit a key (this project has already learned this lesson once, the hard way — §A.4), keep dev-mode-off and provider-configured as independent but operationally-paired flags, never expose an OTP code once real sending is live, and treat DLT/sender-ID registration paperwork as a compliance prerequisite for *domestic* sending specifically (not needed for dev/simulated mode, not needed for Twilio's international-gateway path per §B.2, but required for a properly-branded domestic sender id with any provider). One additional point not covered above: a real provider's API key, once set, should be treated as capable of spending real money per request — the `NOT_CONFIGURED`-returns-a-status-not-an-exception design in §C.6 is partly a safety property too, since it means a missing/misconfigured key can never accidentally fall through to some other unintended send path; it simply does nothing, the same safe-by-default posture this project has used throughout.

## E. Cost / practicality

See §C.5 for the full breakdown. One-line summary: everything can be built, tested, and demonstrated for ₹0 by keeping simulated mode as the default and treating both real SMS and real BHASHINI as opt-in, individually-togglable, unconfigured-by-default integrations — exactly Stage 1/2's own already-successful pattern, extended rather than abandoned.

## F. Exact implementation plan

A future build stage (not this one) would reasonably sequence as:
1. `citizen_sms_provider.py` and `bhashini_translator.py`, both fully built and unit-tested against mocked transports, both defaulting to `NOT_CONFIGURED` — zero external dependency to reach a working, testable state.
2. Wire `citizen_alert_dispatch.py`'s `_resolve_delivery_language()` and `_record_delivery()` to the new modules, per §C.2/§C.6 — testable entirely with mocks, no real keys needed yet.
3. Wire `citizen_otp.py`/`app.py`'s OTP endpoints to `citizen_sms_provider.py`, preserving `DEV_MODE` exactly, per §A.2 — same mock-only testability.
4. Frontend display updates (§C.6) — cosmetic, no new API surface.
5. **Separately, and only when/if actually desired:** register one real SMS provider account (choice made deliberately per an updated version of §B's comparison, at that time, since pricing/features/current provider status can all shift), complete DLT registration if domestic sending is wanted, register for Bhashini API access, and flip both from simulated to real behind their respective env vars — each independently, each reversible by unsetting the var, each never required for the rest of the project to keep working.

## G. Risks / open questions

- **Bhashini's real authentication/rate-limit/error-response contract is not fully confirmed from public documentation** (§B.4) — the design in §C is deliberately defensive (status-based, never assumes a specific error shape) precisely because this wasn't nailed down; the actual integration will need to be adjusted once real API docs/a Postman collection are obtained, possibly requiring direct contact with the Bhashini team for anything beyond PoC-level access.
- **Which SMS provider to actually choose is explicitly left open** — §B compares the *shape* of the decision (Twilio international-gateway vs. domestic-DLT vs. India-specific aggregator) with real, current, cited facts, but deliberately does not pick one, per the instruction not to choose out of familiarity; that choice needs its own short follow-up once Stage 3 is actually greenlit, ideally re-checking pricing/current terms at that time since both change.
- **DLT registration timeline (paperwork, not engineering) could be the actual critical path** for any *domestic* real sending, independent of how fast the code itself is built — worth flagging to whoever owns the project timeline, separate from the engineering estimate in §F.
- **BHASHINI production access beyond PoC appears to require direct outreach**, per §B.4 — this is a scope/timeline risk, not a code risk, and should be sized realistically rather than assumed to be an instant self-serve signup.
- **This report intentionally does not verify BHASHINI's or any SMS provider's current uptime, actual latency, or exact current pricing** beyond what's cited in §B — those are the kind of facts that go stale fast and should be re-checked at actual build time, not locked in from this audit.
