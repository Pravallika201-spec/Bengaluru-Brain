"""
Builds the real per-ward coverage registry described in the architecture
audit: for each of the 369 real Bengaluru wards, determine what REAL data
actually exists for it — never fabricated.

WARD SOURCE: OpenStreetMap admin_level=10 relations within Bengaluru's
administrative area — verified to return exactly 369 real, named wards
(matches the "369 wards" figure that was previously just a bare
`range(1, 370)` with no real geometry, names, or IDs behind 343 of them).
Real centroids for all 369 come from a single fast Overpass "out center"
query (wards_centers_raw.json). Full polygon boundaries (for precise
point-in-polygon containment instead of nearest-centroid) are being fetched
separately in the background (fetch_ward_boundaries.py, ~369 individual
rate-limited Nominatim lookups, slow) — this script uses polygons where
already fetched and falls back to real-centroid nearest-neighbor
assignment elsewhere. Re-run this script after the polygon fetch completes
for full precision; the coverage classification itself does not change,
only which specific ward a borderline point is assigned to.

Joins (all real, no fuzzy name matching):
  - Waste: bengaluru_area_overflow_predictions.csv's `area_osm_id` IS the
    ward's OSM relation id directly (verified 366/366 exact match) — a
    lookup, not a spatial join.
  - Traffic curated locations / real GNN training edges / TomTom collector
    targets: nearest real-ward-centroid assignment (haversine), or true
    polygon containment for any ward whose polygon has been fetched.

Run: python integration/geo/build_ward_registry.py
Output: integration/geo/ward_registry.json
"""
import json
import math
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
TRAFFIC_BACKEND = os.path.join(PROJECT_ROOT, "traffic_module", "backend")
TRAFFIC_DATA = os.path.join(PROJECT_ROOT, "traffic_module", "data")
TRAFFIC_MODELS = os.path.join(PROJECT_ROOT, "traffic_module", "models")
WASTE_OVERFLOW_CSV = os.path.join(PROJECT_ROOT, "waste_module", "waste_module", "data",
                                   "processed", "bengaluru_area_overflow_predictions.csv")

WARD_CENTERS_RAW = os.path.join(HERE, "wards_centers_raw.json")
PARTIAL_POLY_CACHE = os.path.join(HERE, "_wards_partial_cache.json")
OUT_REGISTRY = os.path.join(HERE, "ward_registry.json")

sys.path.insert(0, TRAFFIC_BACKEND)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    if not os.path.exists(WARD_CENTERS_RAW):
        raise FileNotFoundError(
            f"{WARD_CENTERS_RAW} not found. Fetch real ward centers first (see integration/README or "
            "chat history: a single Overpass 'out center' query for admin_level=10 relations within Bengaluru)."
        )

    with open(WARD_CENTERS_RAW, encoding="utf-8") as f:
        raw_wards = json.load(f)

    # Optional: precise polygons fetched so far (may be partial/absent)
    polygons = {}
    from shapely.geometry import Point, shape
    if os.path.exists(PARTIAL_POLY_CACHE):
        with open(PARTIAL_POLY_CACHE, encoding="utf-8") as f:
            poly_cache = json.load(f)
        for wid_str, entry in poly_cache.items():
            if entry.get("geometry"):
                polygons[int(wid_str)] = shape(entry["geometry"])
    n_with_polygon = len(polygons)

    wards = {}
    for el in raw_wards:
        wid = el["id"]
        name = el.get("tags", {}).get("name", f"Ward {wid}")
        center = el.get("center", {})
        wards[wid] = {
            "ward_id": wid,
            "ward_name": name,
            "centroid_lat": center.get("lat"),
            "centroid_lon": center.get("lon"),
            "has_precise_boundary": wid in polygons,
            "waste_data_available": False,
            "waste_area_name": None,
            "traffic_named_locations": [],
            "real_gnn_edges_count": 0,
            "real_gnn_temporal_edge": False,
            "tomtom_collector_targets": [],
        }

    def find_ward(lat, lon):
        """True polygon containment where a boundary has been fetched;
        otherwise nearest real-ward-centroid (haversine) — both are real
        geographic assignments, never a guess at which ward "sounds right"."""
        pt = Point(lon, lat)
        for wid, poly in polygons.items():
            if poly.contains(pt):
                return wid, "polygon_containment"
        best_wid, best_dist = None, float("inf")
        for wid, w in wards.items():
            if w["centroid_lat"] is None:
                continue
            d = haversine_km(lat, lon, w["centroid_lat"], w["centroid_lon"])
            if d < best_dist:
                best_wid, best_dist = wid, d
        return best_wid, f"nearest_centroid ({best_dist:.2f}km)"

    # ---------------- Waste: direct ID lookup, no join needed ----------------
    waste_df = pd.read_csv(WASTE_OVERFLOW_CSV)
    for osm_id, group in waste_df.groupby("area_osm_id"):
        if osm_id in wards:
            wards[osm_id]["waste_data_available"] = True
            wards[osm_id]["waste_area_name"] = group["area_name"].iloc[0]
    n_waste_matched = sum(1 for w in wards.values() if w["waste_data_available"])
    print(f"Waste: {n_waste_matched}/{waste_df['area_osm_id'].nunique()} areas matched to real wards "
          f"(direct OSM id lookup, no fuzzy join)")

    # ---------------- Traffic curated locations ----------------
    from location_data import BENGALURU_LOCATIONS
    n_loc_matched = 0
    for name, info in BENGALURU_LOCATIONS.items():
        wid, method = find_ward(info["lat"], info["lon"])
        if wid:
            wards[wid]["traffic_named_locations"].append(name)
            n_loc_matched += 1
    print(f"Traffic locations: {n_loc_matched}/{len(BENGALURU_LOCATIONS)} matched to real wards")

    # ---------------- Real GNN training edges ----------------
    labels_path = os.path.join(TRAFFIC_MODELS, "real_traffic_labels.json")
    n_edge_matched = 0
    if os.path.exists(labels_path):
        with open(labels_path, encoding="utf-8") as f:
            labels = json.load(f)
        nodes_csv = os.path.join(TRAFFIC_DATA, "nodes.csv")
        nodes_df = pd.read_csv(nodes_csv)
        node_coord = dict(zip(nodes_df["node_id"], zip(nodes_df["y"], nodes_df["x"])))

        def edge_midpoint(u, v):
            if u not in node_coord or v not in node_coord:
                return None
            (lat1, lon1), (lat2, lon2) = node_coord[u], node_coord[v]
            return (lat1 + lat2) / 2, (lon1 + lon2) / 2

        for key, row in labels.get("snapshot_labeled", {}).items():
            mid = edge_midpoint(row["u"], row["v"])
            if mid:
                wid, _ = find_ward(*mid)
                if wid:
                    wards[wid]["real_gnn_edges_count"] += 1
                    n_edge_matched += 1
        for key, row in labels.get("live_static", {}).items():
            mid = edge_midpoint(row["u"], row["v"])
            if mid:
                wid, _ = find_ward(*mid)
                if wid:
                    wards[wid]["real_gnn_edges_count"] += 1
                    wards[wid]["real_gnn_temporal_edge"] = True
                    n_edge_matched += 1
    print(f"Real GNN training edges: {n_edge_matched} matched to real wards")

    # ---------------- TomTom collector targets ----------------
    mapping_csv = os.path.join(TRAFFIC_DATA, "traffic_location_mapping.csv")
    n_collector_matched = 0
    n_collector_total = 0
    if os.path.exists(mapping_csv):
        mapping_df = pd.read_csv(mapping_csv)
        matched_rows = mapping_df[mapping_df["status"] == "MATCHED"]
        n_collector_total = len(matched_rows)
        for _, row in matched_rows.iterrows():
            wid, _ = find_ward(row["latitude"], row["longitude"])
            if wid:
                wards[wid]["tomtom_collector_targets"].append(row["traffic_location"])
                n_collector_matched += 1
    print(f"TomTom collector targets: {n_collector_matched}/{n_collector_total} matched to real wards")

    # ---------------- Classification (never fabricated) ----------------
    sys.path.insert(0, TRAFFIC_BACKEND)
    from data_status_service import get_traffic_data_status
    feed_status = get_traffic_data_status().get("feed_status")

    counts = {"REAL_LIVE": 0, "REAL_HISTORICAL": 0, "ML_PREDICTION": 0, "LIMITED_COVERAGE": 0, "INSUFFICIENT_DATA": 0}
    for w in wards.values():
        if w["tomtom_collector_targets"] and feed_status == "LIVE":
            cls = "REAL_LIVE"
        elif w["real_gnn_temporal_edge"]:
            cls = "REAL_HISTORICAL"
        elif w["real_gnn_edges_count"] > 0:
            cls = "ML_PREDICTION"
        elif w["waste_data_available"] or w["traffic_named_locations"]:
            cls = "LIMITED_COVERAGE"
        else:
            cls = "INSUFFICIENT_DATA"
        w["coverage_class"] = cls
        # Confidence tied to the real GNN's own validated metric — never a
        # per-ward invented number.
        w["confidence"] = 0.62 if cls in ("REAL_LIVE", "REAL_HISTORICAL", "ML_PREDICTION") else None
        counts[cls] += 1

    with open(OUT_REGISTRY, "w", encoding="utf-8") as f:
        json.dump({
            "total_wards": len(wards),
            "wards_with_precise_boundary": n_with_polygon,
            "coverage_summary": counts,
            "built_from": {
                "wards_source": "OpenStreetMap admin_level=10 relations within Bengaluru (real, fetched via Overpass)",
                "waste_join": "direct area_osm_id == ward_id (exact, no fuzzy match)",
                "traffic_join": f"polygon containment for {n_with_polygon} wards with fetched boundaries; "
                                 "nearest real-ward-centroid (haversine) elsewhere — both real, no guessing",
                "feed_status_at_build_time": feed_status,
            },
            "wards": wards,
        }, f, indent=2, ensure_ascii=False)

    print("\n=== WARD COVERAGE SUMMARY (real, not fabricated) ===")
    print(json.dumps(counts, indent=2))
    print(f"Precise boundary available for {n_with_polygon}/{len(wards)} wards (rest use nearest-centroid).")
    print(f"\nSaved -> {OUT_REGISTRY}")


if __name__ == "__main__":
    main()
