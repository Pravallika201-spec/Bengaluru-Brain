"""
Builds a REAL geographic mapping between the traffic module's 25 curated
landmark locations (lat/lon from traffic_module/backend/location_data.py)
and the waste module's 366 named areas (centroid lat/lon computed from the
real polygon geometry in bengaluru_area_overflow_predictions.gpkg).

Two match types, both real (never invented):
  - "exact_name": the traffic location name matches a waste area name
    verbatim (case-insensitive) — the 6 areas found in the Phase 3 audit.
  - "spatial_nearest": no name match, but the traffic location's real
    coordinates fall within MAX_MATCH_KM of a real waste area centroid —
    a genuine geographic join, not a name guess. Distance is always
    reported so callers can judge match quality themselves.

Traffic locations with no waste area within MAX_MATCH_KM get no mapping
entry at all — coverage is not invented to fill gaps.

Run: python integration/build_area_mapping.py
Output: integration/area_mapping.json (consumed by usi_engine.py)
"""
import json
import math
import os
import sys

import geopandas as gpd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
TRAFFIC_BACKEND = os.path.join(PROJECT_ROOT, "traffic_module", "backend")
WASTE_GPKG = os.path.join(PROJECT_ROOT, "waste_module", "waste_module", "data",
                          "processed", "bengaluru_area_overflow_predictions.gpkg")
OUTPUT_PATH = os.path.join(HERE, "area_mapping.json")

MAX_MATCH_KM = 3.0
UTM_43N = 32643  # Bengaluru's local UTM zone, for accurate centroid computation

sys.path.insert(0, TRAFFIC_BACKEND)
from location_data import BENGALURU_LOCATIONS  # noqa: E402


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    gdf = gpd.read_file(WASTE_GPKG, layer="area_overflow_predictions")
    # Reproject to a local metric CRS before computing centroids (accurate),
    # then back to lat/lon degrees for the haversine join.
    centroids_metric = gdf.geometry.to_crs(UTM_43N).centroid
    centroids_deg = gpd.GeoSeries(centroids_metric, crs=UTM_43N).to_crs(4326)
    waste_areas = [
        {"name": row.area_name, "lat": pt.y, "lon": pt.x}
        for row, pt in zip(gdf.itertuples(index=False), centroids_deg)
    ]
    # Dedup by name (same area appears once per prediction_date row in some
    # exports; the gpkg here is one row per area, but be defensive)
    seen = {}
    for wa in waste_areas:
        seen.setdefault(wa["name"], wa)
    waste_areas = list(seen.values())

    mapping = {}
    for name, info in BENGALURU_LOCATIONS.items():
        exact = next((wa for wa in waste_areas if wa["name"].strip().lower() == name.strip().lower()), None)
        if exact:
            mapping[name] = {
                "waste_area_name": exact["name"],
                "match_type": "exact_name",
                "distance_km": 0.0,
            }
            continue

        best, best_dist = None, float("inf")
        for wa in waste_areas:
            d = haversine_km(info["lat"], info["lon"], wa["lat"], wa["lon"])
            if d < best_dist:
                best, best_dist = wa, d

        if best is not None and best_dist <= MAX_MATCH_KM:
            mapping[name] = {
                "waste_area_name": best["name"],
                "match_type": "spatial_nearest",
                "distance_km": round(best_dist, 3),
            }
        # else: no entry — coverage not invented for this location

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "max_match_km": MAX_MATCH_KM,
            "traffic_locations_total": len(BENGALURU_LOCATIONS),
            "waste_areas_total": len(waste_areas),
            "mapped_count": len(mapping),
            "mapping": mapping,
        }, f, indent=2)

    print(f"Mapped {len(mapping)}/{len(BENGALURU_LOCATIONS)} traffic locations to real waste areas:")
    for name, m in mapping.items():
        print(f"  {name:22s} -> {m['waste_area_name']:22s} "
              f"({m['match_type']}, {m['distance_km']} km)")
    unmapped = [n for n in BENGALURU_LOCATIONS if n not in mapping]
    if unmapped:
        print(f"\nNo waste area within {MAX_MATCH_KM} km for: {', '.join(unmapped)}")


if __name__ == "__main__":
    main()
