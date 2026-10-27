"""
Bengaluru Locations Database
Contains all major Bengaluru locations with coordinates and ward identity.

WARD IDENTITY MODEL (canonical, fixed 2026-09-03 — see Priority 2 audit):
Each location carries BOTH:
  - "canonical_ward_id" / "canonical_ward_name": the REAL BBMP/OSM ward this
    location's coordinates fall inside (or nearest to), resolved by point-
    in-polygon against integration/geo/bengaluru_wards.geojson — the same
    369-real-ward registry used by /api/wards/*, the waste module's
    area_osm_id join, and USI's ward-level view. This is the ONE canonical
    identity to use for any new cross-module join.
  - "legacy_ward_id": the OLD hand-entered integer this project used before
    the canonical model existed. It is UNRELATED to any real BBMP/OSM ward
    numbering (it was never derived from geodata) and is KEPT ONLY for
    backward compatibility with ward_stress.py's pre-existing IT_ZONE_WARDS/
    MAJOR_CORRIDORS lists during the transition — do not use it for new
    code, and do not assume two locations sharing a legacy_ward_id are
    geographically related (a genuine bug found during this audit: Silk
    Board and HSR Layout both had legacy_ward_id=174 by coincidence, with no
    real geographic basis — their canonical_ward_id values differ only by
    chance now genuinely matching, both real areas being in the same real
    "HSR Layout" ward).

The canonical mapping was computed once via point-in-polygon (or nearest-
centroid fallback where a location falls just outside a fetched boundary)
and cached at integration/geo/derived/traffic_location_canonical_wards.json
— see integration/geo/build_ward_registry.py sibling tooling for the method.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANONICAL_WARD_LOOKUP_PATH = os.path.join(
    _HERE, "..", "..", "integration", "geo", "derived", "traffic_location_canonical_wards.json"
)


def _load_canonical_ward_lookup():
    try:
        with open(_CANONICAL_WARD_LOOKUP_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


_CANONICAL_WARDS = _load_canonical_ward_lookup()

# legacy_ward_id: the old hand-entered numbers, preserved verbatim (including
# the pre-existing duplicate-by-coincidence values) for backward-compat only.
_LEGACY_WARD_IDS = {
    "Hebbal": 6, "Silk Board": 174, "Manyata Tech Park": 7, "Electronic City": 195,
    "Whitefield": 84, "Koramangala": 68, "Indiranagar": 81, "Marathahalli": 85,
    "HSR Layout": 174, "BTM Layout": 168, "Jayanagar": 155, "JP Nagar": 161,
    "Banashankari": 148, "Rajajinagar": 99, "Yeshwanthpur": 98, "Yelahanka": 3,
    "KR Puram": 24, "Bannerghatta Road": 191, "MG Road": 76, "Shivajinagar": 74,
    "Malleswaram": 96, "Sarjapur Road": 175, "Outer Ring Road": 85,
    "Tumkur Road": 104, "Bellary Road": 5,
}

_RAW_COORDS = {
    # Hebbal/Silk Board corrected to the actual named junction coordinates
    # (verified against real OSM road nodes in traffic_location_mapping.csv —
    # "Hebbal Flyover"/"Silk Board Junction" rows) rather than a rounded
    # 3-decimal area centroid. The centroid was close enough to a DIFFERENT
    # nearby road that OSRM silently routed via a shorter, wrong-corridor
    # path (17.2 km via Sankey/Millers Road instead of ~20.9 km via the real
    # Bellary Road -> Outer Ring Road -> Bannerghatta Road corridor) — this
    # was the root cause of a distance-correctness bug caught by manual
    # review, confirmed by re-querying OSRM directly with both coordinate
    # sets. See FINAL_PROJECT_AUDIT.md / traffic correctness notes.
    "Hebbal": {"lat": 13.041662, "lon": 77.5899438, "it_zone": False},
    "Silk Board": {"lat": 12.9158171, "lon": 77.6240368, "it_zone": False},
    "Manyata Tech Park": {"lat": 13.043, "lon": 77.620, "it_zone": True},
    "Electronic City": {"lat": 12.839, "lon": 77.677, "it_zone": True},
    "Whitefield": {"lat": 12.969, "lon": 77.750, "it_zone": True},
    "Koramangala": {"lat": 12.935, "lon": 77.627, "it_zone": False},
    "Indiranagar": {"lat": 12.979, "lon": 77.638, "it_zone": False},
    "Marathahalli": {"lat": 12.956, "lon": 77.701, "it_zone": False},
    "HSR Layout": {"lat": 12.913, "lon": 77.644, "it_zone": False},
    "BTM Layout": {"lat": 12.916, "lon": 77.610, "it_zone": False},
    "Jayanagar": {"lat": 12.931, "lon": 77.583, "it_zone": False},
    "JP Nagar": {"lat": 12.901, "lon": 77.585, "it_zone": False},
    "Banashankari": {"lat": 12.925, "lon": 77.547, "it_zone": False},
    "Rajajinagar": {"lat": 12.989, "lon": 77.552, "it_zone": False},
    "Yeshwanthpur": {"lat": 13.021, "lon": 77.545, "it_zone": False},
    "Yelahanka": {"lat": 13.100, "lon": 77.596, "it_zone": False},
    "KR Puram": {"lat": 13.008, "lon": 77.696, "it_zone": False},
    "Bannerghatta Road": {"lat": 12.872, "lon": 77.597, "it_zone": False},
    "MG Road": {"lat": 12.975, "lon": 77.609, "it_zone": False},
    "Shivajinagar": {"lat": 12.985, "lon": 77.600, "it_zone": False},
    "Malleswaram": {"lat": 13.003, "lon": 77.568, "it_zone": False},
    "Sarjapur Road": {"lat": 12.906, "lon": 77.685, "it_zone": False},
    "Outer Ring Road": {"lat": 12.956, "lon": 77.696, "it_zone": False},
    "Tumkur Road": {"lat": 13.030, "lon": 77.520, "it_zone": False},
    "Bellary Road": {"lat": 13.050, "lon": 77.595, "it_zone": False},
}

BENGALURU_LOCATIONS = {}
for _name, _info in _RAW_COORDS.items():
    _canon = _CANONICAL_WARDS.get(_name, {})
    BENGALURU_LOCATIONS[_name] = {
        **_info,
        "legacy_ward_id": _LEGACY_WARD_IDS.get(_name),
        "canonical_ward_id": _canon.get("canonical_ward_id"),
        "canonical_ward_name": _canon.get("canonical_ward_name"),
        # "ward" kept as an alias of canonical_ward_id (not legacy_ward_id)
        # so any code still reading info["ward"] gets the REAL identity,
        # not the old arbitrary number.
        "ward": _canon.get("canonical_ward_id"),
    }


def get_location_info(location_name):
    """Get location information by name"""
    return BENGALURU_LOCATIONS.get(location_name)


def get_ward_name(canonical_ward_id):
    """Real ward name for a canonical (OSM) ward id, via the same lookup
    used to build BENGALURU_LOCATIONS. Falls back to a generic label only if
    the id isn't one of the 25 curated locations' wards."""
    for info in BENGALURU_LOCATIONS.values():
        if info.get("canonical_ward_id") == canonical_ward_id:
            return info.get("canonical_ward_name")
    return f"Ward {canonical_ward_id}"


def get_all_locations():
    """Get all available locations"""
    return list(BENGALURU_LOCATIONS.keys())


def get_it_zones():
    """Get all IT zone locations"""
    return [name for name, info in BENGALURU_LOCATIONS.items() if info["it_zone"]]
