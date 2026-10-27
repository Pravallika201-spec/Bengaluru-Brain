"""
Tests for citizen_registry.py + citizen_otp.py (Stage 1: citizen
registration and alert preferences) and the /api/citizens/* endpoints
that wrap them in app.py.

These are entirely new, self-contained modules — nothing here imports or
exercises traffic_incident_service.py, traffic_alert_eligibility.py,
integration/usi_engine.py, integration/alerts.py, ward_stress.py, or any
ML/prediction code. No real SMS is sent by these tests — OTP codes are
read back directly from the dev-mode response/DB, exactly as a developer
would during manual testing, never assumed to have been delivered anywhere.

FINAL FEATURE ADDENDUM: the HTTP tests at the bottom of this file also
exercise the new /api/citizens/{id}/location endpoints, which read/write
ONLY through user_location_service.py's existing, untouched, ephemeral
in-memory store (the same one /api/traffic/location already used) -- no
new persistence, and this file still never touches traffic_incident_
service.py/traffic_alert_eligibility.py/USI/ML code.

Uses a throwaway SQLite file (not data/citizen_alerts.sqlite, the real
one used by the running app) so running the suite never touches real
citizen data.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import citizen_registry as cr
import citizen_otp as otp
import user_location_service as uls


def _import_backend_app_module():
    """Loads traffic_module/backend/app.py by its exact file path,
    under a dedicated module name, rather than a bare `import app`.

    Root cause of the failure this works around: this repository has
    THREE files literally named app.py (this one, friend_waste/app.py,
    and waste_module/app.py -- the latter two are empty placeholder
    files). A bare `import app` resolves to whichever "app" ends up
    first in sys.path / sys.modules, which depends on import order,
    PYTHONPATH, and how pytest was invoked -- on at least one real run
    it resolved to one of the empty stub files instead of this backend's
    real FastAPI app, producing "module 'app' has no attribute 'app'"
    even though this file's own `app = FastAPI()` is correct and
    untouched. Loading by explicit path sidesteps the name collision
    entirely instead of trying to control sys.path ordering."""
    import importlib.util

    app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
    spec = importlib.util.spec_from_file_location("citizen_registry_tests_backend_app", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_function(_):
    # Point both modules at a fresh temp DB file per test so tests never
    # interact with each other or with the real data/citizen_alerts.sqlite.
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.remove(path)  # sqlite3 creates it fresh on first connect
    cr.DB_PATH = path
    cr._schema_ready = False
    uls._locations.clear()


def teardown_function(_):
    try:
        os.remove(cr.DB_PATH)
    except OSError:
        pass
    uls._locations.clear()


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def test_validate_mobile_number_accepts_plus91_and_bare_forms():
    assert cr.validate_mobile_number("+91 98765 43210") == "+919876543210"
    assert cr.validate_mobile_number("9876543210") == "+919876543210"
    assert cr.validate_mobile_number("919876543210") == "+919876543210"


def test_validate_mobile_number_rejects_bad_input():
    for bad in ["12345", "5876543210", "", None, "abcdefghij"]:
        try:
            cr.validate_mobile_number(bad)
            assert False, f"should have rejected {bad!r}"
        except ValueError:
            pass


def test_normalize_language_accepts_names_and_codes_case_insensitively():
    assert cr.normalize_language("English") == "en"
    assert cr.normalize_language("kannada") == "kn"
    assert cr.normalize_language("HINDI") == "hi"
    assert cr.normalize_language("kn") == "kn"


def test_normalize_language_rejects_unsupported():
    try:
        cr.normalize_language("Tamil")
        assert False, "should have rejected an unsupported language"
    except ValueError:
        pass


def test_resolve_ward_none_and_empty_mean_no_ward():
    assert cr.resolve_ward(None) == (None, None)
    assert cr.resolve_ward("") == (None, None)


def test_resolve_ward_rejects_fabricated_ward_id():
    try:
        cr.resolve_ward("not-a-real-ward-id-999999")
        assert False, "should have rejected a fake ward id"
    except ValueError:
        pass


def test_resolve_ward_accepts_a_real_registry_ward():
    import ward_registry_service
    all_wards = ward_registry_service.get_all_wards()
    if not all_wards.get("available") or not all_wards.get("wards"):
        return  # registry not built on this machine — nothing to assert
    first = all_wards["wards"][0]
    ward_id, ward_name = cr.resolve_ward(str(first["ward_id"]))
    assert ward_id == str(first["ward_id"])
    assert ward_name == first["ward_name"]


# ---------------------------------------------------------------------
# Storage: create / get / update / delete
# ---------------------------------------------------------------------

def test_create_and_get_citizen_round_trip():
    citizen = cr.create_citizen(
        mobile_number="+919876500001",
        preferred_language="en",
        traffic_alerts_enabled=True,
        waste_alerts_enabled=False,
        location_consent=True,
        ward_id=None,
        ward_name=None,
    )
    assert citizen["status"] == "pending_verification"
    assert citizen["mobile_verified"] is False
    assert citizen["traffic_alerts_enabled"] is True
    assert citizen["waste_alerts_enabled"] is False
    assert citizen["location_consent"] is True

    fetched = cr.get_citizen(citizen["id"])
    assert fetched == citizen

    by_mobile = cr.get_citizen_by_mobile("+919876500001")
    assert by_mobile["id"] == citizen["id"]


def test_duplicate_mobile_number_is_rejected_not_overwritten():
    first = cr.create_citizen("+919876500002", "en", False, False, False, None, None)
    try:
        cr.create_citizen("+919876500002", "kn", True, True, True, None, None)
        assert False, "should have raised MobileAlreadyRegistered"
    except cr.MobileAlreadyRegistered as e:
        assert e.existing["id"] == first["id"]
    # original record must be untouched
    assert cr.get_citizen(first["id"])["preferred_language"] == "en"


def test_update_citizen_partial_update_preserves_other_fields():
    citizen = cr.create_citizen("+919876500003", "en", True, False, False, None, None)
    updated = cr.update_citizen(citizen["id"], waste_alerts_enabled=True)
    assert updated["waste_alerts_enabled"] is True
    assert updated["traffic_alerts_enabled"] is True  # untouched
    assert updated["updated_at"] >= citizen["updated_at"]


def test_update_citizen_rejects_forbidden_column():
    citizen = cr.create_citizen("+919876500004", "en", False, False, False, None, None)
    try:
        cr.update_citizen(citizen["id"], mobile_number="+911111111111")
        assert False, "mobile_number must not be updatable via generic update"
    except ValueError:
        pass


def test_delete_citizen_removes_row_and_frees_mobile_number():
    citizen = cr.create_citizen("+919876500005", "en", False, False, False, None, None)
    assert cr.delete_citizen(citizen["id"]) is True
    assert cr.get_citizen(citizen["id"]) is None
    assert cr.get_citizen_by_mobile("+919876500005") is None
    # freed for re-registration
    again = cr.create_citizen("+919876500005", "en", False, False, False, None, None)
    assert again["id"] != citizen["id"]


def test_persistence_across_reconnect_simulated_restart():
    citizen = cr.create_citizen("+919876500006", "en", True, True, False, None, None)
    citizen_id = citizen["id"]
    # Force a brand-new connection (module-level cached schema flag reset)
    # the way a real process restart would.
    cr._schema_ready = False
    reloaded = cr.get_citizen(citizen_id)
    assert reloaded is not None
    assert reloaded["mobile_number"] == "+919876500006"
    assert reloaded["traffic_alerts_enabled"] is True


# ---------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------

def test_otp_full_verification_flow():
    citizen = cr.create_citizen("+919876500007", "en", False, False, False, None, None)
    result = otp.generate_otp(citizen["id"], citizen["mobile_number"], purpose="registration")
    assert len(result["code"]) == 6 and result["code"].isdigit()

    ok, _ = otp.verify_otp(citizen["id"], citizen["mobile_number"], "000000", purpose="registration")
    assert ok is False, "a wrong code must never verify"

    ok, reason = otp.verify_otp(citizen["id"], citizen["mobile_number"], result["code"], purpose="registration")
    assert ok is True, reason

    ok, _ = otp.verify_otp(citizen["id"], citizen["mobile_number"], result["code"], purpose="registration")
    assert ok is False, "a consumed code must not be reusable"


def test_otp_never_claims_to_be_sent():
    assert "sent" not in otp.DEV_NOTICE.lower() or "not sent" in otp.DEV_NOTICE.lower()
    assert "NOT sent" in otp.DEV_NOTICE or "not sent" in otp.DEV_NOTICE.lower()


# ---------------------------------------------------------------------
# HTTP layer (requires the full app — heavier import, same pattern as
# test_enhanced_prediction.py / test_live_unexpected_traffic.py in this
# same tests/ directory).
# ---------------------------------------------------------------------

def test_http_register_verify_patch_delete_round_trip():
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()

    client = TestClient(app_module.app)
    mobile = "+919876500099"

    existing = cr.get_citizen_by_mobile(mobile)
    if existing:
        cr.delete_citizen(existing["id"])

    r = client.post("/api/citizens/register", json={
        "mobile_number": mobile,
        "preferred_language": "Kannada",
        "traffic_alerts_enabled": True,
        "waste_alerts_enabled": False,
        "location_consent": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citizen"]["status"] == "pending_verification"
    assert body["dev_mode"] is True
    dev_otp = body["dev_otp"]
    citizen_id = body["citizen"]["id"]

    # duplicate registration -> 409
    r2 = client.post("/api/citizens/register", json={"mobile_number": mobile})
    assert r2.status_code == 409

    # wrong OTP -> 400
    r3 = client.post("/api/citizens/verify-otp", json={"mobile_number": mobile, "otp_code": "000000"})
    assert r3.status_code == 400

    # correct OTP -> verified + active
    r4 = client.post("/api/citizens/verify-otp", json={"mobile_number": mobile, "otp_code": dev_otp})
    assert r4.status_code == 200, r4.text
    assert r4.json()["citizen"]["status"] == "active"

    # GET
    r5 = client.get(f"/api/citizens/{citizen_id}")
    assert r5.status_code == 200
    assert r5.json()["mobile_verified"] is True

    # PATCH preferences
    r6 = client.patch(f"/api/citizens/{citizen_id}", json={"waste_alerts_enabled": True})
    assert r6.status_code == 200
    assert r6.json()["waste_alerts_enabled"] is True

    # PATCH deactivate
    r7 = client.patch(f"/api/citizens/{citizen_id}", json={"status": "inactive"})
    assert r7.status_code == 200
    assert r7.json()["status"] == "inactive"

    # DELETE
    r8 = client.delete(f"/api/citizens/{citizen_id}")
    assert r8.status_code == 200
    assert r8.json()["deleted"] is True

    r9 = client.get(f"/api/citizens/{citizen_id}")
    assert r9.status_code == 404


def test_http_existing_endpoints_still_respond():
    """Sanity check only — confirms adding the citizen routes did not
    break FastAPI's route registration for pre-existing endpoints. Not a
    re-test of their internal logic (out of scope / already covered by
    this project's other test files)."""
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()

    client = TestClient(app_module.app)
    assert client.get("/api/ward-stress").status_code == 200
    assert client.get("/api/alerts/active").status_code == 200
    assert client.get("/api/health").status_code == 200


# ---------------------------------------------------------------------
# FINAL FEATURE: /api/citizens/{id}/location (browser geolocation,
# supplements ward-based matching in citizen_alert_dispatch.py). Reuses
# the EXISTING, untouched user_location_service.py ephemeral store --
# no new persistence to test here, just the thin HTTP wiring: consent/
# status gating, and that a stored coordinate is actually reachable via
# citizen_alert_dispatch.citizen_location_session_id()'s own convention.
# ---------------------------------------------------------------------

def _register_and_activate_citizen(client, mobile, location_consent=True):
    r = client.post("/api/citizens/register", json={
        "mobile_number": mobile,
        "preferred_language": "English",
        "traffic_alerts_enabled": True,
        "waste_alerts_enabled": False,
        "location_consent": location_consent,
    })
    assert r.status_code == 200, r.text
    citizen_id = r.json()["citizen"]["id"]
    dev_otp = r.json()["dev_otp"]
    r2 = client.post("/api/citizens/verify-otp", json={"mobile_number": mobile, "otp_code": dev_otp})
    assert r2.status_code == 200, r2.text
    return citizen_id


def test_http_location_update_requires_consent():
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500111", location_consent=False)

    r = client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 12.97, "longitude": 77.59})
    assert r.status_code == 403


def test_http_location_update_requires_active_citizen():
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500112", location_consent=True)
    client.patch(f"/api/citizens/{citizen_id}", json={"status": "inactive"})

    r = client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 12.97, "longitude": 77.59})
    assert r.status_code == 403


def test_http_location_update_requires_known_citizen():
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    r = client.post("/api/citizens/999999/location", json={"latitude": 12.97, "longitude": 77.59})
    assert r.status_code == 404


def test_http_location_update_rejects_implausible_coordinates():
    from fastapi.testclient import TestClient
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500113", location_consent=True)

    r = client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 999.0, "longitude": 77.59})
    assert r.status_code == 400


def test_http_location_update_then_dispatch_can_read_it_back():
    """Proves the HTTP endpoint and citizen_alert_dispatch.py's own
    live-location reader agree on the same session-id convention --
    never two independent, silently-drifting implementations."""
    from fastapi.testclient import TestClient
    import citizen_alert_dispatch as cad
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500114", location_consent=True)

    r = client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 13.02, "longitude": 77.59})
    assert r.status_code == 200, r.text
    assert r.json()["tracking"] is True

    assert cad._live_location_for_citizen(citizen_id) == (13.02, 77.59)


def test_http_location_delete_stops_tracking():
    from fastapi.testclient import TestClient
    import citizen_alert_dispatch as cad
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500115", location_consent=True)
    client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 13.02, "longitude": 77.59})
    assert cad._live_location_for_citizen(citizen_id) is not None

    r = client.delete(f"/api/citizens/{citizen_id}/location")
    assert r.status_code == 200
    assert r.json()["removed"] is True
    assert cad._live_location_for_citizen(citizen_id) is None


def test_http_patch_consent_off_stops_tracking_automatically():
    """Turning location_consent off via the existing PATCH endpoint must
    proactively clear any stored live coordinate -- not just wait for
    the ephemeral store's own TTL -- per the "stop tracking when consent
    is disabled" requirement."""
    from fastapi.testclient import TestClient
    import citizen_alert_dispatch as cad
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500116", location_consent=True)
    client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 13.02, "longitude": 77.59})
    assert cad._live_location_for_citizen(citizen_id) is not None

    r = client.patch(f"/api/citizens/{citizen_id}", json={"location_consent": False})
    assert r.status_code == 200
    assert r.json()["location_consent"] is False

    assert cad._live_location_for_citizen(citizen_id) is None


def test_http_patch_status_inactive_stops_tracking_automatically():
    from fastapi.testclient import TestClient
    import citizen_alert_dispatch as cad
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500117", location_consent=True)
    client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 13.02, "longitude": 77.59})
    assert cad._live_location_for_citizen(citizen_id) is not None

    r = client.patch(f"/api/citizens/{citizen_id}", json={"status": "inactive"})
    assert r.status_code == 200

    assert cad._live_location_for_citizen(citizen_id) is None


def test_http_delete_citizen_also_clears_live_location():
    from fastapi.testclient import TestClient
    import citizen_alert_dispatch as cad
    app_module = _import_backend_app_module()
    client = TestClient(app_module.app)

    citizen_id = _register_and_activate_citizen(client, "+919876500118", location_consent=True)
    client.post(f"/api/citizens/{citizen_id}/location", json={"latitude": 13.02, "longitude": 77.59})
    assert cad._live_location_for_citizen(citizen_id) is not None

    r = client.delete(f"/api/citizens/{citizen_id}")
    assert r.status_code == 200

    assert cad._live_location_for_citizen(citizen_id) is None
