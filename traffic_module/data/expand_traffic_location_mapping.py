"""
Expands traffic_location_mapping.csv (the target list the real-time
collector, collect_live_traffic_history.py, polls) from 16 ad-hoc named
junctions to also include the 25 curated Bengaluru landmarks already used
elsewhere in the app (backend/location_data.py), snapped to their nearest
REAL OSM graph node from nodes.csv via haversine distance.

This does NOT fabricate any traffic data — it only widens the real set of
points the collector will poll once TOMTOM_API_KEY is configured and it is
run continuously. Existing rows are preserved untouched; only genuinely new
named locations (not already present, case-insensitively) are appended.
The original file is backed up to traffic_location_mapping.csv.bak first.

Run: python traffic_module/data/expand_traffic_location_mapping.py
"""
import os
import shutil
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(HERE, "traffic_location_mapping.csv")
NODES_FILE = os.path.join(HERE, "nodes.csv")
BACKEND_DIR = os.path.join(os.path.dirname(HERE), "backend")

sys.path.insert(0, BACKEND_DIR)
from location_data import BENGALURU_LOCATIONS  # noqa: E402

MAX_SNAP_DISTANCE_M = 300.0  # don't snap to a node further than this — report CHECK_MANUALLY instead


def haversine_m(lat1, lon1, lat2_arr, lon2_arr):
    r = 6371000.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2_arr)
    dphi = np.radians(lat2_arr - lat1)
    dlmb = np.radians(lon2_arr - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def main():
    existing = pd.read_csv(MAPPING_FILE)
    existing_names = set(existing["traffic_location"].str.lower().str.strip())

    nodes = pd.read_csv(NODES_FILE)
    node_lat = nodes["y"].to_numpy()
    node_lon = nodes["x"].to_numpy()
    node_ids = nodes["node_id"].to_numpy()

    new_rows = []
    for name, info in BENGALURU_LOCATIONS.items():
        if name.lower().strip() in existing_names:
            continue
        dists = haversine_m(info["lat"], info["lon"], node_lat, node_lon)
        nearest_idx = int(np.argmin(dists))
        nearest_dist = float(dists[nearest_idx])
        status = "MATCHED" if nearest_dist <= MAX_SNAP_DISTANCE_M else "CHECK_MANUALLY"
        new_rows.append({
            "traffic_location": name,
            "latitude": info["lat"],
            "longitude": info["lon"],
            "nearest_node": float(node_ids[nearest_idx]),
            "distance_m": nearest_dist,
            "status": status,
        })

    if not new_rows:
        print("No new locations to add — mapping file already covers all curated locations.")
        return

    shutil.copy2(MAPPING_FILE, MAPPING_FILE + ".bak")
    combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    combined.to_csv(MAPPING_FILE, index=False)

    print(f"Backed up original -> {MAPPING_FILE}.bak")
    print(f"Added {len(new_rows)} new locations (of {len(BENGALURU_LOCATIONS)} curated landmarks checked):")
    for row in new_rows:
        print(f"  {row['traffic_location']:25s} -> node {row['nearest_node']:.0f}, "
              f"{row['distance_m']:.1f}m away, {row['status']}")
    print(f"\nTotal mapping rows now: {len(combined)} "
          f"({(combined['status'] == 'MATCHED').sum()} MATCHED)")


if __name__ == "__main__":
    main()
