"""
============================================================
FIND MISSING BENGALURU WARDS
============================================================

Compares the area_name values in your area boundary file
against the official 369-ward GBA reference list, and prints
exactly which wards are missing or only fuzzy-matched (so you
can tell a genuine gap apart from a naming/spelling mismatch).

USAGE:
    python find_missing_wards.py /path/to/bengaluru_area_overflow_predictions.gpkg

    If your file isn't a .gpkg (e.g. it's a .csv/.shp with an
    area_name column), pass that path instead — the loader below
    tries geopandas first, then falls back to pandas for CSV.

Requires: pandas, geopandas (only if reading .gpkg/.shp),
          bengaluru_369_wards_reference.csv in the same folder.
============================================================
"""

import sys
import os
import difflib
import pandas as pd

REFERENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "bengaluru_369_wards_reference.csv")

FUZZY_CUTOFF = 0.82  # similarity threshold (0-1); lower = more lenient matching


def load_area_names(path):
    """Load area_name values from a .gpkg, .shp, or .csv file."""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".gpkg", ".shp", ".geojson"):
        import geopandas as gpd
        if ext == ".gpkg":
            # Try the layer name used elsewhere in this project first;
            # fall back to whatever the first/only layer is.
            try:
                gdf = gpd.read_file(path, layer="area_overflow_predictions")
            except Exception:
                gdf = gpd.read_file(path)
        else:
            gdf = gpd.read_file(path)
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
    else:
        df = pd.read_csv(path)

    area_col = next((c for c in df.columns if c.lower() in
                      ("area_name", "area", "ward_name", "ward")), None)
    if area_col is None:
        raise ValueError(
            f"Couldn't find an area/ward name column. Columns found: {list(df.columns)}"
        )

    return sorted(df[area_col].dropna().astype(str).str.strip().unique().tolist())


def normalize(name):
    """Loosen comparison: lowercase, strip 'ward' suffix, collapse punctuation/spaces."""
    n = name.lower()
    n = n.replace(".", "").replace("-", " ")
    n = n.replace(" ward", "").strip()
    n = " ".join(n.split())
    return n


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_missing_wards.py /path/to/your_area_file")
        sys.exit(1)

    your_file = sys.argv[1]

    if not os.path.exists(REFERENCE_FILE):
        print(f"Reference file not found next to this script: {REFERENCE_FILE}")
        sys.exit(1)

    reference = pd.read_csv(REFERENCE_FILE)
    official_names = reference["ward_name"].tolist()
    official_normalized = {normalize(n): n for n in official_names}

    your_names = load_area_names(your_file)
    your_normalized = {normalize(n) for n in your_names}

    print(f"Your file has {len(your_names)} unique area names.")
    print(f"Official reference has {len(official_names)} wards.")
    print(f"Difference: {len(official_names) - len(your_names)}\n")

    missing = []
    fuzzy_matched = []

    for norm_official, original_official in official_normalized.items():
        if norm_official in your_normalized:
            continue  # exact match after normalization

        close = difflib.get_close_matches(norm_official, your_normalized, n=1, cutoff=FUZZY_CUTOFF)
        if close:
            fuzzy_matched.append((original_official, close[0]))
        else:
            missing.append(original_official)

    print("=" * 60)
    print(f"GENUINELY MISSING WARDS ({len(missing)}):")
    print("=" * 60)
    if missing:
        row = reference[reference["ward_name"].isin(missing)]
        print(row[["ward_name", "assembly_constituency", "city_corporation"]]
              .to_string(index=False))
    else:
        print("None — every official ward has at least a fuzzy match in your data.")

    if fuzzy_matched:
        print("\n" + "=" * 60)
        print(f"LIKELY NAMING MISMATCHES ({len(fuzzy_matched)}) — check these aren't false gaps:")
        print("=" * 60)
        for official, yours in fuzzy_matched:
            print(f"  official: {official!r}  <->  yours: {yours!r}")

    print("\nTip: if 'genuinely missing' comes back empty but your total count is still off,")
    print("the gap is likely duplicate area_name values in your file collapsing two wards")
    print("into one row, or two official wards sharing the same name in different")
    print("corporations (e.g. 'Bilekahalli' appears twice in the official list).")


if __name__ == "__main__":
    main()