"""
Stage 3B tests for citizen_sms_provider.py.

Hard rule for this entire file: NOTHING here may ever reach the real
network. Every test either stays in CITIZEN_ALERTS_DEV_MODE (which the
module itself guarantees makes zero network calls), or monkeypatches
`requests.post` to a fake before exercising the "production mode"
branches. The autouse `block_real_sockets` fixture below is an extra,
independent safety net: it patches socket.create_connection to raise
immediately, so even a bug that bypassed the `requests.post` patch could
not actually open a TCP connection to Exotel or anywhere else.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import citizen_sms_provider as sms


@pytest.fixture(autouse=True)
def block_real_sockets(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError(
            "A test attempted a real network connection. This must never "
            "happen in the Stage 3B SMS provider test suite."
        )
    monkeypatch.setattr("socket.create_connection", _blocked)
    yield


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts from a clean slate for every env var this module
    reads, regardless of what the real shell/CI environment has set."""
    for name in (
        "CITIZEN_ALERTS_DEV_MODE",
        "EXOTEL_ACCOUNT_SID",
        "EXOTEL_API_KEY",
        "EXOTEL_API_TOKEN",
        "EXOTEL_SENDER_ID",
        "EXOTEL_SUBDOMAIN",
        "CITIZEN_ALERTS_SMS_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _configure_production(monkeypatch, timeout=None):
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "false")
    monkeypatch.setenv("EXOTEL_ACCOUNT_SID", "SID12345")
    monkeypatch.setenv("EXOTEL_API_KEY", "test-key-never-real")
    monkeypatch.setenv("EXOTEL_API_TOKEN", "test-token-never-real")
    monkeypatch.setenv("EXOTEL_SENDER_ID", "BLRALERT")
    if timeout is not None:
        monkeypatch.setenv("CITIZEN_ALERTS_SMS_TIMEOUT_SECONDS", str(timeout))


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, raise_on_json=False):
        self.status_code = status_code
        self._json_data = json_data or {}
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json:
            raise ValueError("not json")
        return self._json_data


# ---------------------------------------------------------------------
# DEV_MODE (default) -- must never touch the network
# ---------------------------------------------------------------------

def test_dev_mode_default_when_unset_is_simulated(monkeypatch):
    calls = {"post": 0}
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = sms.send_sms("+919876543210", "Test alert text", "en")

    assert result == {"status": sms.STATUS_SIMULATED, "provider_message_id": None, "error": None}
    assert calls["post"] == 0, "DEV_MODE must never call requests.post"


def test_dev_mode_explicit_true_is_simulated(monkeypatch):
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "true")
    calls = {"post": 0}
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = sms.send_sms("+919876543210", "Test alert text", "kn")

    assert result["status"] == sms.STATUS_SIMULATED
    assert calls["post"] == 0


def test_dev_mode_even_with_full_exotel_config_present(monkeypatch):
    """DEV_MODE must win even if Exotel credentials happen to be set --
    the toggle is the single source of truth, not "are credentials
    present"."""
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "true")
    _configure_production(monkeypatch)
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "true")  # override back to true after helper sets false
    calls = {"post": 0}
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = sms.send_sms("+919876543210", "Test alert text", "en")

    assert result["status"] == sms.STATUS_SIMULATED
    assert calls["post"] == 0


# ---------------------------------------------------------------------
# Production mode, not configured -- must fail safely, never simulate
# ---------------------------------------------------------------------

def test_production_mode_unconfigured_fails_closed(monkeypatch):
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "false")
    calls = {"post": 0}
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = sms.send_sms("+919876543210", "Test alert text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "sms_provider_not_configured"
    assert result["provider_message_id"] is None
    assert calls["post"] == 0, "must never attempt a network call when not configured"


def test_production_mode_partially_configured_fails_closed(monkeypatch):
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "false")
    monkeypatch.setenv("EXOTEL_ACCOUNT_SID", "SID12345")
    monkeypatch.setenv("EXOTEL_API_KEY", "test-key-never-real")
    # EXOTEL_API_TOKEN and EXOTEL_SENDER_ID intentionally left unset
    calls = {"post": 0}
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: calls.__setitem__("post", calls["post"] + 1))

    result = sms.send_sms("+919876543210", "Test alert text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "sms_provider_not_configured"
    assert calls["post"] == 0


def test_placeholder_values_count_as_not_configured(monkeypatch):
    """.env.example ships with blank values; a value accidentally left as
    an obvious placeholder should not be treated as real configuration."""
    monkeypatch.setenv("CITIZEN_ALERTS_DEV_MODE", "false")
    monkeypatch.setenv("EXOTEL_ACCOUNT_SID", "your_key_here")
    monkeypatch.setenv("EXOTEL_API_KEY", "placeholder")
    monkeypatch.setenv("EXOTEL_API_TOKEN", "changeme")
    monkeypatch.setenv("EXOTEL_SENDER_ID", "")

    assert sms.sms_provider_configured() is False


# ---------------------------------------------------------------------
# Production mode, configured -- mocked HTTP only, never real
# ---------------------------------------------------------------------

def test_production_mode_success_captures_message_id(monkeypatch):
    _configure_production(monkeypatch)
    captured = {}

    def fake_post(url, auth=None, data=None, timeout=None):
        captured["url"] = url
        captured["auth"] = auth
        captured["data"] = data
        captured["timeout"] = timeout
        return _FakeResponse(200, {"SMSMessage": {"Sid": "SMSabc123", "Status": "sent"}})

    monkeypatch.setattr(sms.requests, "post", fake_post)

    result = sms.send_sms("+919876543210", "Real alert body", "en")

    assert result == {"status": sms.STATUS_SENT, "provider_message_id": "SMSabc123", "error": None}
    assert captured["url"] == "https://api.exotel.com/v1/Accounts/SID12345/Sms/send"
    assert captured["auth"] == ("test-key-never-real", "test-token-never-real")
    assert captured["data"]["To"] == "+919876543210"
    assert captured["data"]["Body"] == "Real alert body"
    assert captured["data"]["From"] == "BLRALERT"
    assert captured["timeout"] == 10.0


def test_production_mode_honors_custom_subdomain_and_timeout(monkeypatch):
    _configure_production(monkeypatch, timeout=25)
    monkeypatch.setenv("EXOTEL_SUBDOMAIN", "api.in1.exotel.com")
    captured = {}

    def fake_post(url, auth=None, data=None, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse(200, {"SMSMessage": {"Sid": "SMSxyz", "Status": "queued"}})

    monkeypatch.setattr(sms.requests, "post", fake_post)

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_SENT
    assert captured["url"] == "https://api.in1.exotel.com/v1/Accounts/SID12345/Sms/send"
    assert captured["timeout"] == 25.0


def test_production_mode_provider_reports_failed_status(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.setattr(
        sms.requests, "post",
        lambda *a, **k: _FakeResponse(200, {"SMSMessage": {"Sid": "SMSfail1", "Status": "failed"}}),
    )

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["provider_message_id"] == "SMSfail1"
    assert result["error"] == "provider_status_failed"


def test_production_mode_http_error_status(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: _FakeResponse(500, {}))

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "provider_http_500"
    assert result["provider_message_id"] is None


def test_production_mode_http_auth_error_status(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: _FakeResponse(401, {}))

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "provider_http_401"


def test_production_mode_malformed_json_response(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: _FakeResponse(200, raise_on_json=True))

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "provider_response_unparseable"


def test_production_mode_timeout_is_handled(monkeypatch):
    _configure_production(monkeypatch)

    def raise_timeout(*a, **k):
        raise sms.requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(sms.requests, "post", raise_timeout)

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "provider_timeout"


def test_production_mode_connection_error_is_handled(monkeypatch):
    _configure_production(monkeypatch)

    def raise_conn_error(*a, **k):
        raise sms.requests.exceptions.ConnectionError("simulated connection error")

    monkeypatch.setattr(sms.requests, "post", raise_conn_error)

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "provider_request_error:ConnectionError"


def test_production_mode_unexpected_exception_never_propagates(monkeypatch):
    """Even a completely unanticipated exception inside the send path
    must come back as a FAILED dict, never raise into the caller."""
    _configure_production(monkeypatch)

    def raise_weird(*a, **k):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(sms.requests, "post", raise_weird)

    result = sms.send_sms("+919876543210", "Text", "en")

    assert result["status"] == sms.STATUS_FAILED
    assert result["error"] == "unexpected_error:RuntimeError"


# ---------------------------------------------------------------------
# sms_provider_configured() helper
# ---------------------------------------------------------------------

def test_sms_provider_configured_true_only_when_all_four_set(monkeypatch):
    assert sms.sms_provider_configured() is False
    _configure_production(monkeypatch)
    assert sms.sms_provider_configured() is True


def test_sms_provider_configured_false_when_any_one_missing(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.delenv("EXOTEL_SENDER_ID", raising=False)
    assert sms.sms_provider_configured() is False


# ---------------------------------------------------------------------
# Credential-leak guard
# ---------------------------------------------------------------------

def test_credentials_never_appear_in_returned_dict(monkeypatch):
    _configure_production(monkeypatch)
    monkeypatch.setattr(sms.requests, "post", lambda *a, **k: _FakeResponse(500, {}))

    result = sms.send_sms("+919876543210", "Text", "en")

    as_text = repr(result)
    assert "test-key-never-real" not in as_text
    assert "test-token-never-real" not in as_text
