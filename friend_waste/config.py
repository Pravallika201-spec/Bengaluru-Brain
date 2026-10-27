"""
=========================================================
Urban Predictive Intelligence System (UPIS)
GeoAI Waste Intelligence Engine
Configuration File
=========================================================
"""

from pathlib import Path

# =========================================================
# Project Information
# =========================================================

PROJECT_NAME = "Urban Predictive Intelligence System"
MODULE_NAME = "GeoAI Waste Intelligence Engine"

CITY = "Bengaluru"
STATE = "Karnataka"
COUNTRY = "India"

# =========================================================
# Directories
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
GIS_DIR = BASE_DIR / "gis"
MAPS_DIR = BASE_DIR / "maps"
MODELS_DIR = BASE_DIR / "models"
OUTPUT_DIR = BASE_DIR / "outputs"

# =========================================================
# GIS
# =========================================================

GRID_SIZE_METERS = 500

BOUNDARY_FILE = DATA_DIR / "bengaluru_boundary.geojson"

GRID_GEOJSON = DATA_DIR / "bengaluru_grid.geojson"

GRID_CSV = DATA_DIR / "bengaluru_grid.csv"

GRID_MAP = MAPS_DIR / "bengaluru_grid.html"

# Coordinate Reference Systems
WGS84 = "EPSG:4326"
PROJECTED_CRS = "EPSG:32643"      # UTM Zone 43N (covers Bengaluru)

# =========================================================
# Random Seed
# =========================================================

RANDOM_STATE = 42
# =========================================================
# Land Use
# =========================================================


LANDUSE_OUTPUT = DATA_DIR / "urban_mesh_landuse.csv"

LANDUSE_TAGS = [
    "residential",
    "commercial",
    "industrial",
    "retail",
    "park",
    "grass",
    "forest",
    "cemetery",
    "education",
    "hospital",
    "construction",
]