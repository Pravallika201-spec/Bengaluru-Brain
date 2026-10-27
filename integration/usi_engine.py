"""
Urban Severity Index (USI): fuses traffic_signal + waste_signal into one
composite 0-100 score per area, with a documented, configurable
methodology (usi_config.json) — not an arbitrary sum.

METHODOLOGY (see usi_config.json for the live numbers):
  1. Weighted linear blend of the two normalized (0-100) component scores.
     Default weights are equal (0.5/0.5) — edit usi_config.json to change,
     no code change needed.
  2. Missing-data handling: if one component has no data (None), the USI
     falls back to the other component ALONE (not zero-filled — a missing
     signal must never silently drag the index down) and the result is
     flagged partial_data=True so a dashboard can show that caveat.
  3. Compounding-risk bonus: when BOTH components are independently >= a
     "high" threshold (default 60/100, from usi_config.json
     severity_levels.medium_max), a modest bonus (+10, capped at 100) is
     added. Rationale: heavy traffic congestion measurably impedes waste
     collection vehicle access (this is exactly the OR-Tools routing this
     project already models — trucks stuck in traffic collect less, less
     often), so simultaneous highs represent worse real-world risk than
     their linear average suggests. This is a documented modeling choice,
     not a fabricated multiplier — it is applied identically and
     transparently to every area, and is reported separately in the
     result so it's never hidden inside an opaque final number.
  4. Bands: Green/Yellow/Orange/Red from usi_config.json bands
     (default cutoffs 40/60/80).

Both component scores AND their sources are always preserved in the
result, together with a human-readable `reason`, so a dashboard can
explain *why* an area scored as it did — never just the final number.
"""
import json
import os
from datetime import datetime

from traffic_signal import get_traffic_severity
from waste_signal import get_waste_severity

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usi_config.json")
AREA_MAPPING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "area_mapping.json")


def _load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_area_mapping():
    """Real traffic-location -> waste-area join, built by
    build_area_mapping.py from actual coordinates (exact name match, or a
    real nearest-neighbor spatial match within 3km — never invented). Falls
    back to an empty mapping (exact-name-only behavior) if the mapping
    hasn't been built yet on this machine."""
    if not os.path.exists(AREA_MAPPING_PATH):
        return {}
    try:
        with open(AREA_MAPPING_PATH, encoding="utf-8") as f:
            return json.load(f).get("mapping", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _level(score, levels):
    if score is None:
        return "UNKNOWN"
    if score <= levels["low_max"]:
        return "LOW"
    if score <= levels["medium_max"]:
        return "MEDIUM"
    if score <= levels["high_max"]:
        return "HIGH"
    return "CRITICAL"


def _band(usi, bands):
    if usi <= bands["green_max"]:
        return "Green"
    if usi <= bands["yellow_max"]:
        return "Yellow"
    if usi <= bands["orange_max"]:
        return "Orange"
    return "Red"


def compute_usi(area_name):
    config = _load_config()
    traffic = get_traffic_severity(area_name)

    area_mapping = _load_area_mapping()
    map_entry = area_mapping.get(traffic.get("area_name") or area_name)
    waste_lookup_name = map_entry["waste_area_name"] if map_entry else area_name
    waste = get_waste_severity(waste_lookup_name)
    if map_entry:
        waste["geo_match_type"] = map_entry["match_type"]
        waste["geo_match_distance_km"] = map_entry["distance_km"]
    else:
        waste["geo_match_type"] = "exact_name" if waste.get("severity") is not None else "none"
        waste["geo_match_distance_km"] = 0.0

    t_score = traffic.get("severity")
    w_score = waste.get("severity")
    tw, ww = config["traffic_weight"], config["waste_weight"]

    partial_data = False
    compounding_bonus_applied = False

    if t_score is None and w_score is None:
        usi = None
    elif t_score is None:
        usi = w_score
        partial_data = True
    elif w_score is None:
        usi = t_score
        partial_data = True
    else:
        usi = tw * t_score + ww * w_score
        high_threshold = config["severity_levels"]["medium_max"]
        if t_score >= high_threshold and w_score >= high_threshold:
            usi = min(100.0, usi + 10.0)
            compounding_bonus_applied = True

    band = _band(usi, config["bands"]) if usi is not None else "Unknown"
    t_level = _level(t_score, config["severity_levels"])
    w_level = _level(w_score, config["severity_levels"])

    reason_parts = []
    if t_score is not None:
        reason_parts.append(f"{t_level.title()} traffic congestion"
                             f"{' (simulated estimate)' if traffic['source'] == 'SIMULATED_WARD_STRESS' else ''}")
    if w_score is not None:
        reason_parts.append(f"{w_level.title()} waste overflow risk")
    if compounding_bonus_applied:
        reason_parts.append("compounded because both are elevated at once, "
                             "hampering waste-truck access")
    if map_entry and map_entry["match_type"] == "spatial_nearest":
        reason_parts.append(f"waste data joined from the nearest real area "
                             f"({waste.get('area_name')}, {map_entry['distance_km']}km away)")
    reason = " and ".join(reason_parts) if reason_parts else "No traffic or waste data available for this area."

    # Confidence/coverage status — never hidden inside the final number.
    if t_score is None or w_score is None:
        coverage_status = "LOW (missing one signal)"
    elif traffic["source"] == "REAL_GNN" and waste["geo_match_type"] == "exact_name":
        coverage_status = "HIGH (real GNN + exact-name waste match)"
    elif traffic["source"] == "REAL_GNN" or waste["geo_match_type"] == "exact_name":
        coverage_status = "MEDIUM-HIGH (one real+exact signal, one simulated/spatial)"
    elif waste["geo_match_type"] == "spatial_nearest":
        coverage_status = f"MEDIUM (waste joined via {waste['geo_match_distance_km']}km spatial match, traffic simulated)"
    else:
        coverage_status = "MEDIUM (both signals present but at least one simulated)"

    return {
        "area_name": traffic.get("area_name") or waste.get("area_name") or area_name,
        "traffic": {"score": t_score, "level": t_level, "source": traffic["source"], "detail": traffic["detail"]},
        "waste": {"score": w_score, "level": w_level, "source": waste["source"], "detail": waste["detail"],
                  "geo_match_type": waste.get("geo_match_type"), "geo_match_distance_km": waste.get("geo_match_distance_km"),
                  # Explicit score-breakdown transparency: base model score vs.
                  # citizen-report contribution vs. the final (capped-at-100)
                  # score actually used above. All three numbers are real
                  # values from get_waste_severity(), not display-only math.
                  "base_score": waste.get("model_score"),
                  "citizen_report_contribution": waste.get("citizen_report_bonus"),
                  "citizen_report_count_7d": waste.get("citizen_report_count_7d"),
                  "final_score": w_score,
                  "score_breakdown_text": (
                      f"Base waste score: {waste.get('model_score')} / "
                      f"Citizen report contribution: +{waste.get('citizen_report_bonus')} / "
                      f"Final score: {w_score}"
                  ) if waste.get("model_score") is not None else None},
        "usi": round(usi, 1) if usi is not None else None,
        "band": band,
        "partial_data": partial_data,
        "compounding_bonus_applied": compounding_bonus_applied,
        "coverage_status": coverage_status,
        "reason": reason.capitalize() + ".",
        "methodology_weights": {"traffic_weight": tw, "waste_weight": ww},
        "timestamp": datetime.now().isoformat(),
    }
