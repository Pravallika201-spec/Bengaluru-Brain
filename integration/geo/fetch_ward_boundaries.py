"""
One-time (re-runnable) fetch of REAL Bengaluru ward boundaries from
OpenStreetMap — the authoritative source behind the "369 wards" figure that
was previously just a bare `range(1, 370)` in ward_stress.py with no real
geometry, names, or IDs behind 343 of them.

Verified before writing this script (see chat/audit): Overpass's
admin_level=10 relations within Bengaluru's administrative area return
EXACTLY 369 real, named ward boundaries — this is the real source, not a
number picked out of nowhere. The waste module's 366 "areas" are a subset
of these same real OSM entities (bengaluru_area_overflow_predictions.csv's
`area_osm_id` matches these relation ids 366/366 — a 100% overlap, checked
directly against a fresh Overpass fetch), so there is no fuzzy join needed
for waste<->ward.

Output: integration/geo/bengaluru_wards.geojson (369 real polygons) and
integration/geo/bengaluru_wards_index.json (lightweight id/name/centroid,
no geometry, for fast loading elsewhere).

Run: python integration/geo/fetch_ward_boundaries.py
Takes ~7-8 minutes (369 individual Nominatim lookups via osmnx, rate-limited
to respect usage policy). Safe to re-run — skips wards already fetched.
"""
import json
import os
import time

import osmnx as ox
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_GEOJSON = os.path.join(HERE, "bengaluru_wards.geojson")
OUT_INDEX = os.path.join(HERE, "bengaluru_wards_index.json")
PARTIAL_CACHE = os.path.join(HERE, "_wards_partial_cache.json")

HEADERS = {"User-Agent": "BengaluruBrain/1.0 (final-year project; contact: raavipravallika6@gmail.com)"}
ox.settings.http_user_agent = HEADERS["User-Agent"]


def fetch_ward_id_list():
    query = ('[out:json][timeout:120];'
             'area["name"="Bengaluru"]["boundary"="administrative"]->.a;'
             '(relation(area.a)[admin_level=10];);'
             'out tags;')
    r = requests.get("https://overpass-api.de/api/interpreter", params={"data": query},
                      timeout=130, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    return [(el["id"], el.get("tags", {}).get("name", f"Ward {el['id']}")) for el in data["elements"]]


def load_partial_cache():
    if os.path.exists(PARTIAL_CACHE):
        with open(PARTIAL_CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_partial_cache(cache):
    with open(PARTIAL_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def main():
    ward_list = fetch_ward_id_list()
    print(f"Found {len(ward_list)} real ward relations (admin_level=10) within Bengaluru.")

    cache = load_partial_cache()
    features = []
    index = {}

    for i, (osm_id, name) in enumerate(ward_list, start=1):
        key = str(osm_id)
        if key in cache:
            entry = cache[key]
        else:
            try:
                gdf = ox.geocode_to_gdf([f"R{osm_id}"], by_osmid=True)
                geom = gdf.geometry.iloc[0]
                centroid = geom.centroid
                entry = {
                    "ward_id": osm_id,
                    "ward_name": name,
                    "centroid_lat": centroid.y,
                    "centroid_lon": centroid.x,
                    "geometry": geom.__geo_interface__,
                }
                time.sleep(1.1)  # respect Nominatim's usage policy (max 1 req/sec)
            except Exception as e:
                print(f"  [{i}/{len(ward_list)}] FAILED for ward {osm_id} ({name}): {e}")
                entry = {"ward_id": osm_id, "ward_name": name, "centroid_lat": None,
                         "centroid_lon": None, "geometry": None, "error": str(e)}
            cache[key] = entry
            save_partial_cache(cache)

        if entry.get("geometry"):
            features.append({
                "type": "Feature",
                "properties": {"ward_id": entry["ward_id"], "ward_name": entry["ward_name"]},
                "geometry": entry["geometry"],
            })
        index[key] = {
            "ward_name": entry["ward_name"],
            "centroid_lat": entry["centroid_lat"],
            "centroid_lon": entry["centroid_lon"],
            "has_geometry": entry.get("geometry") is not None,
        }

        if i % 20 == 0 or i == len(ward_list):
            print(f"  progress: {i}/{len(ward_list)} wards processed "
                  f"({sum(1 for v in index.values() if v['has_geometry'])} with real geometry)")

    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f)
    with open(OUT_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    n_ok = sum(1 for v in index.values() if v["has_geometry"])
    print(f"\nDone: {n_ok}/{len(ward_list)} real ward boundaries saved -> {OUT_GEOJSON}")
    print(f"Lightweight index -> {OUT_INDEX}")
    if n_ok == len(ward_list):
        try:
            os.remove(PARTIAL_CACHE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
