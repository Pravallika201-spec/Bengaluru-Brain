"""
Stage 3C -- real English -> Hindi translation seam via BHASHINI, kept
behind the same fail-closed posture Stage 3B established for
citizen_sms_provider.py. Per the Stage 3 audit (Claude outputs/
STAGE3_SMS_BHASHINI_AUDIT_2026-09-29.md, section B.4/C.1): BHASHINI's
actual necessary role here is narrow -- English -> Hindi only. Kannada
already has real, natively-authored content everywhere in this project
(kannada_messages.py, integration/alerts.py) and is NOT routed through
this module; this module is never called for a Kannada-preferring
citizen.

WHAT THIS MODULE DOES AND DOES NOT DO
--------------------------------------
- It exposes exactly ONE function callers should use: translate_to_hindi().
  It takes a canonical English alert string and returns either a real
  Hindi translation or the original English text, with an explicit
  status saying which. It never decides WHETHER or to WHOM a citizen is
  alerted -- that remains entirely citizen_alert_dispatch.py's job
  (eligibility, ward/location matching, cooldown, dedup are all
  untouched by this stage). It has no knowledge of citizens, mobile
  numbers, or the SMS provider at all.
- It does not expose any HTTP endpoint -- there is no FastAPI route
  anywhere in this file.
- It never calls the real BHASHINI API unless BOTH (a) all required
  credentials are configured (see CONFIGURATION below) AND (b) the
  caller actually invokes translate_to_hindi() -- there is no DEV_MODE
  toggle here because, unlike SMS sending, attempting a translation has
  no side effect on anyone's phone; the safety property that matters is
  "never crash, never fabricate a translation, always have a safe
  English fallback" instead, enforced on every code path below.
- It never logs, prints, or includes in any returned error string the
  ULCA user id or API key. Only a short error tag is ever surfaced.

REAL BHASHINI API SHAPE (per the Stage 3 audit's own documented
research -- a genuine two-call pipeline, not a single request):
  1. POST BHASHINI_PIPELINE_CONFIG_URL (Meity/ULCA's public "Pipeline
     Config" endpoint) with headers {"userID": ..., "ulcaApiKey": ...}
     and a body naming the translation task (en->hi) and your own
     BHASHINI_PIPELINE_ID. The response carries a per-call
     `callbackUrl`, an `inferenceApiKey` (a short-lived bearer credential
     for step 2, NOT your long-lived ULCA key), and the `serviceId` the
     actual model is registered under.
  2. POST that `callbackUrl` (a genuinely different host than step 1 --
     this is BHASHINI's actual documented "Pipeline Compute" step) with
     that response's own inferenceApiKey as the auth header, sending the
     English text and the serviceId from step 1. The response carries
     the translated Hindi string.
  Both calls are real HTTP POSTs made only when translate_to_hindi() is
  called with full configuration present; a test suite must mock both
  (see test_bhashini_translator.py's own docstring).

CONFIGURATION (environment variables only -- see traffic_module/.env.example;
never hardcode real values anywhere in source):
    BHASHINI_ULCA_USER_ID        -- ULCA user id (step 1 auth).
    BHASHINI_ULCA_API_KEY        -- ULCA API key (step 1 auth).
    BHASHINI_PIPELINE_ID         -- your own registered BHASHINI pipeline
                                     id (obtained from the BHASHINI
                                     portal/Pipeline Search -- there is
                                     no working default; the Stage 3
                                     audit's own research explicitly
                                     flagged this as undocumented
                                     publicly, so no id is fabricated
                                     here).
    BHASHINI_PIPELINE_CONFIG_URL -- optional, defaults to the public
                                     Meity/ULCA endpoint documented in
                                     the Stage 3 audit
                                     ("https://meity-auth.ulca.in/ulca/
                                     apis/v0/model/getModelsPipeline").
    BHASHINI_TIMEOUT_SECONDS     -- optional, defaults to 10 (applied to
                                     EACH of the two HTTP calls
                                     separately, not their sum).

STATUS CONTRACT
----------------
translate_to_hindi() always returns a dict and never raises for an
ordinary failure:
    {"status": "TRANSLATED" | "FALLBACK_ENGLISH",
     "text": str,
     "error": str | None}

  - TRANSLATED: `text` is the real Hindi string BHASHINI returned;
    `error` is None.
  - FALLBACK_ENGLISH: `text` is the ORIGINAL english_text, byte-for-byte
    unchanged; `error` is a short tag explaining why (e.g.
    "bhashini_not_configured", "bhashini_config_timeout",
    "bhashini_compute_http_500", "bhashini_config_response_unparseable").
    This is the exact same fail-closed contract citizen_sms_provider.py
    uses for its own FAILED status -- a caller can always safely use
    `text` without checking `status` first, but should surface/record
    `status`/`error` for visibility (this project's own stated
    principle: never silently mis-send, never silently hide a gap).
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

STATUS_TRANSLATED = "TRANSLATED"
STATUS_FALLBACK = "FALLBACK_ENGLISH"

_SOURCE_LANGUAGE = "en"
_TARGET_LANGUAGE = "hi"
_TASK_TYPE = "translation"

_DEFAULT_PIPELINE_CONFIG_URL = "https://meity-auth.ulca.in/ulca/apis/v0/model/getModelsPipeline"

_TRUTHY_BLANK = {"", "your_key_here", "placeholder", "changeme"}


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if value.lower() in _TRUTHY_BLANK:
        return None
    return value or None


def _pipeline_config_url() -> str:
    return _env("BHASHINI_PIPELINE_CONFIG_URL") or _DEFAULT_PIPELINE_CONFIG_URL


def _timeout_seconds() -> float:
    raw = _env("BHASHINI_TIMEOUT_SECONDS")
    try:
        return float(raw) if raw else 10.0
    except ValueError:
        return 10.0


def bhashini_configured() -> bool:
    """Mirrors citizen_sms_provider.sms_provider_configured() exactly.
    True only when every credential BHASHINI's Pipeline Config call
    requires is present and non-placeholder. Read fresh every call."""
    return bool(
        _env("BHASHINI_ULCA_USER_ID")
        and _env("BHASHINI_ULCA_API_KEY")
        and _env("BHASHINI_PIPELINE_ID")
    )


def translate_to_hindi(english_text: str) -> dict:
    """The only function other backend code should call. See module
    docstring for the full status contract. Never raises; always falls
    back to returning `english_text` unchanged when anything prevents a
    real translation."""
    if not english_text or not english_text.strip():
        return {"status": STATUS_FALLBACK, "text": english_text or "", "error": "empty_source_text"}

    if not bhashini_configured():
        print(
            "[CITIZEN ALERT TRANSLATION] a Hindi-preferring citizen needs "
            "translation but BHASHINI is not fully configured -- falling "
            "back to English. Never fabricating a translation."
        )
        return {"status": STATUS_FALLBACK, "text": english_text, "error": "bhashini_not_configured"}

    try:
        return _translate_via_bhashini(english_text)
    except Exception as exc:  # last-resort safety net: a translation
        # attempt must never raise into the dispatch layer.
        print(f"[CITIZEN ALERT TRANSLATION] unexpected error attempting translation: {type(exc).__name__}")
        return {"status": STATUS_FALLBACK, "text": english_text, "error": f"unexpected_error:{type(exc).__name__}"}


def _translate_via_bhashini(english_text: str) -> dict:
    config_result = _get_pipeline_config()
    if config_result.get("error"):
        return {"status": STATUS_FALLBACK, "text": english_text, "error": config_result["error"]}

    compute_result = _compute_translation(
        callback_url=config_result["callback_url"],
        inference_api_key_name=config_result["inference_api_key_name"],
        inference_api_key_value=config_result["inference_api_key_value"],
        service_id=config_result["service_id"],
        english_text=english_text,
    )
    if compute_result.get("error"):
        return {"status": STATUS_FALLBACK, "text": english_text, "error": compute_result["error"]}

    translated = compute_result.get("text", "")
    if not translated or not translated.strip():
        print("[CITIZEN ALERT TRANSLATION] BHASHINI returned an empty translation -- falling back to English.")
        return {"status": STATUS_FALLBACK, "text": english_text, "error": "bhashini_empty_translation"}

    return {"status": STATUS_TRANSLATED, "text": translated, "error": None}


def _get_pipeline_config() -> dict:
    """Step 1: Pipeline Config. Returns either
    {"callback_url", "inference_api_key_name", "inference_api_key_value",
    "service_id", "error": None} on success, or {"error": "<tag>"} (all
    other keys absent) on any failure -- never raises."""
    user_id = _env("BHASHINI_ULCA_USER_ID")
    api_key = _env("BHASHINI_ULCA_API_KEY")
    pipeline_id = _env("BHASHINI_PIPELINE_ID")

    body = {
        "pipelineTasks": [
            {"taskType": _TASK_TYPE, "config": {"language": {"sourceLanguage": _SOURCE_LANGUAGE, "targetLanguage": _TARGET_LANGUAGE}}}
        ],
        "pipelineRequestConfig": {"pipelineId": pipeline_id},
    }

    try:
        response = requests.post(
            _pipeline_config_url(),
            headers={"userID": user_id, "ulcaApiKey": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=_timeout_seconds(),
        )
    except requests.exceptions.Timeout:
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-config request timed out after {_timeout_seconds()}s")
        return {"error": "bhashini_config_timeout"}
    except requests.exceptions.RequestException as exc:
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-config request failed: {type(exc).__name__}")
        return {"error": f"bhashini_config_request_error:{type(exc).__name__}"}

    if response.status_code not in (200, 201):
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-config returned HTTP {response.status_code}")
        return {"error": f"bhashini_config_http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        print("[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-config response was not valid JSON")
        return {"error": "bhashini_config_response_unparseable"}

    try:
        endpoint = payload["pipelineInferenceAPIEndPoint"]
        callback_url = endpoint["callbackUrl"]
        inference_key = endpoint["inferenceApiKey"]
        inference_key_name = inference_key["name"]
        inference_key_value = inference_key["value"]
        service_id = payload["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    except (KeyError, IndexError, TypeError):
        print("[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-config response was missing expected fields")
        return {"error": "bhashini_config_response_missing_fields"}

    return {
        "callback_url": callback_url,
        "inference_api_key_name": inference_key_name,
        "inference_api_key_value": inference_key_value,
        "service_id": service_id,
        "error": None,
    }


def _compute_translation(callback_url: str, inference_api_key_name: str,
                          inference_api_key_value: str, service_id: str,
                          english_text: str) -> dict:
    """Step 2: Pipeline Compute. Returns {"text": "<hindi>", "error": None}
    on success, or {"error": "<tag>"} on any failure -- never raises. The
    inference API key from step 1 is passed only via the headers dict --
    never interpolated into any printed string."""
    body = {
        "pipelineTasks": [
            {
                "taskType": _TASK_TYPE,
                "config": {
                    "language": {"sourceLanguage": _SOURCE_LANGUAGE, "targetLanguage": _TARGET_LANGUAGE},
                    "serviceId": service_id,
                },
            }
        ],
        "inputData": {"input": [{"source": english_text}]},
    }

    try:
        response = requests.post(
            callback_url,
            headers={inference_api_key_name: inference_api_key_value, "Content-Type": "application/json"},
            json=body,
            timeout=_timeout_seconds(),
        )
    except requests.exceptions.Timeout:
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-compute request timed out after {_timeout_seconds()}s")
        return {"error": "bhashini_compute_timeout"}
    except requests.exceptions.RequestException as exc:
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-compute request failed: {type(exc).__name__}")
        return {"error": f"bhashini_compute_request_error:{type(exc).__name__}"}

    if response.status_code not in (200, 201):
        print(f"[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-compute returned HTTP {response.status_code}")
        return {"error": f"bhashini_compute_http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        print("[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-compute response was not valid JSON")
        return {"error": "bhashini_compute_response_unparseable"}

    try:
        translated = payload["pipelineResponse"][0]["output"][0]["target"]
    except (KeyError, IndexError, TypeError):
        print("[CITIZEN ALERT TRANSLATION] BHASHINI pipeline-compute response was missing expected fields")
        return {"error": "bhashini_compute_response_missing_fields"}

    return {"text": translated, "error": None}
