"""
Quick manual check: search your own area_name list for anything
resembling the 4 wards flagged as missing, using loose keyword
matching instead of the stricter fuzzy cutoff.

USAGE:
    python check_candidates.py data\\processed\\bengaluru_area_overflow_predictions.gpkg
"""

import sys
import geopandas as gpd

KEYWORDS = {
    "Koramangala Hanumantha South": ["koramangala", "hanumantha"],
    "Vijinapura": ["vijinapura", "vijaynapura", "vijaya pura"],
    "Prakash Nagara": ["prakash"],
    "K.P Agrahara": ["agrahara", "k p", "kp agrahara"],
}

path = sys.argv[1]
try:
    gdf = gpd.read_file(path, layer="area_overflow_predictions")
except Exception:
    gdf = gpd.read_file(path)

names = gdf["area_name"].dropna().astype(str).tolist()

for official, keywords in KEYWORDS.items():
    print(f"\n{'='*60}\nSearching for near-matches of: {official}\n{'='*60}")
    matches = [n for n in names if any(kw.lower() in n.lower() for kw in keywords)]
    if matches:
        for m in matches:
            print(f"  found: {m!r}")
    else:
        print("  No near-matches at all — likely a genuine gap.")