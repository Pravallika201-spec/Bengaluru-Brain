"""
Tests for citizen_alert_dispatch.py (Stage 2: connecting the Stage 1
citizen registry to the two EXISTING, already-firing alert sources).

Uses a throwaway SQLite file (never data/citizen_alerts.sqlite, the real
one the running app uses), exactly like tests/test_citizen_registry.py.

Two things are monkeypatched, deliberately, and disclosed here:

  1. traffic_alert_eligibility.get_active_traffic_incident_alerts() --
     patched to return one already-recorded-eligible incident on a REAL
     segment_id, with REAL coordinates pulled once (module-level, at
     import time of this test file) from the project's actual
     bengaluru_traffic_history.csv via the real analyze_all_segments().
     This tests dispatch_traffic_alerts()'s own matching/dedup/
     preference logic against real geography, without needing a live
     TRAFFIC_ANOMALY to actually be occurring in the collected data
     right now (get_active_traffic_incident_alerts() only ever returns
     what /api/traffic/incidents already recorded as eligible during a
     live run -- see that function's own docstring).

  2. usi_engine.compute_usi / alerts.classify_alert_type / alerts.
     generate_alert -- patched with values matching their REAL,
     documented return shapes (confirmed by reading those modules
     directly), for the tests that check dispatch's own wiring (ward
     resolution, independent traffic/waste preference gating, dual-
     subscriber dedup) in isolation from usi_engine's own math and
     alerts.py's own template rendering -- neither of which is part of
     what Stage 2 built, and neither may be modified.

     integration_bridge.get_active_alerts() is ALSO called for real
     (never mocked) in two dedicated tests that check its actual,
     currently-true availability state on whichever machine the suite
     runs on:
       - test_dispatch_usi_alerts_unavailable_integration_degrades_gracefully
         mocks ONLY get_active_alerts() itself, to deterministically
         force and verify the unavailable-integration path (a real state
         on a machine missing an optional dependency like torch).
       - test_dispatch_usi_alerts_real_environment_end_to_end_without_fabricating_data
         calls get_active_alerts() for real, unmocked, and branches on
         whatever it actually reports: if unavailable, asserts the same
         safe-empty behavior as the mocked test; if available (confirmed
         true on the real Windows dev environment, which reports real
         active USI areas), it resolves one of those REAL areas to a
         REAL ward and confirms genuine end-to-end delivery -- without
         asserting any invented area name, ward, or alert count.

Nothing here imports, modifies, or exercises traffic prediction/ML code,
waste_module, friend_waste, USI calculation code, or the existing
Traffic/Waste alert STATE-MUTATING functions (is_alert_eligible,
maybe_alert_and_send, check_and_update) -- only their existing read-only
accessors, via monkeypatching in the traffic case and the real call in
the USI availability case.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import citizen_registry as cr
import citizen_alert_dispatch as cad
import traffic_alert_eligibility as tae
import user_location_service as uls
from traffic_incident_service import (
    haversine_km, analyze_all_segments, load_recent_observations_from_csv,
)

_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bengaluru_traffic_history.csv")

# Resolved once, from the REAL collected data -- a real segment with real
# coordinates, not invented. If the underlying CSV/segment set ever
# changes on this machine such that this exact segment_id disappears,
# these tests will fail loudly (skipped) rather than silently pass on
# fabricated data.
_REAL_SEGMENT = None
if os.path.exists(_CSV_PATH):
    _by_segment = load_recent_observations_from_csv(_CSV_PATH)
    for _r in analyze_all_segments(_by_segment):
        if _r.get("segment_id") == "430043686_10219547463_0" and _r.get("latitude") is not None:
            _REAL_SEGMENT = _r
            break

# Real wards, from the real ward registry (see the Stage 2 audit /
# report for how these specific ids were confirmed):
#   R.T Nagar (19883245) -- centroid ~1.27km from the real segment above
#   Vignananagara (19883251) -- centroid ~10.2km from it (out of radius)
#   Hebbal (19883365) -- waste_area_name == 'Hebbal' (exact-name USI match)
#   Madiwala (19884562) -- waste_area_name == 'Madiwala' (the real
#     area_mapping.json spatial-nearest target for the traffic location
#     "Silk Board", confirmed 0.718km apart, match_type spatial_nearest)
WARD_RT_NAGAR = "19883245"
WARD_VIGNANANAGARA = "19883251"
WARD_HEBBAL = "19883365"
WARD_MADIWALA = "19884562"


def setup_function(_):
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.remove(path)
    cr.DB_PATH = path
    cr._schema_ready = False
    cad.reset_schema_cache()
    cad.reset_ward_index_cache()
    uls._locations.clear()


def teardown_function(_):
    try:
        os.remove(cr.DB_PATH)
    except OSError:
        pass
    uls._locations.clear()


def _make_citizen(mobile, ward_id, traffic=True, waste=True, location_consent=True,
                   language="English", verified=True, status="active"):
    c = cr.create_citizen(
        mobile_number=mobile,
        preferred_language=cr.normalize_language(language),  # "English"/"Hindi" -> 'en'/'hi', matching what the real /api/citizens/register endpoint does
        traffic_alerts_enabled=traffic,
        waste_alerts_enabled=waste,
        location_consent=location_consent,
        ward_id=ward_id,
        ward_name=None,
    )
    fields = {}
    if verified:
        fields["mobile_verified"] = True
    if status != "pending_verification":
        fields["status"] = status
    if fields:
        c = cr.update_citizen(c["id"], **fields)
    return c


# ---------------------------------------------------------------------
# resolve_ward_ids_for_usi_area -- real area_mapping.json + real ward registry
# ---------------------------------------------------------------------

def test_resolve_ward_ids_exact_name_match():
    # "Hebbal" resolves to the Hebbal ward itself (exact waste_area_name
    # match) AND legitimately also to Bhoopasandra ward, which lists
    # "Hebbal" as one of its own real traffic_named_locations (confirmed
    # against the real ward registry) -- both are real matches, not a bug;
    # resolve_ward_ids_for_usi_area intentionally returns list[str].
    ids = cad.resolve_ward_ids_for_usi_area("Hebbal")
    assert WARD_HEBBAL in ids


def test_resolve_ward_ids_via_area_mapping_spatial_join():
    # "Silk Board" (a traffic location) has no ward of its own name --
    # area_mapping.json real-joins it to the "Madiwala" waste area (0.718km
    # away, match_type spatial_nearest) -- confirmed present via that path.
    ids = cad.resolve_ward_ids_for_usi_area("Silk Board")
    assert WARD_MADIWALA in ids


def test_resolve_ward_ids_unknown_area_returns_empty_never_a_guess():
    assert cad.resolve_ward_ids_for_usi_area("Not A Real Bengaluru Area XYZ") == []


# ---------------------------------------------------------------------
# Hindi fallback
# ---------------------------------------------------------------------

def test_resolve_delivery_language_english_and_kannada_pass_through():
    assert cad._resolve_delivery_language("en") == ("en", None)
    assert cad._resolve_delivery_language("kn") == ("kn", None)


def test_resolve_delivery_language_hindi_is_now_deferred_to_bhashini_attempt():
    """Stage 3C: 'hi' no longer decides English-fallback immediately --
    it returns a provisional ("hi", None), deferring the real decision
    to _prepare_message_text() (called from _record_delivery(), which
    is where the canonical English text is actually available to
    translate). See test_prepare_message_text_* below for the actual
    translate-or-fallback behavior."""
    assert cad._resolve_delivery_language("hi") == ("hi", None)


def test_prepare_message_text_english_and_kannada_are_pure_passthrough():
    message = {"english": "Heavy traffic ahead.", "kannada": "ಟ್ರಾಫಿಕ್ ಎಚ್ಚರಿಕೆ."}
    assert cad._prepare_message_text(message, "en", None) == ("Heavy traffic ahead.", "en", None)
    assert cad._prepare_message_text(message, "kn", None) == ("ಟ್ರಾಫಿಕ್ ಎಚ್ಚರಿಕೆ.", "kn", None)


def test_prepare_message_text_hindi_uses_real_translation_when_available(monkeypatch):
    import bhashini_translator as bh
    monkeypatch.setattr(
        cad.bhashini_translator, "translate_to_hindi",
        lambda text: {"status": bh.STATUS_TRANSLATED, "text": "अनुवादित संदेश", "error": None},
    )
    message = {"english": "Heavy traffic ahead.", "kannada": "ಟ್ರಾಫಿಕ್ ಎಚ್ಚರಿಕೆ."}

    text, lang, fallback = cad._prepare_message_text(message, "hi", None)

    assert text == "अनुवादित संदेश"
    assert lang == "hi"
    assert fallback is None


def test_prepare_message_text_hindi_falls_back_with_named_reason_on_failure(monkeypatch):
    import bhashini_translator as bh
    monkeypatch.setattr(
        cad.bhashini_translator, "translate_to_hindi",
        lambda text: {"status": bh.STATUS_FALLBACK, "text": text, "error": "bhashini_not_configured"},
    )
    message = {"english": "Heavy traffic ahead.", "kannada": "ಟ್ರಾಫಿಕ್ ಎಚ್ಚರಿಕೆ."}

    text, lang, fallback = cad._prepare_message_text(message, "hi", None)

    assert text == "Heavy traffic ahead."
    assert lang == "en"
    assert fallback == "hi_bhashini_fallback_sent_en:bhashini_not_configured"


# ---------------------------------------------------------------------
# Traffic-incident dispatch -- real geography, monkeypatched eligibility feed
# ---------------------------------------------------------------------

def _patch_active_traffic_incidents(monkeypatch, last_alert_time="2026-09-29T12:00:00"):
    assert _REAL_SEGMENT is not None, "expected real segment 430043686_10219547463_0 in bengaluru_traffic_history.csv"
    fake_alert = {
        "segment_id": _REAL_SEGMENT["segment_id"],
        "road_name": _REAL_SEGMENT.get("road_name") or _REAL_SEGMENT["segment_id"],
        "type": "TRAFFIC_ANOMALY",
        "english": "Unexpected heavy traffic detected on CQAL Road. Please consider an alternate route.",
        "kannada": "CQAL Road ನಲ್ಲಿ ನಿರೀಕ್ಷೆಗಿಂತ ಹೆಚ್ಚು ಸಂಚಾರ ದಟ್ಟಣೆ ಪತ್ತೆಯಾಗಿದೆ.",
        "last_alert_time": last_alert_time,
    }
    monkeypatch.setattr(tae, "get_active_traffic_incident_alerts", lambda: [fake_alert])


def test_dispatch_traffic_alerts_matches_only_verified_active_consenting_in_range_citizen(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch)

    near_ok = _make_citizen("9000000001", WARD_RT_NAGAR)  # traffic=True, consent=True, verified, active -- should match
    far_away = _make_citizen("9000000002", WARD_VIGNANANAGARA)  # out of radius
    no_traffic_pref = _make_citizen("9000000003", WARD_RT_NAGAR, traffic=False)  # preference gate
    no_consent = _make_citizen("9000000004", WARD_RT_NAGAR, location_consent=False)  # consent gate
    unverified = _make_citizen("9000000005", WARD_RT_NAGAR, verified=False)  # verification gate
    inactive = _make_citizen("9000000006", WARD_RT_NAGAR, status="inactive")  # status gate

    result = cad.dispatch_traffic_alerts()

    assert result["incidents_checked"] == 1
    assert result["citizens_matched"] == 1
    assert result["citizens_notified"] == 1
    matched_ids = {d["citizen_id"] for d in result["details"]}
    assert matched_ids == {near_ok["id"]}
    for excluded in (far_away, no_traffic_pref, no_consent, unverified, inactive):
        assert excluded["id"] not in matched_ids

    deliveries = cad.get_deliveries_for_citizen(near_ok["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["alert_source"] == "traffic"
    assert deliveries[0]["alert_key"] == _REAL_SEGMENT["segment_id"]
    assert deliveries[0]["status"] == "SIMULATED_NOT_SENT"
    assert deliveries[0]["language_sent"] == "en"
    assert deliveries[0]["language_fallback"] is None

    # excluded citizens have no delivery rows at all
    for excluded in (far_away, no_traffic_pref, no_consent, unverified, inactive):
        assert cad.get_deliveries_for_citizen(excluded["id"]) == []


def test_dispatch_traffic_alerts_duplicate_run_same_instance_does_not_double_notify(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch, last_alert_time="2026-09-29T12:00:00")
    citizen = _make_citizen("9000000010", WARD_RT_NAGAR)

    first = cad.dispatch_traffic_alerts()
    assert first["citizens_notified"] == 1
    assert first["citizens_skipped_dedup"] == 0

    second = cad.dispatch_traffic_alerts()
    assert second["citizens_notified"] == 0
    assert second["citizens_skipped_dedup"] == 1

    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1  # still exactly one row, not two


def test_dispatch_traffic_alerts_new_instance_timestamp_notifies_again(monkeypatch):
    citizen = _make_citizen("9000000011", WARD_RT_NAGAR)

    _patch_active_traffic_incidents(monkeypatch, last_alert_time="2026-09-29T12:00:00")
    cad.dispatch_traffic_alerts()

    # A real escalation/re-detection would carry a NEW last_alert_time
    # (traffic_alert_eligibility._AlertRecord.last_alert_time updates on
    # severity increase / location change / cooldown expiry) -- dispatch
    # must treat that as a new instance, not the same one.
    _patch_active_traffic_incidents(monkeypatch, last_alert_time="2026-09-29T12:45:00")
    second = cad.dispatch_traffic_alerts()

    assert second["citizens_notified"] == 1
    assert len(cad.get_deliveries_for_citizen(citizen["id"])) == 2


def test_dispatch_traffic_alerts_no_incidents_is_a_safe_noop():
    result = cad.dispatch_traffic_alerts()
    assert result == {
        "incidents_checked": 0, "citizens_matched": 0,
        "citizens_notified": 0, "citizens_skipped_dedup": 0, "details": [],
    }


# ---------------------------------------------------------------------
# FINAL FEATURE: live browser geolocation supplementing (never
# replacing) ward-centroid matching.
# ---------------------------------------------------------------------

def test_citizen_location_session_id_format():
    assert cad.citizen_location_session_id(42) == "citizen:42"


def test_live_location_for_citizen_none_when_never_reported():
    citizen = _make_citizen("9000000020", WARD_RT_NAGAR)
    assert cad._live_location_for_citizen(citizen["id"]) is None


def test_live_location_for_citizen_returns_reported_coordinates():
    citizen = _make_citizen("9000000021", WARD_RT_NAGAR)
    uls.update_location(cad.citizen_location_session_id(citizen["id"]), 13.01, 77.59)
    assert cad._live_location_for_citizen(citizen["id"]) == (13.01, 77.59)


def test_live_location_for_citizen_none_when_stale():
    import datetime as dt
    citizen = _make_citizen("9000000022", WARD_RT_NAGAR)
    loc = uls.update_location(cad.citizen_location_session_id(citizen["id"]), 13.01, 77.59)
    # Simulate a report older than the ephemeral store's own TTL -- the
    # SAME object user_location_service._locations already holds a
    # reference to, so this does not bypass or duplicate its logic.
    loc.last_updated = dt.datetime.now() - dt.timedelta(seconds=uls.LOCATION_TTL_SECONDS + 10)
    assert cad._live_location_for_citizen(citizen["id"]) is None


def test_remove_live_location_for_citizen_clears_it():
    citizen = _make_citizen("9000000023", WARD_RT_NAGAR)
    uls.update_location(cad.citizen_location_session_id(citizen["id"]), 13.01, 77.59)
    assert cad._live_location_for_citizen(citizen["id"]) is not None

    cad.remove_live_location_for_citizen(citizen["id"])

    assert cad._live_location_for_citizen(citizen["id"]) is None


def test_dispatch_traffic_alerts_prefers_fresh_live_location_over_ward_centroid(monkeypatch):
    """Registered ward (Vignananagara) is ~10.2km from the real incident
    -- out of DEFAULT_MATCH_RADIUS_KM via the ward-centroid path alone.
    A fresh live coordinate placed exactly AT the incident's own real
    location must still bring this citizen into range -- proving
    dispatch actually prefers the live coordinate, not just that it
    tolerates one being present."""
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000024", WARD_VIGNANANAGARA)
    uls.update_location(
        cad.citizen_location_session_id(citizen["id"]),
        _REAL_SEGMENT["latitude"], _REAL_SEGMENT["longitude"],
    )

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_matched"] == 1
    assert result["citizens_notified"] == 1
    assert result["details"][0]["citizen_id"] == citizen["id"]
    assert result["details"][0]["location_source"] == "live_gps"
    assert result["details"][0]["distance_km"] == 0.0


def test_dispatch_traffic_alerts_live_location_out_of_range_overrides_in_range_ward(monkeypatch):
    """Registered ward (R.T Nagar) is ~1.27km from the real incident --
    IN range via the ward-centroid path alone. A fresh live coordinate
    far away must take priority and keep this citizen OUT of range --
    proving the live coordinate is actually consulted first, not merely
    used as a tie-breaker alongside the ward centroid."""
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000025", WARD_RT_NAGAR)
    far_lat = _REAL_SEGMENT["latitude"] + 0.5   # ~55km away -- well outside the 2km radius
    uls.update_location(cad.citizen_location_session_id(citizen["id"]), far_lat, _REAL_SEGMENT["longitude"])

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_matched"] == 0
    assert result["citizens_notified"] == 0
    assert cad.get_deliveries_for_citizen(citizen["id"]) == []


def test_dispatch_traffic_alerts_falls_back_to_ward_centroid_when_no_live_location(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000026", WARD_RT_NAGAR)

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_matched"] == 1
    assert result["details"][0]["location_source"] == "ward_centroid"


def test_dispatch_traffic_alerts_stale_live_location_falls_back_to_ward_centroid(monkeypatch):
    """A live coordinate that has gone stale (no refresh within the
    ephemeral store's TTL -- e.g. the browser tab was closed) must be
    treated exactly like no live coordinate at all, never used."""
    import datetime as dt
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000027", WARD_RT_NAGAR)
    far_lat = _REAL_SEGMENT["latitude"] + 0.5
    loc = uls.update_location(cad.citizen_location_session_id(citizen["id"]), far_lat, _REAL_SEGMENT["longitude"])
    loc.last_updated = dt.datetime.now() - dt.timedelta(seconds=uls.LOCATION_TTL_SECONDS + 10)

    result = cad.dispatch_traffic_alerts()

    # The stale far-away coordinate must be ignored -- falls back to the
    # ward centroid, which IS in range, so this citizen is still matched.
    assert result["citizens_matched"] == 1
    assert result["details"][0]["location_source"] == "ward_centroid"


def test_hindi_citizen_falls_back_to_english_when_bhashini_not_configured(monkeypatch):
    """Real, unmocked bhashini_translator.translate_to_hindi() call --
    BHASHINI_ULCA_USER_ID/BHASHINI_ULCA_API_KEY/BHASHINI_PIPELINE_ID are
    not set anywhere in this test suite's environment, so this
    genuinely exercises the "not configured" fallback branch end to
    end, the same way test_dispatch_usi_alerts_real_environment_end_to_end_
    without_fabricating_data exercises a real (not mocked) call elsewhere
    in this file."""
    monkeypatch.delenv("BHASHINI_ULCA_USER_ID", raising=False)
    monkeypatch.delenv("BHASHINI_ULCA_API_KEY", raising=False)
    monkeypatch.delenv("BHASHINI_PIPELINE_ID", raising=False)
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000012", WARD_RT_NAGAR, language="Hindi")

    cad.dispatch_traffic_alerts()

    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["language_sent"] == "en"
    assert deliveries[0]["language_fallback"] == "hi_bhashini_fallback_sent_en:bhashini_not_configured"


def test_hindi_citizen_gets_real_hindi_when_bhashini_configured_and_succeeds(monkeypatch):
    """Mocked BHASHINI HTTP calls (never real network) -- proves the
    dispatch layer actually uses a successful translation when one is
    available, with language_sent becoming 'hi' and no fallback note."""
    import bhashini_translator as bh

    def fake_translate(english_text):
        return {"status": bh.STATUS_TRANSLATED, "text": "हिंदी में परीक्षण संदेश", "error": None}

    monkeypatch.setattr(cad.bhashini_translator, "translate_to_hindi", fake_translate)
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000013", WARD_RT_NAGAR, language="Hindi")

    cad.dispatch_traffic_alerts()

    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["language_sent"] == "hi"
    assert deliveries[0]["language_fallback"] is None


def test_hindi_citizen_falls_back_with_named_reason_when_bhashini_call_fails(monkeypatch):
    """Mocked BHASHINI failure (never real network) -- proves the
    fallback tag names the specific reason bhashini_translator reported,
    distinct from the old Stage 2 'hi_not_yet_supported_sent_en' tag."""
    import bhashini_translator as bh

    def fake_translate(english_text):
        return {"status": bh.STATUS_FALLBACK, "text": english_text, "error": "bhashini_config_timeout"}

    monkeypatch.setattr(cad.bhashini_translator, "translate_to_hindi", fake_translate)
    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000014", WARD_RT_NAGAR, language="Hindi")

    cad.dispatch_traffic_alerts()

    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["language_sent"] == "en"
    assert deliveries[0]["language_fallback"] == "hi_bhashini_fallback_sent_en:bhashini_config_timeout"


def test_bhashini_never_called_for_english_or_kannada_citizens(monkeypatch):
    """Belt-and-suspenders: bhashini_translator.translate_to_hindi must
    only ever be invoked for a Hindi-preferring citizen -- never for
    English or Kannada, which this stage must leave completely
    unaffected."""
    calls = []
    monkeypatch.setattr(cad.bhashini_translator, "translate_to_hindi", lambda text: calls.append(text) or {"status": "TRANSLATED", "text": "x", "error": None})
    _patch_active_traffic_incidents(monkeypatch)
    _make_citizen("9000000015", WARD_RT_NAGAR, language="English")
    _make_citizen("9000000016", WARD_RT_NAGAR, language="Kannada")

    cad.dispatch_traffic_alerts()

    assert calls == []


# ---------------------------------------------------------------------
# USI dispatch -- real ward/area-mapping resolution + real
# integration_bridge.get_active_alerts() availability behavior;
# usi_engine/alerts internals stood in for (see module docstring above)
# ---------------------------------------------------------------------

def test_dispatch_usi_alerts_unavailable_integration_degrades_gracefully(monkeypatch):
    """Deterministic (mocked): forces integration_bridge.get_active_alerts()
    to report unavailable -- as it genuinely does on a machine missing an
    optional dependency (e.g. torch) -- and confirms dispatch_usi_alerts()
    degrades the same way integration_bridge itself does: a safe empty
    result, never a crash, never a fabricated alert, and zero delivery
    rows created. This is the state the original version of this test
    assumed was the ONLY state; it is now mocked explicitly so it stays
    true regardless of which real environment the suite runs in."""
    import integration_bridge
    monkeypatch.setattr(
        integration_bridge, "get_active_alerts",
        lambda: {"available": False, "reason": "No module named 'torch'", "alerts": []},
    )
    citizen = _make_citizen("9000000040", WARD_HEBBAL)  # both preferences on

    result = cad.dispatch_usi_alerts()

    assert result["areas_checked"] == 0
    assert result["citizens_matched"] == 0
    assert result["citizens_notified"] == 0
    assert result["unavailable_reason"] == "No module named 'torch'"
    assert cad.get_deliveries_for_citizen(citizen["id"]) == []


def test_dispatch_usi_alerts_real_environment_end_to_end_without_fabricating_data():
    """Calls the REAL, unmocked integration_bridge.get_active_alerts().

    On a machine without the USI pipeline's optional dependencies (this
    project's own sandboxed test shell has no torch installed), that
    real call itself reports unavailable, and this test asserts the same
    safe-empty behavior as the mocked test above -- proving the two
    paths agree instead of silently skipping the real call.

    On a machine where the real USI pipeline IS available (confirmed:
    the real Windows dev environment reports real active areas), this
    test does NOT assert any invented count, area name, or alert
    content -- it reads whatever the real system currently reports,
    tries to resolve one of those REAL active areas to a REAL ward via
    the real ward registry + real area_mapping.json (exactly the
    resolution dispatch_usi_alerts() itself uses), registers one real
    citizen in that real ward with both preferences on, and confirms
    dispatch actually delivers to them exactly once. If none of the
    currently-active real areas resolve to any ward in this project's
    own registry, that is reported as a real, unfabricated data gap
    rather than papered over with an assertion that would trivially
    pass either way."""
    import integration_bridge

    active = integration_bridge.get_active_alerts()  # REAL call, never mocked

    if not active.get("available"):
        result = cad.dispatch_usi_alerts()
        assert result["areas_checked"] == 0
        assert result["citizens_matched"] == 0
        assert result["citizens_notified"] == 0
        return

    assert isinstance(active["alerts"], list)
    if not active["alerts"]:
        # Available, genuinely zero areas currently in an alertable band
        # right now -- a real, honest outcome, nothing to match against.
        result = cad.dispatch_usi_alerts()
        assert result["citizens_matched"] == 0
        return

    resolved_area = None
    resolved_ward_ids = []
    for area in active["alerts"]:
        ids = cad.resolve_ward_ids_for_usi_area(area["area_name"])
        if ids:
            resolved_area = area["area_name"]
            resolved_ward_ids = ids
            break

    if resolved_area is None:
        # Every currently-active real area failed to resolve to any real
        # ward via this project's own registry/area_mapping.json -- a
        # genuine coverage gap in the real data, not a test to force-pass.
        result = cad.dispatch_usi_alerts()
        assert result["areas_checked"] == len(active["alerts"])
        return

    citizen = _make_citizen("9000000041", resolved_ward_ids[0], traffic=True, waste=True)

    result = cad.dispatch_usi_alerts()

    assert result["areas_checked"] >= 1
    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["alert_source"] == "usi"
    assert deliveries[0]["alert_key"] == resolved_area
    assert deliveries[0]["status"] == "SIMULATED_NOT_SENT"


def _install_fake_usi_modules(monkeypatch, alert_type, band="Yellow", area_name="Hebbal", last_alert_time="2026-09-29T12:00:00"):
    """Stands in for integration_bridge/usi_engine/alerts with values
    matching their REAL, documented return shapes (see those modules'
    own source, read directly during design). Exercises dispatch_usi_
    alerts()'s own ward-resolution/preference/dedup logic for real."""
    import types
    import integration_bridge

    fake_active = {
        "available": True,
        "alerts": [{"area_name": area_name, "usi": 65.0, "band": band, "last_alert_time": last_alert_time, "reason": "test"}],
        "count": 1,
    }
    monkeypatch.setattr(integration_bridge, "get_active_alerts", lambda: fake_active)

    fake_usi_result = {
        "area_name": area_name, "band": band, "usi": 65.0,
        "reason": "Test reason", "compounding_bonus_applied": False,
        "traffic": {"score": 70.0, "level": "HIGH", "source": "REAL"},
        "waste": {"score": 70.0, "level": "HIGH", "source": "REAL"},
    }
    fake_usi_engine = types.SimpleNamespace(compute_usi=lambda area: fake_usi_result)
    fake_alerts_module = types.SimpleNamespace(
        classify_alert_type=lambda r: alert_type,
        generate_alert=lambda r: {
            "area": area_name, "band": band, "english": f"Test alert for {area_name}",
            "kannada": f"ಪರೀಕ್ಷೆ {area_name}", "alert_type": alert_type,
        },
    )
    monkeypatch.setitem(sys.modules, "usi_engine", fake_usi_engine)
    monkeypatch.setitem(sys.modules, "alerts", fake_alerts_module)


def test_dispatch_usi_alerts_waste_only_reaches_only_waste_subscribers(monkeypatch):
    _install_fake_usi_modules(monkeypatch, alert_type="WASTE_ONLY")
    traffic_citizen = _make_citizen("9000000020", WARD_HEBBAL, traffic=True, waste=False)
    waste_citizen = _make_citizen("9000000021", WARD_HEBBAL, traffic=False, waste=True)

    result = cad.dispatch_usi_alerts()

    assert result["citizens_notified"] == 1
    assert cad.get_deliveries_for_citizen(waste_citizen["id"]) != []
    assert cad.get_deliveries_for_citizen(traffic_citizen["id"]) == []


def test_dispatch_usi_alerts_traffic_only_reaches_only_traffic_subscribers(monkeypatch):
    _install_fake_usi_modules(monkeypatch, alert_type="TRAFFIC_ONLY")
    traffic_citizen = _make_citizen("9000000022", WARD_HEBBAL, traffic=True, waste=False)
    waste_citizen = _make_citizen("9000000023", WARD_HEBBAL, traffic=False, waste=True)

    result = cad.dispatch_usi_alerts()

    assert result["citizens_notified"] == 1
    assert cad.get_deliveries_for_citizen(traffic_citizen["id"]) != []
    assert cad.get_deliveries_for_citizen(waste_citizen["id"]) == []


def test_dispatch_usi_alerts_urgent_combined_reaches_both_but_never_double_delivers_a_dual_subscriber(monkeypatch):
    _install_fake_usi_modules(monkeypatch, alert_type="URGENT_COMBINED")
    traffic_only = _make_citizen("9000000024", WARD_HEBBAL, traffic=True, waste=False)
    waste_only = _make_citizen("9000000025", WARD_HEBBAL, traffic=False, waste=True)
    both = _make_citizen("9000000026", WARD_HEBBAL, traffic=True, waste=True)
    neither = _make_citizen("9000000027", WARD_HEBBAL, traffic=False, waste=False)

    result = cad.dispatch_usi_alerts()

    assert result["citizens_notified"] == 3
    assert len(cad.get_deliveries_for_citizen(both["id"])) == 1  # not 2
    assert cad.get_deliveries_for_citizen(traffic_only["id"]) != []
    assert cad.get_deliveries_for_citizen(waste_only["id"]) != []
    assert cad.get_deliveries_for_citizen(neither["id"]) == []


def test_dispatch_usi_alerts_duplicate_run_same_instance_does_not_double_notify(monkeypatch):
    _install_fake_usi_modules(monkeypatch, alert_type="WASTE_ONLY")
    citizen = _make_citizen("9000000028", WARD_HEBBAL, traffic=False, waste=True)

    first = cad.dispatch_usi_alerts()
    assert first["citizens_notified"] == 1
    second = cad.dispatch_usi_alerts()
    assert second["citizens_notified"] == 0
    assert second["citizens_skipped_dedup"] == 1
    assert len(cad.get_deliveries_for_citizen(citizen["id"])) == 1


# ---------------------------------------------------------------------
# run_dispatch orchestration
# ---------------------------------------------------------------------

def test_run_dispatch_combines_both_sources(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch)
    traffic_citizen = _make_citizen("9000000030", WARD_RT_NAGAR)

    result = cad.run_dispatch()

    assert "traffic" in result and "usi" in result
    assert result["traffic"]["citizens_notified"] == 1
    assert result["citizens_notified_total"] >= 1
    assert "run_at" in result

# ---------------------------------------------------------------------
# Stage 3B: citizen_sms_provider wiring
#
# These tests never touch the real network -- they monkeypatch
# cad.citizen_sms_provider.send_sms() itself (the same seam
# _record_delivery() calls), so they can deterministically exercise the
# SENT/FAILED/SIMULATED_NOT_SENT branching and the "never send twice for
# one alert instance" guarantee without depending on citizen_sms_provider's
# own DEV_MODE/Exotel internals (those have their own dedicated test file,
# test_citizen_sms_provider.py, which is itself mock-only / never-real-
# network -- see that file's own docstring).
# ---------------------------------------------------------------------

def _install_fake_sms_provider(monkeypatch, result=None, calls=None):
    """Replaces cad.citizen_sms_provider.send_sms with a fake that
    records every call (mobile_number, text, language) into `calls` (a
    list the caller provides) and returns `result` (defaulting to a
    SENT outcome). Never imports or touches requests/sockets."""
    if result is None:
        result = {"status": "SENT", "provider_message_id": "FAKE-SID-1", "error": None}
    if calls is None:
        calls = []

    def fake_send_sms(mobile_number, text, language="en"):
        calls.append((mobile_number, text, language))
        return dict(result)

    monkeypatch.setattr(cad.citizen_sms_provider, "send_sms", fake_send_sms)
    return calls


def test_dispatch_records_sent_status_and_provider_message_id_from_provider(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch)
    calls = _install_fake_sms_provider(
        monkeypatch, result={"status": "SENT", "provider_message_id": "SMSreal123", "error": None},
    )
    citizen = _make_citizen("9000000040", WARD_RT_NAGAR)

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_notified"] == 1
    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "SENT"
    assert deliveries[0]["provider_message_id"] == "SMSreal123"
    assert deliveries[0]["provider_error"] is None
    assert len(calls) == 1
    assert calls[0][0] == citizen["mobile_number"]


def test_dispatch_records_failed_status_and_provider_error_from_provider(monkeypatch):
    _patch_active_traffic_incidents(monkeypatch)
    _install_fake_sms_provider(
        monkeypatch, result={"status": "FAILED", "provider_message_id": None, "error": "sms_provider_not_configured"},
    )
    citizen = _make_citizen("9000000041", WARD_RT_NAGAR)

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_notified"] == 1  # a delivery row WAS recorded -- a failed send is still a recorded attempt, not a fabricated success
    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert deliveries[0]["status"] == "FAILED"
    assert deliveries[0]["provider_message_id"] is None
    assert deliveries[0]["provider_error"] == "sms_provider_not_configured"


def test_dispatch_never_calls_provider_twice_for_the_same_alert_instance(monkeypatch):
    """The core safety guarantee this stage adds: a duplicate dispatch
    run for an alert instance that's already been recorded must not
    attempt a second real send -- whatever the first attempt's outcome
    was (SENT or FAILED)."""
    _patch_active_traffic_incidents(monkeypatch)
    calls = _install_fake_sms_provider(monkeypatch)
    citizen = _make_citizen("9000000042", WARD_RT_NAGAR)

    first = cad.dispatch_traffic_alerts()
    assert first["citizens_notified"] == 1
    second = cad.dispatch_traffic_alerts()
    assert second["citizens_notified"] == 0
    assert second["citizens_skipped_dedup"] == 1

    assert len(calls) == 1, "send_sms must be called exactly once for one alert instance, even across repeated dispatch runs"
    assert len(cad.get_deliveries_for_citizen(citizen["id"])) == 1


def test_dispatch_default_dev_mode_never_reaches_real_requests_post(monkeypatch):
    """Extra, independent safety net at the dispatch-integration level
    (on top of citizen_sms_provider's own unit tests): with
    CITIZEN_ALERTS_DEV_MODE unset (the default), a full dispatch run must
    never call requests.post at all -- proven here by monkeypatching
    requests.post itself to raise if it's ever invoked."""
    monkeypatch.delenv("CITIZEN_ALERTS_DEV_MODE", raising=False)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("requests.post must never be called while CITIZEN_ALERTS_DEV_MODE is on")

    monkeypatch.setattr(cad.citizen_sms_provider.requests, "post", _must_not_be_called)

    _patch_active_traffic_incidents(monkeypatch)
    citizen = _make_citizen("9000000043", WARD_RT_NAGAR)

    result = cad.dispatch_traffic_alerts()

    assert result["citizens_notified"] == 1
    deliveries = cad.get_deliveries_for_citizen(citizen["id"])
    assert deliveries[0]["status"] == "SIMULATED_NOT_SENT"
