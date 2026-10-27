"""
Stage 3B -- real SMS delivery seam for a configured provider (Exotel),
kept behind the SAME CITIZEN_ALERTS_DEV_MODE toggle citizen_otp.py
already established in Stage 1, per the Stage 3 audit's own proposed
design (Claude outputs/STAGE3_SMS_BHASHINI_AUDIT_2026-09-29.md, section
C.6): "single seam for real sending... returns a NOT_CONFIGURED-style
status (not an exception) when no provider key is set, so callers never
need a try/except just to stay in today's simulated mode."

WHAT THIS MODULE DOES AND DOES NOT DO
--------------------------------------
- It exposes exactly ONE function callers should use: send_sms(). It
  decides HOW to attempt delivering a message it is handed. It never
  decides WHETHER a citizen should be alerted -- that decision (eligibility,
  ward/location matching, cooldown, deduplication) is made entirely by
  citizen_alert_dispatch.py's existing dispatch_traffic_alerts() /
  dispatch_usi_alerts(), exactly as before. This module receives an
  already-approved citizen mobile number and an already-composed message
  string; nothing else.
- It does not expose any "send arbitrary SMS to any number" HTTP endpoint
  -- there is no FastAPI route anywhere in this file. It is a plain
  Python module, importable only from other backend code.
- It never sends a real SMS while CITIZEN_ALERTS_DEV_MODE is on (default).
  DEV_MODE on means this module makes NO network call at all -- not a
  mocked one, an ACTUAL absence of any HTTP request -- and returns the
  exact same "SIMULATED_NOT_SENT" status citizen_alert_dispatch.py has
  recorded since Stage 2.
- It never logs, prints, or includes in any returned error string the
  Exotel API key, API token, or full raw response body. Only a status
  code / short error tag and (when present) the provider's own message
  id are ever surfaced.

CONFIGURATION (environment variables only -- see traffic_module/.env.example
for the placeholder file; never hardcode real values anywhere in source):
    CITIZEN_ALERTS_DEV_MODE   -- already exists (citizen_otp.py). "true"
                                 (default) = never send for real.
    EXOTEL_ACCOUNT_SID        -- Exotel Account SID.
    EXOTEL_API_KEY            -- Exotel API Key (Basic Auth username).
    EXOTEL_API_TOKEN          -- Exotel API Token (Basic Auth password).
    EXOTEL_SENDER_ID          -- DLT-approved sender id / ExoPhone number
                                 used as the SMS "From".
    EXOTEL_SUBDOMAIN          -- optional, defaults to "api.exotel.com"
                                 (Exotel's public docs show this as the
                                 API host; some accounts are provisioned
                                 on a region-specific subdomain instead).
    CITIZEN_ALERTS_SMS_TIMEOUT_SECONDS -- optional, defaults to 10.

STATUS CONTRACT
----------------
send_sms() always returns a dict and never raises for an ordinary
provider/network failure:
    {"status": "SIMULATED_NOT_SENT" | "SENT" | "FAILED",
     "provider_message_id": str | None,
     "error": str | None}

  - DEV_MODE on (default, unchanged Stage 2 behavior): SIMULATED_NOT_SENT,
    no network call.
  - DEV_MODE off but not fully configured (any of the four EXOTEL_* vars
    above missing/blank): FAILED, error="sms_provider_not_configured".
    This is a deliberate fail-closed choice -- Stage 3B must never
    silently fall back to pretending a message was sent, or silently
    fall back to DEV_MODE's simulated status, when a real send was
    actually requested (CITIZEN_ALERTS_DEV_MODE=false) but the operator
    forgot to finish configuring credentials.
  - DEV_MODE off and configured: a real HTTPS POST to Exotel's Send SMS
    API, with an explicit timeout, Basic Auth credentials that are never
    logged, and the provider's own SMS Sid captured as
    provider_message_id when the response includes one.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except Exception:
    pass

STATUS_SIMULATED = "SIMULATED_NOT_SENT"
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"

_TRUTHY_BLANK = {"", "your_key_here", "placeholder", "changeme"}


def _dev_mode() -> bool:
    """Read fresh on every call (not cached at import time) so tests can
    monkeypatch os.environ and so a real process can flip this via env
    reload without a restart-order dependency. Mirrors citizen_otp.py's
    own DEV_MODE expression exactly: default on, off only when explicitly
    set to 'false'."""
    return os.getenv("CITIZEN_ALERTS_DEV_MODE", "true").strip().lower() != "false"


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if value.lower() in _TRUTHY_BLANK:
        return None
    return value or None


def _exotel_subdomain() -> str:
    return _env("EXOTEL_SUBDOMAIN") or "api.exotel.com"


def _timeout_seconds() -> float:
    raw = _env("CITIZEN_ALERTS_SMS_TIMEOUT_SECONDS")
    try:
        return float(raw) if raw else 10.0
    except ValueError:
        return 10.0


def sms_provider_configured() -> bool:
    """Mirrors the exact `tomtom_configured = bool(os.getenv(...))`
    pattern app.py already uses for TomTom/OpenWeather. True only when
    every credential Exotel's Send SMS API requires is present and
    non-placeholder. Read fresh every call -- never cached -- so tests
    and real config-reload both see current environment state."""
    return bool(
        _env("EXOTEL_ACCOUNT_SID")
        and _env("EXOTEL_API_KEY")
        and _env("EXOTEL_API_TOKEN")
        and _env("EXOTEL_SENDER_ID")
    )


def send_sms(mobile_number: str, text: str, language: str = "en") -> dict:
    """The only function other backend code should call. See module
    docstring for the full status contract. `mobile_number` is expected
    already in the project's normalized +91XXXXXXXXXX form (see
    citizen_registry.validate_mobile_number) -- this function does not
    reformat or guess a number, it sends to exactly what it is given."""
    if _dev_mode():
        print(
            f"[SIMULATED CITIZEN SMS] status={STATUS_SIMULATED} "
            f"lang={language} (CITIZEN_ALERTS_DEV_MODE is on -- no network call made)"
        )
        return {"status": STATUS_SIMULATED, "provider_message_id": None, "error": None}

    if not sms_provider_configured():
        print(
            "[CITIZEN SMS] a real send was requested (CITIZEN_ALERTS_DEV_MODE=false) "
            "but no SMS provider is fully configured -- recording FAILED. "
            "Never silently falling back to SIMULATED_NOT_SENT."
        )
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": "sms_provider_not_configured"}

    try:
        return _send_via_exotel(mobile_number, text)
    except Exception as exc:  # last-resort safety net: a delivery attempt
        # must never raise into the dispatch layer, whatever goes wrong.
        print(f"[CITIZEN SMS] unexpected error attempting send: {type(exc).__name__}")
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": f"unexpected_error:{type(exc).__name__}"}


def _exotel_send_url() -> str:
    sid = _env("EXOTEL_ACCOUNT_SID")
    return f"https://{_exotel_subdomain()}/v1/Accounts/{sid}/Sms/send"


def _send_via_exotel(mobile_number: str, text: str) -> dict:
    """Real HTTPS call to Exotel's Send SMS API. Auth is passed only via
    the `auth=` kwarg (HTTP Basic Auth) -- never interpolated into a
    printed string, never included in the returned dict. Exotel's
    documented endpoint shape:
    https://<api_key>:<api_token>@api.exotel.com/v1/Accounts/<sid>/Sms/send
    (used here as method params rather than embedded in the URL, so the
    key/token can never end up in a log line that prints the URL)."""
    api_key = _env("EXOTEL_API_KEY")
    api_token = _env("EXOTEL_API_TOKEN")
    sender_id = _env("EXOTEL_SENDER_ID")

    try:
        response = requests.post(
            _exotel_send_url(),
            auth=(api_key, api_token),
            data={"From": sender_id, "To": mobile_number, "Body": text},
            timeout=_timeout_seconds(),
        )
    except requests.exceptions.Timeout:
        print(f"[CITIZEN SMS] Exotel request timed out after {_timeout_seconds()}s")
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": "provider_timeout"}
    except requests.exceptions.RequestException as exc:
        # exc's own str() can include the request URL but never the auth
        # tuple (requests does not embed Basic Auth credentials in
        # exception messages) -- only the exception class name is logged
        # here regardless, to stay unambiguous about never leaking
        # credentials even if that assumption were ever wrong.
        print(f"[CITIZEN SMS] Exotel request failed: {type(exc).__name__}")
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": f"provider_request_error:{type(exc).__name__}"}

    return _parse_exotel_response(response)


def _parse_exotel_response(response: "requests.Response") -> dict:
    if response.status_code not in (200, 201, 202):
        print(f"[CITIZEN SMS] Exotel returned HTTP {response.status_code}")
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": f"provider_http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        print("[CITIZEN SMS] Exotel response was not valid JSON")
        return {"status": STATUS_FAILED, "provider_message_id": None, "error": "provider_response_unparseable"}

    sms_info = payload.get("SMSMessage") or {}
    message_id = sms_info.get("Sid")
    status_field = str(sms_info.get("Status") or "").strip().lower()

    if status_field in ("failed", "expired", "rejected", "blacklisted"):
        return {"status": STATUS_FAILED, "provider_message_id": message_id, "error": f"provider_status_{status_field}"}

    return {"status": STATUS_SENT, "provider_message_id": message_id, "error": None}
