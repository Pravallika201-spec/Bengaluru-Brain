"""
=========================================================
Urban Predictive Intelligence System
Land Use Intelligence Engine
=========================================================

Converts raw OpenStreetMap tags into standardized
urban land-use categories for the Waste Intelligence
Module.

No external API is used.
All processing is local.
=========================================================
"""

from pathlib import Path

import geopandas as gpd


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "osm"
    / "bengaluru_osm_multipolygons.gpkg"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_landuse.gpkg"
)


# ---------------------------------------------------------
# Classification function
# ---------------------------------------------------------

def classify_landuse(row):

    amenity = str(row.get("amenity", "")).lower()
    leisure = str(row.get("leisure", "")).lower()
    landuse = str(row.get("landuse", "")).lower()
    building = str(row.get("building", "")).lower()
    shop = str(row.get("shop", "")).lower()
    tourism = str(row.get("tourism", "")).lower()
    natural = str(row.get("natural", "")).lower()


    # -----------------------------------------------------
    # 1. Waste / Utility
    # -----------------------------------------------------

    if landuse in {
        "landfill",
        "garages"
    }:
        return "Waste_Utility"


    if amenity in {
        "recycling",
        "waste_basket",
        "waste_disposal",
        "waste_transfer_station"
    }:
        return "Waste_Utility"


    # -----------------------------------------------------
    # 2. Water
    # -----------------------------------------------------

    if landuse in {
        "basin",
        "reservoir"
    }:
        return "Water"


    if natural in {
        "water",
        "wetland"
    }:
        return "Water"


    # -----------------------------------------------------
    # 3. Religious
    # -----------------------------------------------------

    if landuse == "religious":
        return "Religious"


    if amenity in {
        "place_of_worship",
        "monastery"
    }:
        return "Religious"


    # -----------------------------------------------------
    # 4. Institutional / Education
    # -----------------------------------------------------

    if landuse in {
        "education",
        "college"
    }:
        return "Institutional"


    if amenity in {
        "school",
        "college",
        "university",
        "kindergarten",
        "hospital",
        "clinic",
        "police",
        "fire_station",
        "library",
        "public_building",
        "community_centre",
        "social_facility"
    }:
        return "Institutional"


    # -----------------------------------------------------
    # 5. Recreational
    # -----------------------------------------------------

    if leisure in {
        "park",
        "pitch",
        "swimming_pool",
        "garden",
        "playground",
        "sports_centre",
        "fitness_station",
        "track",
        "common",
        "fitness_centre",
        "stadium",
        "bleachers",
        "outdoor_seating",
        "resort",
        "sports_hall",
        "golf_course",
        "recreation_ground",
        "social_club",
        "miniature_golf",
        "bandstand",
        "schoolyard",
        "nature_reserve",
        "indoor_play",
        "dog_park",
        "dance",
        "horse_riding"
    }:
        return "Recreational"


    # -----------------------------------------------------
    # 6. Green Space
    # -----------------------------------------------------

    if landuse in {
        "forest",
        "grass",
        "meadow",
        "village_green",
        "flowerbed",
        "plant_nursery",
        "plantation"
    }:
        return "Green_Space"


    # -----------------------------------------------------
    # 7. Agricultural
    # -----------------------------------------------------

    if landuse in {
        "farmland",
        "farmyard",
        "orchard",
        "greenhouse_horticulture"
    }:
        return "Agricultural"


    # -----------------------------------------------------
    # 8. Industrial
    # -----------------------------------------------------

    if landuse in {
        "industrial",
        "quarry"
    }:
        return "Industrial"


    # -----------------------------------------------------
    # 9. Construction / Development
    # -----------------------------------------------------

    if landuse in {
        "construction",
        "brownfield",
        "greenfield"
    }:
        return "Construction"


    # -----------------------------------------------------
    # 10. Transport
    # -----------------------------------------------------

    if landuse in {
        "railway"
    }:
        return "Transport"


    if amenity in {
        "parking",
        "parking_space",
        "bus_station",
        "fuel",
        "motorcycle_parking"
    }:
        return "Transport"


    if building in {
        "transportation"
    }:
        return "Transport"


    # -----------------------------------------------------
    # 11. Commercial
    # -----------------------------------------------------

    if landuse in {
        "commercial",
        "retail"
    }:
        return "Commercial"


    if amenity in {
        "restaurant",
        "fast_food",
        "cafe",
        "marketplace",
        "bank",
        "cinema",
        "theatre",
        "events_venue"
    }:
        return "Commercial"


    if shop not in {
        "",
        "nan"
    }:
        return "Commercial"


    if tourism not in {
        "",
        "nan"
    }:
        return "Commercial"


    # -----------------------------------------------------
    # 12. Residential
    # -----------------------------------------------------

    if landuse == "residential":
        return "Residential"


    if building in {
        "apartments",
        "house",
        "residential",
        "detached",
        "semidetached_house",
        "terrace"
    }:
        return "Residential"


    # -----------------------------------------------------
    # 13. Military
    # -----------------------------------------------------

    if landuse == "military":
        return "Military"


    # -----------------------------------------------------
    # 14. Other
    # -----------------------------------------------------

    return "Other"


# ---------------------------------------------------------
# Main processing
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("BENGALURU LAND USE INTELLIGENCE ENGINE")
    print("=" * 60)

    print("\nLoading Bengaluru OSM data...")

    gdf = gpd.read_file(
        INPUT_FILE,
        layer="multipolygons"
    )

    print(
        f"Loaded {len(gdf):,} features."
    )

    print("\nClassifying land use...")

    gdf["landuse_class"] = gdf.apply(
        classify_landuse,
        axis=1
    )

    print("\nLand-use classification completed.")

    print("\nClassification summary:")
    print("-" * 40)

    print(
        gdf["landuse_class"]
        .value_counts()
    )

    print("\nSaving processed dataset...")

    gdf.to_file(
        OUTPUT_FILE,
        layer="landuse",
        driver="GPKG"
    )

    print("\nSaved successfully:")
    print(OUTPUT_FILE)

    print("\n" + "=" * 60)
    print("LAND USE ENGINE COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()