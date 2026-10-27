"""
Stage 3C tests for bhashini_translator.py.

Hard rule for this entire file, same as test_citizen_sms_provider.py:
NOTHING here may ever reach the real network. Every "configured"-path
test monkeypatches `requests.post` to a fake before exercising the
translation branches; the autouse `block_real_sockets` fixture is an
extra, independent safety net patching socket.create_connection to
raise immediately.

BHASHINI's real API is a genuine two-call pipeline (see
bhashini_translator.py's own module docstring): Pipeline Config, then
Pipeline Compute against whatever callback URL Config returned. Tests
that need a successful path mock requests.post with a callable that
inspects the URL/body to decide which of the two calls it's answering,
since both calls go through the same requests.post seam.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bhashini_translator as bh


@pytest.fixture(autouse=True)
def block_real_sockets(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError(
            "A test attempted a real network connection. This must never "
            "happen in the Stage 3C BHASHINI translator test suite."
        )
    monkeypatch.setattr("socket.create_connection", _blocked)
    yield


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "BHASHINI_ULCA_USER_ID",
        "BHASHINI_ULCA_API_KEY",
        "BHASHINI_PIPELINE_ID",
        "BHASHINI_PIPELINE_CONFIG_URL",
        "BHASHINI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _configure(monkeypatch, timeout=None):
    monkeypatch.setenv("BHASHINI_ULCA_USER_ID", "test-user-never-real")
    monkeypatch.setenv("BHASHINI_ULCA_API_KEY", "test-ulca-key-never-real")
    monkeypatch.setenv("BHASHINI_PIPELINE_ID", "test-pipeline-id")
    if timeout is not None:
        monkeypatch.setenv("BHASHINI_TIMEOUT_SECONDS", str(timeout))


_GOOD_CONFIG_PAYLOAD = {
    "pipelineResponseConfig": [
        {"taskType": "translation", "config": [{"serviceId": "test-service-id"}]}
    ],
    "pipelineInferenceAPIEndPoint": {
        "callbackUrl": "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
        "inferenceApiKey": {"name": "Authorization", "value": "test-inference-key-never-real"},
    },
}


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, raise_on_json=False):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json:
            raise ValueError("not json")
        return self._json_data


def _good_compute_payload(hindi_text="नमस्ते, यह एक परीक्षण है।"):
    return {"pipelineResponse": [{"taskType": "translation", "output": [{"target": hindi_text}]}]}


def _make_two_call_router(config_response, compute_response):
    """Returns a fake requests.post that answers the FIRST call
    (Pipeline Config, to bh._pipeline_config_url()) with config_response
    and every subsequent call (Pipeline Compute, to whatever callbackUrl
    Config claimed) with compute_response -- exactly mirroring the real
    two-hop pipeline without hardcoding call order beyond "config first"."""
    calls = {"count": 0, "urls": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["urls"].append(url)
        calls["count"] += 1
        if calls["count"] == 1:
            return config_response
        return compute_response

    return fake_post, calls


# ---------------------------------------------------------------------
# Not configured / partially configured -- must fail closed, no network
# ---------------------------------------------------------------------

def test_not_configured_falls_back_to_english_without_network_call(monkeypatch):
    calls = {"post": 0}
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result == {"status": bh.STATUS_FALLBACK, "text": "Heavy traffic ahead.", "error": "bhashini_not_configured"}
    assert calls["post"] == 0


def test_partially_configured_falls_back_to_english(monkeypatch):
    monkeypatch.setenv("BHASHINI_ULCA_USER_ID", "test-user-never-real")
    monkeypatch.setenv("BHASHINI_ULCA_API_KEY", "test-ulca-key-never-real")
    # BHASHINI_PIPELINE_ID intentionally left unset
    calls = {"post": 0}
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_not_configured"
    assert calls["post"] == 0


def test_placeholder_values_count_as_not_configured(monkeypatch):
    monkeypatch.setenv("BHASHINI_ULCA_USER_ID", "your_key_here")
    monkeypatch.setenv("BHASHINI_ULCA_API_KEY", "placeholder")
    monkeypatch.setenv("BHASHINI_PIPELINE_ID", "changeme")

    assert bh.bhashini_configured() is False


def test_empty_source_text_falls_back_without_network_call(monkeypatch):
    _configure(monkeypatch)
    calls = {"post": 0}
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = bh.translate_to_hindi("")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "empty_source_text"
    assert calls["post"] == 0


def test_whitespace_only_source_text_falls_back_without_network_call(monkeypatch):
    _configure(monkeypatch)
    calls = {"post": 0}
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = bh.translate_to_hindi("   ")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "empty_source_text"
    assert calls["post"] == 0


# ---------------------------------------------------------------------
# Configured + success -- mocked HTTP only, both pipeline hops
# ---------------------------------------------------------------------

def test_configured_success_translates_and_returns_hindi(monkeypatch):
    _configure(monkeypatch)
    fake_post, calls = _make_two_call_router(
        _FakeResponse(200, _GOOD_CONFIG_PAYLOAD),
        _FakeResponse(200, _good_compute_payload("भारी ट्रैफिक आगे है।")),
    )
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result == {"status": bh.STATUS_TRANSLATED, "text": "भारी ट्रैफिक आगे है।", "error": None}
    assert calls["count"] == 2
    assert calls["urls"][0] == bh._DEFAULT_PIPELINE_CONFIG_URL
    assert calls["urls"][1] == _GOOD_CONFIG_PAYLOAD["pipelineInferenceAPIEndPoint"]["callbackUrl"]


def test_configured_success_sends_expected_request_shapes(monkeypatch):
    _configure(monkeypatch, timeout=15)
    captured = {"config": None, "compute": None}

    def fake_post(url, headers=None, json=None, timeout=None):
        if captured["config"] is None:
            captured["config"] = {"url": url, "headers": headers, "json": json, "timeout": timeout}
            return _FakeResponse(200, _GOOD_CONFIG_PAYLOAD)
        captured["compute"] = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        return _FakeResponse(200, _good_compute_payload())

    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_TRANSLATED
    assert captured["config"]["headers"]["userID"] == "test-user-never-real"
    assert captured["config"]["headers"]["ulcaApiKey"] == "test-ulca-key-never-real"
    assert captured["config"]["json"]["pipelineRequestConfig"]["pipelineId"] == "test-pipeline-id"
    assert captured["config"]["json"]["pipelineTasks"][0]["config"]["language"] == {"sourceLanguage": "en", "targetLanguage": "hi"}
    assert captured["config"]["timeout"] == 15.0

    assert captured["compute"]["url"] == _GOOD_CONFIG_PAYLOAD["pipelineInferenceAPIEndPoint"]["callbackUrl"]
    assert captured["compute"]["headers"]["Authorization"] == "test-inference-key-never-real"
    assert captured["compute"]["json"]["pipelineTasks"][0]["config"]["serviceId"] == "test-service-id"
    assert captured["compute"]["json"]["inputData"]["input"][0]["source"] == "Heavy traffic ahead."
    assert captured["compute"]["timeout"] == 15.0


def test_custom_pipeline_config_url_is_honored(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("BHASHINI_PIPELINE_CONFIG_URL", "https://example-custom-bhashini-gateway.test/config")
    fake_post, calls = _make_two_call_router(
        _FakeResponse(200, _GOOD_CONFIG_PAYLOAD),
        _FakeResponse(200, _good_compute_payload()),
    )
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_TRANSLATED
    assert calls["urls"][0] == "https://example-custom-bhashini-gateway.test/config"


# ---------------------------------------------------------------------
# Pipeline Config (step 1) failures -- all must fall back to English
# ---------------------------------------------------------------------

def test_config_call_timeout_falls_back(monkeypatch):
    _configure(monkeypatch)

    def raise_timeout(*a, **k):
        raise bh.requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(bh.requests, "post", raise_timeout)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result == {"status": bh.STATUS_FALLBACK, "text": "Heavy traffic ahead.", "error": "bhashini_config_timeout"}


def test_config_call_connection_error_falls_back(monkeypatch):
    _configure(monkeypatch)

    def raise_conn_error(*a, **k):
        raise bh.requests.exceptions.ConnectionError("simulated connection error")

    monkeypatch.setattr(bh.requests, "post", raise_conn_error)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_config_request_error:ConnectionError"
    assert result["text"] == "Heavy traffic ahead."


def test_config_call_http_error_falls_back(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: _FakeResponse(500, {}))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_config_http_500"


def test_config_call_auth_error_falls_back(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: _FakeResponse(401, {}))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_config_http_401"


def test_config_call_malformed_json_falls_back(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: _FakeResponse(200, raise_on_json=True))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_config_response_unparseable"


def test_config_call_missing_fields_falls_back(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: _FakeResponse(200, {"unexpected": "shape"}))

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_config_response_missing_fields"


# ---------------------------------------------------------------------
# Pipeline Compute (step 2) failures -- all must fall back to English
# ---------------------------------------------------------------------

def test_compute_call_timeout_falls_back(monkeypatch):
    _configure(monkeypatch)

    def flaky_post(url, headers=None, json=None, timeout=None):
        if url == bh._DEFAULT_PIPELINE_CONFIG_URL:
            return _FakeResponse(200, _GOOD_CONFIG_PAYLOAD)
        raise bh.requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(bh.requests, "post", flaky_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_compute_timeout"
    assert result["text"] == "Heavy traffic ahead."


def test_compute_call_connection_error_falls_back(monkeypatch):
    _configure(monkeypatch)

    def flaky_post(url, headers=None, json=None, timeout=None):
        if url == bh._DEFAULT_PIPELINE_CONFIG_URL:
            return _FakeResponse(200, _GOOD_CONFIG_PAYLOAD)
        raise bh.requests.exceptions.ConnectionError("simulated connection error")

    monkeypatch.setattr(bh.requests, "post", flaky_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_compute_request_error:ConnectionError"


def test_compute_call_http_error_falls_back(monkeypatch):
    _configure(monkeypatch)
    fake_post, _ = _make_two_call_router(_FakeResponse(200, _GOOD_CONFIG_PAYLOAD), _FakeResponse(503, {}))
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_compute_http_503"


def test_compute_call_malformed_json_falls_back(monkeypatch):
    _configure(monkeypatch)
    fake_post, _ = _make_two_call_router(
        _FakeResponse(200, _GOOD_CONFIG_PAYLOAD), _FakeResponse(200, raise_on_json=True),
    )
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_compute_response_unparseable"


def test_compute_call_missing_fields_falls_back(monkeypatch):
    _configure(monkeypatch)
    fake_post, _ = _make_two_call_router(
        _FakeResponse(200, _GOOD_CONFIG_PAYLOAD), _FakeResponse(200, {"unexpected": "shape"}),
    )
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_compute_response_missing_fields"


def test_compute_call_empty_translation_falls_back(monkeypatch):
    _configure(monkeypatch)
    fake_post, _ = _make_two_call_router(
        _FakeResponse(200, _GOOD_CONFIG_PAYLOAD), _FakeResponse(200, _good_compute_payload("")),
    )
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "bhashini_empty_translation"
    assert result["text"] == "Heavy traffic ahead."


def test_unexpected_exception_never_propagates(monkeypatch):
    _configure(monkeypatch)

    def raise_weird(*a, **k):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(bh.requests, "post", raise_weird)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    assert result["status"] == bh.STATUS_FALLBACK
    assert result["error"] == "unexpected_error:RuntimeError"
    assert result["text"] == "Heavy traffic ahead."


# ---------------------------------------------------------------------
# bhashini_configured() helper
# ---------------------------------------------------------------------

def test_bhashini_configured_true_only_when_all_three_set(monkeypatch):
    assert bh.bhashini_configured() is False
    _configure(monkeypatch)
    assert bh.bhashini_configured() is True


def test_bhashini_configured_false_when_any_one_missing(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("BHASHINI_PIPELINE_ID", raising=False)
    assert bh.bhashini_configured() is False


# ---------------------------------------------------------------------
# Credential-leak guard
# ---------------------------------------------------------------------

def test_credentials_never_appear_in_returned_dict(monkeypatch):
    _configure(monkeypatch)
    fake_post, _ = _make_two_call_router(_FakeResponse(500, {}), _FakeResponse(500, {}))
    monkeypatch.setattr(bh.requests, "post", fake_post)

    result = bh.translate_to_hindi("Heavy traffic ahead.")

    as_text = repr(result)
    assert "test-ulca-key-never-real" not in as_text
    assert "test-inference-key-never-real" not in as_text


def test_credentials_never_appear_in_printed_output(monkeypatch, capsys):
    _configure(monkeypatch)
    monkeypatch.setattr(bh.requests, "post", lambda *a, **k: _FakeResponse(500, {}))

    bh.translate_to_hindi("Heavy traffic ahead.")

    printed = capsys.readouterr().out
    assert "test-ulca-key-never-real" not in printed
    assert "test-user-never-real" not in printed
