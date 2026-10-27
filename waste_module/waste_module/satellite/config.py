from pathlib import Path


# =========================================================
# PROJECT PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SATELLITE_ROOT = (
    PROJECT_ROOT / "waste_module" / "satellite"
)

OUTPUT_DIR = SATELLITE_ROOT / "outputs"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# BENGALURU
# =========================================================

CITY_NAME = "Bengaluru"

CENTER_LAT = 12.9716
CENTER_LON = 77.5946


# =========================================================
# SENTINEL-2
# =========================================================

SENTINEL_COLLECTION = (
    "COPERNICUS/S2_SR_HARMONIZED"
)

MAX_CLOUD_PERCENT = 30


# =========================================================
# SENTINEL-2 BANDS
# =========================================================

BLUE_BAND = "B2"
GREEN_BAND = "B3"
RED_BAND = "B4"
NIR_BAND = "B8"

SWIR1_BAND = "B11"
SWIR2_BAND = "B12"


# =========================================================
# OUTPUT
# =========================================================

LATEST_IMAGE_INFO = (
    OUTPUT_DIR / "latest_satellite_image.txt"
)