"""
Thin accessor for integration/geo/ward_registry.json — the real, per-ward
coverage registry (see integration/geo/build_ward_registry.py for exactly
how it was built and from which real sources). This module contains no
logic of its own, matching the project's pattern of keeping cross-module
data access as thin bridges.
"""
import json
import os

REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "integration", "geo", "ward_registry.json",
)

_cache = {"data": None}


def _load():
    if _cache["data"] is None:
        if not os.path.exists(REGISTRY_PATH):
            return None
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            _cache["data"] = json.load(f)
    return _cache["data"]


def get_ward_summary():
    data = _load()
    if data is None:
        return {"available": False, "reason": "ward_registry.json not built yet — "
                                                "run integration/geo/build_ward_registry.py"}
    return {
        "available": True,
        "total_wards": data["total_wards"],
        "wards_with_precise_boundary": data.get("wards_with_precise_boundary", 0),
        "coverage_summary": data["coverage_summary"],
        "built_from": data["built_from"],
    }


def get_all_wards():
    data = _load()
    if data is None:
        return {"available": False, "reason": "ward_registry.json not built yet", "wards": []}
    return {"available": True, "wards": list(data["wards"].values())}


def get_ward(ward_id):
    data = _load()
    if data is None:
        return {"available": False, "reason": "ward_registry.json not built yet"}
    ward = data["wards"].get(str(ward_id))
    if ward is None:
        return {"available": False, "reason": f"No ward with id {ward_id}"}
    return {"available": True, **ward}
