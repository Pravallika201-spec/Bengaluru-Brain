"""
Traces exactly where the 4 missing wards are falling out of the
pipeline: bengaluru_area_boundaries.gpkg -> bengaluru_grid_area_mapping.csv
-> bengaluru_area_overflow_predictions.gpkg

USAGE (run from waste_module/, with the venv active):
    python trace_missing_wards.py
"""

import os
import pandas as pd
import geopandas as gpd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

BOUNDARIES_FILE = os.path.join(PROCESSED_DIR, "bengaluru_area_boundaries.gpkg")
MAPPING_FILE = os.path.join(PROCESSED_DIR, "bengaluru_grid_area_mapping.csv")

CANDIDATES = [
    "Koramangala Hanumantha South",
    "Vijinapura",
    "Prakash Nagara",
    "K.P Agrahara",
]


def normalize(name):
    return " ".join(str(name).lower().replace(".", "").split())


def main():
    if not os.path.exists(BOUNDARIES_FILE):
        print(f"Boundaries file not found: {BOUNDARIES_FILE}")
        return
    if not os.path.exists(MAPPING_FILE):
        print(f"Mapping file not found: {MAPPING_FILE}")
        return

    boundaries = gpd.read_file(BOUNDARIES_FILE)
    mapping = pd.read_csv(MAPPING_FILE)

    print(f"Boundaries file has {len(boundaries):,} ward polygons.")
    print(f"Mapping file has {len(mapping):,} grid-to-area rows, "
          f"covering {mapping['area_name'].nunique():,} unique areas.\n")

    boundary_names_norm = {normalize(n): n for n in boundaries["name"]}
    mapping_names_norm = set(normalize(n) for n in mapping["area_name"].dropna())

    for candidate in CANDIDATES:
        norm = normalize(candidate)
        print("=" * 65)
        print(f"Checking: {candidate}")
        print("=" * 65)

        # Loose substring search in boundaries, in case of a naming variant
        loose_matches = [orig for norm_n, orig in boundary_names_norm.items()
                          if norm in norm_n or norm_n in norm]

        if not loose_matches:
            print("  NOT FOUND in bengaluru_area_boundaries.gpkg at all.")
            print("  -> This ward's polygon was never sourced. The gap is in")
            print("     whatever script builds bengaluru_area_boundaries.gpkg")
            print("     (likely an OSM query that's missing this ward's boundary).")
        else:
            for match in loose_matches:
                row = boundaries[boundaries["name"] == match].iloc[0]
                osm_id = row.get("osm_id", "?")
                admin_level = row.get("admin_level", "?")
                print(f"  FOUND in boundaries: name={match!r}, osm_id={osm_id}, admin_level={admin_level}")

                match_norm = normalize(match)
                grid_count = sum(1 for n in mapping["area_name"].dropna() if normalize(n) == match_norm)
                print(f"  Grid cells mapped to it in bengaluru_grid_area_mapping.csv: {grid_count}")
                if grid_count == 0:
                    print("  -> Polygon exists, but ZERO grid cells were ever assigned to it.")
                    print("     This is a grid-to-area mapping gap, not a missing boundary.")
                    print("     Likely cause: the ward is small enough that no 500m grid-cell")
                    print("     centroid/point falls inside its polygon during the spatial join.")
                else:
                    print("  -> Has grid cells AND a boundary — should have survived the merge.")
                    print("     If it's still missing from the final output, check for an")
                    print("     area_osm_id or area_admin_level type mismatch between the two files.")
        print()


if __name__ == "__main__":
    main()