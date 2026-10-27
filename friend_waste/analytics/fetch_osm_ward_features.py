"""
============================================================
WARD-LEVEL OSM FEATURE COLLECTOR
============================================================

Shared input for both alternative prediction models:
  - Option 1: per-capita generation model
  - Option 2: POI-density regression model

Pulls, for every ward in bengaluru_area_boundaries.gpkg:
  - residential_building_count  (proxy for population, via household size)
  - commercial_poi_count        (shops, restaurants, markets — proxy for
                                  commercial waste generation)
  - ward_area_km2

IMPORTANT DESIGN NOTE:
  Querying ALL buildings across the entire city in one single Overpass
  request is too large and will time out (this happened in testing — a
  180s timeout wasn't enough for a city Bengaluru's size). Instead, the
  city's bounding box is split into a grid of smaller tiles, each queried
  separately, and the results combined — bounded, reliable request sizes
  instead of one giant one. Still far fewer requests than querying each
  of the 369 wards individually, which would risk rate-limiting.

Input:
    bengaluru_area_boundaries.gpkg

Output:
    ward_osm_features.csv

Requires: osmnx, geopandas
    pip install osmnx --break-system-packages   (if not already installed)
============================================================
"""

import os
import time
import geopandas as gpd
import pandas as pd

try:
    import osmnx as ox
except ImportError:
    raise ImportError(
        "osmnx is required for this script. Install it with:\n"
        "    pip install osmnx --break-system-packages"
    )

# Give the Overpass server more time per request, and let osmnx handle
# rate-limit backoff automatically if the server asks us to slow down.
ox.settings.requests_timeout = 300
ox.settings.overpass_rate_limit = True

# ============================================================
# PATHS — same pattern as area_overflow_predictor.py
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

PROCESSED_DIR = os.path.join(BASE_DIR, "waste_module", "data", "processed")
AREA_FILE = os.path.join(PROCESSED_DIR, "bengaluru_area_boundaries.gpkg")
OUTPUT_FILE = os.path.join(PROCESSED_DIR, "ward_osm_features.csv")

# Residential building tags that count toward population estimation
RESIDENTIAL_BUILDING_TAGS = [
    "residential", "house", "apartments", "terrace",
    "semidetached_house", "detached", "bungalow", "dormitory"
]

# Commercial/retail tags that count toward commercial waste estimation
COMMERCIAL_AMENITY_TAGS = [
    "restaurant", "fast_food", "cafe", "marketplace",
    "bar", "pub", "food_court", "pharmacy", "bank", "clinic"
]


def load_ward_boundaries():
    print("\nLoading ward boundaries...")
    if not os.path.exists(AREA_FILE):
        raise FileNotFoundError(f"Ward boundaries not found:\n{AREA_FILE}")
    wards = gpd.read_file(AREA_FILE)
    print(f"Wards loaded: {len(wards):,}")
    if wards.crs is None:
        wards = wards.set_crs("EPSG:4326")
    return wards


# How many tiles to split the city into, per side (4 = a 4x4 grid = 16 tiles).
# Bengaluru is roughly 40km across, so a 4x4 grid gives ~10km tiles — small
# enough that each Overpass request reliably completes within the timeout.
GRID_SIZE = 4

# Seconds to wait between tile requests, being polite to the free Overpass API
REQUEST_DELAY_SECONDS = 2


def make_tiles(union_polygon, grid_size=GRID_SIZE):
    """Split the bounding box of the ward union into a grid_size x grid_size
    grid of (west, south, east, north) tuples."""
    west, south, east, north = union_polygon.bounds
    lon_step = (east - west) / grid_size
    lat_step = (north - south) / grid_size

    tiles = []
    for i in range(grid_size):
        for j in range(grid_size):
            tile_west = west + i * lon_step
            tile_east = west + (i + 1) * lon_step
            tile_south = south + j * lat_step
            tile_north = south + (j + 1) * lat_step
            tiles.append((tile_west, tile_south, tile_east, tile_north))
    return tiles


def _features_from_bbox(west, south, east, north, tags):
    """Call osmnx's bbox feature fetch, handling both the old (north, south,
    east, west) argument order used in osmnx <2.0 and the new bbox-tuple
    signature used in osmnx >=2.0."""
    try:
        # osmnx >= 2.0: single bbox tuple (left, bottom, right, top)
        return ox.features_from_bbox((west, south, east, north), tags=tags)
    except TypeError:
        pass
    try:
        # osmnx < 2.0: four separate positional args, north/south/east/west order
        return ox.features_from_bbox(north, south, east, west, tags=tags)
    except AttributeError:
        # Very old osmnx used a different function name entirely
        return ox.geometries_from_bbox(north, south, east, west, tags=tags)


def fetch_tiled(union_polygon, tags, label):
    """Query OSM tile by tile across the city's bounding box, instead of
    one request for the whole city at once (which times out)."""
    tiles = make_tiles(union_polygon)
    print(f"\nFetching {label} in {len(tiles)} tiles across the city...")

    all_results = []
    for idx, (west, south, east, north) in enumerate(tiles, start=1):
        print(f"  Tile {idx}/{len(tiles)}...", end=" ", flush=True)
        try:
            tile_result = _features_from_bbox(west, south, east, north, tags)
            print(f"{len(tile_result):,} found")
            if not tile_result.empty:
                all_results.append(tile_result)
        except Exception as e:
            # An empty tile (no matching features, e.g. over a lake or park)
            # raises an error in some osmnx versions rather than returning
            # empty — treat that as zero results and keep going, don't let
            # one bad tile kill the whole run.
            print(f"skipped ({type(e).__name__})")
        time.sleep(REQUEST_DELAY_SECONDS)

    if not all_results:
        print(f"  No {label} found in any tile.")
        return gpd.GeoDataFrame()

    combined = pd.concat(all_results, ignore_index=False)
    # Tiles can overlap slightly at edges — drop exact duplicate OSM elements
    combined = combined[~combined.index.duplicated(keep="first")]
    print(f"  Total {label} after combining tiles: {len(combined):,}")
    return combined


def fetch_buildings(union_polygon):
    return fetch_tiled(union_polygon, {"building": True}, "buildings")


def fetch_commercial_pois(union_polygon):
    tags = {
        "shop": True,
        "amenity": COMMERCIAL_AMENITY_TAGS,
    }
    return fetch_tiled(union_polygon, tags, "commercial POIs")


def classify_residential(buildings):
    """Keep only buildings tagged as residential-type."""
    if "building" not in buildings.columns:
        return buildings.iloc[0:0]
    mask = buildings["building"].astype(str).str.lower().isin(RESIDENTIAL_BUILDING_TAGS)
    return buildings[mask]


def classify_generic(buildings):
    """Buildings tagged generically ('yes'/'true'/'1') rather than with a
    specific type. A lot of OSM building data in India is tagged this way
    without further detail — used only as a fallback for wards where the
    strict residential filter found nothing at all."""
    if "building" not in buildings.columns:
        return buildings.iloc[0:0]
    mask = buildings["building"].astype(str).str.lower().isin(["yes", "true", "1"])
    return buildings[mask]


def count_per_ward(features, wards, count_col_name):
    """Spatially join point/polygon features to wards and count per ward."""
    ward_name_col = "area_name" if "area_name" in wards.columns else "name"

    if features.empty:
        result = wards[[ward_name_col]].rename(columns={ward_name_col: "area_name"}).copy()
        result[count_col_name] = 0
        return result

    # OSM buildings/POIs often carry their own "name" tag, which collides
    # with the ward's "name"/"area_name" column during the join — rename
    # the ward column to something unique BEFORE joining, same pattern
    # grid_area_mapper.py already uses for this exact reason.
    wards_for_join = wards[[ward_name_col, "geometry"]].rename(
        columns={ward_name_col: "_ward_name"})

    features = features.copy()
    # Reproject to a metric CRS before taking centroids — centroid math on
    # unprojected lat/lon coordinates is distorted (this is what the
    # "Geometry is in a geographic CRS" warning was flagging).
    if features.crs is None:
        features = features.set_crs(wards.crs, allow_override=True)
    original_crs = features.crs
    features = features.to_crs("EPSG:32643")
    features["geometry"] = features.geometry.centroid
    features = features.to_crs(wards_for_join.crs)

    joined = gpd.sjoin(features, wards_for_join, how="left", predicate="within")

    counts = joined.groupby("_ward_name").size().reset_index(name=count_col_name)
    counts = counts.rename(columns={"_ward_name": "area_name"})
    return counts


def compute_ward_area(wards):
    print("\nComputing ward areas...")
    metric = wards.to_crs("EPSG:32643")  # same metric CRS used elsewhere in this project
    name_col = "area_name" if "area_name" in wards.columns else "name"
    result = pd.DataFrame({
        "area_name": wards[name_col],
        "ward_area_km2": metric.geometry.area / 1_000_000,
    })
    return result


def main():
    print("=" * 70)
    print("WARD-LEVEL OSM FEATURE COLLECTOR")
    print("=" * 70)

    wards = load_ward_boundaries()

    union_polygon = wards.geometry.union_all() if hasattr(wards.geometry, "union_all") else wards.geometry.unary_union

    buildings = fetch_buildings(union_polygon)
    residential = classify_residential(buildings)
    print(f"Residential buildings (of all buildings fetched): {len(residential):,}")

    pois = fetch_commercial_pois(union_polygon)

    residential_counts = count_per_ward(residential, wards, "residential_building_count")
    poi_counts = count_per_ward(pois, wards, "commercial_poi_count")
    ward_areas = compute_ward_area(wards)

    # All three now consistently key on "area_name" — no more guessing
    # which name the source file happened to use.
    result = ward_areas.merge(residential_counts, on="area_name", how="left")
    result = result.merge(poi_counts, on="area_name", how="left")
    result["residential_building_count"] = result["residential_building_count"].fillna(0).astype(int)
    result["commercial_poi_count"] = result["commercial_poi_count"].fillna(0).astype(int)

    # Targeted fallback: for wards where the strict residential filter found
    # NOTHING, fall back to generically-tagged buildings ('building=yes') —
    # a lot of OSM building data in India is tagged this way without further
    # detail. Only applied to zero-count wards, so it doesn't inflate wards
    # that already have good, specific OSM data.
    zero_wards = result.loc[result["residential_building_count"] == 0, "area_name"].tolist()
    result["used_generic_building_fallback"] = False

    if zero_wards:
        print(f"\n{len(zero_wards)} ward(s) had zero strictly-tagged residential buildings — "
              f"applying generic-tag fallback for those specific wards only...")
        generic = classify_generic(buildings)
        generic_counts = count_per_ward(generic, wards, "generic_building_count")
        fallback = generic_counts[generic_counts["area_name"].isin(zero_wards)]

        result = result.merge(fallback, on="area_name", how="left")
        result["generic_building_count"] = result["generic_building_count"].fillna(0).astype(int)

        needs_fallback = result["area_name"].isin(zero_wards)
        result.loc[needs_fallback, "residential_building_count"] = result.loc[needs_fallback, "generic_building_count"]
        result.loc[needs_fallback, "used_generic_building_fallback"] = True
        result = result.drop(columns=["generic_building_count"])

        still_zero = (result["residential_building_count"] == 0).sum()
        print(f"After fallback: {still_zero} ward(s) still have zero residential buildings "
              f"(genuinely no building data of any kind in OSM for these).")

    result.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved to:\n{OUTPUT_FILE}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Wards processed: {len(result):,}")
    print(f"Wards with zero residential buildings found: {(result['residential_building_count'] == 0).sum():,}")
    print(f"Wards using the generic-tag fallback: {result['used_generic_building_fallback'].sum():,}")
    print(f"Wards with zero commercial POIs found: {(result['commercial_poi_count'] == 0).sum():,}")
    print("\nTop 10 wards by residential building count:")
    print(result.sort_values("residential_building_count", ascending=False)
          .head(10)[["area_name", "residential_building_count", "commercial_poi_count"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()