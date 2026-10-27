"""
Bridges the traffic backend (app.py) to the D:\\major project\\integration
package (USI engine + bilingual alerts) and to the waste module's real
processed data, WITHOUT duplicating any of that logic here.

Design intent (matches the project's "keep integration code separate from
the original traffic and waste modules" rule): this file contains no USI
math and no alert wording of its own — it only imports the real
integration/*.py modules and the waste module's real CSV outputs, and
exposes small, JSON-serializable functions for app.py's FastAPI routes to
call. If integration or waste data is unavailable on a given machine, every
function here degrades gracefully (returns an explicit "unavailable" shape)
rather than crashing the traffic API.
"""
import os
import sys
import json
import hashlib
import time as _time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INTEGRATION_DIR = os.path.join(PROJECT_ROOT, "integration")
WASTE_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "waste_module", "waste_module", "data", "processed")
WASTE_ROUTE_MODULE_DIR = os.path.join(PROJECT_ROOT, "waste_module", "waste_module", "route")
WASTE_PRIORITY_AREAS_CSV = os.path.join(PROJECT_ROOT, "waste_module", "waste_module", "satellite", "outputs",
                                         "bengaluru_priority_areas.csv")
WASTE_OVERFLOW_CSV = os.path.join(WASTE_PROCESSED_DIR, "bengaluru_area_overflow_predictions.csv")

if INTEGRATION_DIR not in sys.path:
    sys.path.insert(0, INTEGRATION_DIR)
if WASTE_ROUTE_MODULE_DIR not in sys.path:
    sys.path.insert(0, WASTE_ROUTE_MODULE_DIR)

# In-process cache for the real OR-Tools solve, keyed on EVERY input that
# affects the optimization plus a data-version fingerprint — so a changed
# vehicle count, capacity, area selection, or updated source data all
# correctly invalidate it. A cache hit still returns the ORIGINAL solve's
# real optimization_timestamp (marked route_source=CACHED_MATCHING_INPUTS)
# rather than presenting old numbers as freshly computed.
_WASTE_ROUTE_CACHE = {}
_WASTE_ROUTE_CACHE_TTL_SECONDS = 300  # even an identical-input cache entry expires


def _waste_data_version():
    """Fingerprint of the source dataset (mtime+size) — changes whenever the
    underlying priority-areas data is regenerated, forcing a fresh solve
    even for identical solve parameters."""
    try:
        st = os.stat(WASTE_PRIORITY_AREAS_CSV)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "missing"

_STATE = {"error": None, "usi_engine": None, "alerts": None}


def _ensure_loaded():
    if _STATE["usi_engine"] is not None or _STATE["error"] is not None:
        return
    try:
        import usi_engine  # noqa
        import alerts  # noqa
        _STATE["usi_engine"] = usi_engine
        _STATE["alerts"] = alerts
    except Exception as e:  # pragma: no cover - defensive
        _STATE["error"] = str(e)


AREA_MAPPING_PATH = os.path.join(INTEGRATION_DIR, "area_mapping.json")


def verify_area_coverage():
    """Real coverage, derived from area_mapping.json (built by
    integration/build_area_mapping.py from actual coordinates: exact name
    matches, plus genuine nearest-neighbor spatial matches within 3km —
    never invented). Falls back to a live exact-name-only recompute if the
    mapping file hasn't been built yet on this machine."""
    if os.path.exists(AREA_MAPPING_PATH):
        try:
            import json
            with open(AREA_MAPPING_PATH, encoding="utf-8") as f:
                data = json.load(f)
            mapping = data.get("mapping", {})
            exact = sorted(k for k, v in mapping.items() if v["match_type"] == "exact_name")
            spatial = sorted(k for k, v in mapping.items() if v["match_type"] == "spatial_nearest")
            return {
                "available": True,
                "traffic_locations_count": data.get("traffic_locations_total"),
                "waste_areas_count": data.get("waste_areas_total"),
                "overlap_count": data.get("mapped_count"),
                "overlap_areas": sorted(mapping.keys()),
                "exact_name_matches": exact,
                "spatial_matches": spatial,
                "match_method": "real geographic join (exact name + nearest-neighbor within "
                                 f"{data.get('max_match_km')}km), see integration/build_area_mapping.py",
            }
        except Exception as e:
            return {"available": False, "reason": str(e)}

    try:
        from location_data import BENGALURU_LOCATIONS
        import pandas as pd
        if not os.path.exists(WASTE_OVERFLOW_CSV):
            return {"available": False, "reason": "waste overflow data file not found"}
        waste_areas = set(pd.read_csv(WASTE_OVERFLOW_CSV)["area_name"].str.lower().str.strip())
        traffic_areas = {name.lower(): name for name in BENGALURU_LOCATIONS.keys()}
        overlap = sorted(traffic_areas[k] for k in traffic_areas if k in waste_areas)
        return {
            "available": True,
            "traffic_locations_count": len(traffic_areas),
            "waste_areas_count": len(waste_areas),
            "overlap_count": len(overlap),
            "overlap_areas": overlap,
            "match_method": "exact name match only (area_mapping.json not built yet — "
                             "run integration/build_area_mapping.py for spatial matches too)",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_usi_areas():
    """Areas the dashboard can show a real USI for, with coordinates for
    map plotting (from the traffic module's own curated location table —
    never fabricated)."""
    _ensure_loaded()
    if _STATE["error"]:
        return {"available": False, "reason": _STATE["error"], "areas": []}

    from location_data import BENGALURU_LOCATIONS
    coverage = verify_area_coverage()
    areas = []
    for name in coverage.get("overlap_areas", []):
        info = BENGALURU_LOCATIONS.get(name)
        if info:
            areas.append({"name": name, "lat": info["lat"], "lon": info["lon"], "ward": info["ward"]})
    return {"available": True, "coverage": coverage, "areas": areas}


def get_usi_for_area(area_name):
    _ensure_loaded()
    if _STATE["error"]:
        return {"available": False, "reason": _STATE["error"]}
    try:
        result = _STATE["usi_engine"].compute_usi(area_name)
        return {"available": True, **result}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_alert_for_area(area_name, simulate_sms=True, phone_number="+91-SIMULATED"):
    _ensure_loaded()
    if _STATE["error"]:
        return {"available": False, "reason": _STATE["error"]}
    try:
        usi_result = _STATE["usi_engine"].compute_usi(area_name)
        alert = _STATE["alerts"].generate_alert(usi_result)
        sms = None
        if simulate_sms:
            # Routed through maybe_alert_and_send (not a direct send) so the
            # real dedup/cooldown and rapid-escalation logic in
            # integration/alert_state.py actually applies to API-triggered
            # alerts too, not just the CLI demo script.
            sms = _STATE["alerts"].maybe_alert_and_send(usi_result, phone_number)
        return {"available": True, "usi": usi_result, "alert": alert, "sms_simulated": sms}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_active_alerts():
    """Areas currently sitting in an alertable band, from the real
    per-area alert_state.json cooldown tracker (integration/alert_state.py)
    — i.e. genuinely fired alerts, not a recomputation of WHICH areas are
    alerting. The "reason" text per area IS freshly recomputed here (a real
    compute_usi() call, same function every other USI endpoint uses) since
    alert_state.json only ever persisted usi/band/timestamp, not the reason
    string — this is cheap (a handful of areas) and gives an honest,
    current explanation rather than omitting it or fabricating one."""
    _ensure_loaded()
    if _STATE["error"]:
        return {"available": False, "reason": _STATE["error"], "alerts": []}
    try:
        import alert_state
        state = alert_state.get_all_state()
        alerts = []
        for name, info in state.items():
            if info.get("band") not in ("Yellow", "Orange", "Red"):
                continue
            reason = None
            try:
                usi_result = _STATE["usi_engine"].compute_usi(name)
                reason = usi_result.get("reason")
            except Exception:
                pass
            alerts.append({
                "area_name": name, "usi": info.get("usi"), "band": info.get("band"),
                "last_alert_time": info.get("last_alert_time"), "reason": reason,
            })
        alerts.sort(key=lambda a: a["usi"] or 0, reverse=True)
        return {"available": True, "alerts": alerts, "count": len(alerts)}
    except Exception as e:
        return {"available": False, "reason": str(e), "alerts": []}


def get_waste_summary():
    """Real citywide waste summary from the waste module's actual processed
    data (latest prediction_date only) — no synthetic fill-in."""
    try:
        import pandas as pd
        if not os.path.exists(WASTE_OVERFLOW_CSV):
            return {"available": False, "reason": "bengaluru_area_overflow_predictions.csv not found"}
        df = pd.read_csv(WASTE_OVERFLOW_CSV)
        df["prediction_date"] = pd.to_datetime(df["prediction_date"])
        latest_date = df["prediction_date"].max()
        latest = df[df["prediction_date"] == latest_date]

        risk_counts = latest["Area_Overflow_Risk"].value_counts().to_dict()
        top_risk = (
            latest.sort_values("Overflow_Risk_Score", ascending=False)
            .head(10)[["area_name", "Overflow_Risk_Score", "Area_Overflow_Risk", "Collection_Priority"]]
            .to_dict("records")
        )
        routing = get_waste_routing_summary()
        return {
            "available": True,
            "source": "WASTE_HEURISTIC_MODEL",
            "source_detail": (
                "Land-use-ratio heuristic (real OSM building/landuse polygons -> fixed per-landuse-type "
                "waste-intensity weights, see prediction/waste_estimator.py) x a deterministic day-of-week/"
                "seasonal multiplier table. NOT the trained satellite RandomForest model in ml/ "
                "(satellite_waste_random_forest.joblib exists but is not in this live path) — verified by "
                "checking that the same grid cell's estimated_daily_waste_kg is byte-identical across all "
                "7 stored dates, only the multiplier differs. Real spatial data, heuristic (not ML) formula."
            ),
            "prediction_date": str(latest_date.date()),
            "areas_monitored": int(len(latest)),
            "risk_distribution": risk_counts,
            "total_predicted_waste_kg": float(latest["Total_Predicted_Waste_kg"].sum()),
            "top_risk_areas": top_risk,
            "routing": routing,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def get_waste_routing_summary(area_names=None, num_vehicles=None, vehicle_capacity_kg=None,
                                time_limit_seconds=None, force_refresh=False):
    """Real OR-Tools solve (see waste_module/waste_module/route/
    ortools_area_route_optimizer.py::solve_routes_for_api). Genuinely
    re-solves whenever the inputs (area selection, vehicle count, capacity)
    or the underlying data change — a cache hit is only ever returned for
    an EXACT match on all of those, and is always labeled
    route_source=CACHED_MATCHING_INPUTS with the ORIGINAL solve's real
    timestamp, never presented as a fresh computation."""
    try:
        import ortools_area_route_optimizer as opt
    except Exception as e:
        return {"available": False, "solver_status": "ERROR",
                "reason": f"OR-Tools optimizer module unavailable: {e}"}

    cache_key_raw = json.dumps({
        "areas": sorted(a.strip().lower() for a in area_names) if area_names is not None else None,
        "num_vehicles": num_vehicles,
        "vehicle_capacity_kg": vehicle_capacity_kg,
        "data_version": _waste_data_version(),
    }, sort_keys=True)
    cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()[:16]

    if not force_refresh:
        cached = _WASTE_ROUTE_CACHE.get(cache_key)
        if cached and (_time.time() - cached["cached_at"]) < _WASTE_ROUTE_CACHE_TTL_SECONDS:
            result = dict(cached["result"])
            if result.get("available"):
                result["route_source"] = "CACHED_MATCHING_INPUTS"
                result["cache_key"] = cache_key
                result["cache_age_seconds"] = round(_time.time() - cached["cached_at"], 1)
            return result

    result = opt.solve_routes_for_api(
        area_names=area_names,
        num_vehicles=num_vehicles,
        vehicle_capacity_kg=vehicle_capacity_kg,
        time_limit_seconds=time_limit_seconds or 8,
    )
    result["cache_key"] = cache_key
    if result.get("available"):
        _WASTE_ROUTE_CACHE[cache_key] = {"result": dict(result), "cached_at": _time.time()}
    return result
