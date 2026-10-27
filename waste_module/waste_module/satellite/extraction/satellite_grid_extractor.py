import ee
import geopandas as gpd
import pandas as pd
import os
import json
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

GRID_PATH = "waste_module/data/bengaluru_grid.geojson"

OUTPUT_DIR = "waste_module/satellite/outputs"

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_features.csv"
)

METADATA_FILE = (
    "waste_module/satellite/outputs/"
    "satellite_metadata.json"
)

SENTINEL_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# ------------------------------------------------------------
# Satellite selection
# ------------------------------------------------------------

# Use a larger temporal window to improve spatial coverage.
COMPOSITE_DAYS = 60

# Keep reasonably clean scenes.
MAX_CLOUD_PERCENT = 50

# Minimum valid pixels required for a grid cell.
MIN_VALID_PIXELS = 5


# ============================================================
# EARTH ENGINE INITIALIZATION
# ============================================================

def initialize_earth_engine():

    print("\nInitializing Google Earth Engine...")

    try:

        ee.Initialize()

        print(
            "Earth Engine initialized successfully."
        )

    except Exception as e:

        print(
            "\nEarth Engine initialization failed."
        )

        print(
            "Run Earth Engine authentication first."
        )

        raise e


# ============================================================
# LOAD GRID
# ============================================================

def load_grid():

    print("\nLoading Bengaluru grid...")

    grid = gpd.read_file(GRID_PATH)

    print(
        "Grid cells:",
        len(grid)
    )

    print(
        "Grid CRS:",
        grid.crs
    )

    if grid.crs is None:

        raise ValueError(
            "Grid CRS is missing."
        )

    # Earth Engine requires WGS84.
    grid = grid.to_crs("EPSG:4326")

    grid = grid[
        [
            "Grid_ID",
            "geometry"
        ]
    ].copy()

    return grid


# ============================================================
# CONVERT GEOPANDAS TO EARTH ENGINE
# ============================================================

def geopandas_to_ee(grid):

    print(
        "\nConverting Bengaluru grid "
        "to Earth Engine features..."
    )

    features = []

    for _, row in grid.iterrows():

        geometry = row.geometry

        if geometry is None:
            continue

        if geometry.is_empty:
            continue

        ee_geometry = ee.Geometry(
            geometry.__geo_interface__
        )

        feature = ee.Feature(
            ee_geometry,
            {
                "Grid_ID": str(
                    row["Grid_ID"]
                )
            }
        )

        features.append(feature)

    collection = ee.FeatureCollection(
        features
    )

    print(
        "Earth Engine grid features:",
        len(features)
    )

    return collection


# ============================================================
# SENTINEL-2 CLOUD / SHADOW MASK
# ============================================================

def mask_sentinel2(image):

    scl = image.select("SCL")

    # Keep only reliable surface classes:
    #
    # 4 = Vegetation
    # 5 = Bare soil
    # 6 = Water
    # 7 = Unclassified
    #
    # Remove:
    # 3  Cloud shadow
    # 8  Cloud medium probability
    # 9  Cloud high probability
    # 10 Thin cirrus
    # 11 Snow / ice
    #
    # This conservative mask avoids using known
    # cloud/shadow contaminated pixels.

    mask = (
        scl.eq(4)
        .Or(scl.eq(5))
        .Or(scl.eq(6))
        .Or(scl.eq(7))
    )

    return (
        image
        .updateMask(mask)
        .divide(10000)
        .copyProperties(
            image,
            image.propertyNames()
        )
    )


# ============================================================
# GET RECENT SENTINEL COMPOSITE
# ============================================================

def get_latest_sentinel_mosaic(region):

    print(
        "\nSearching Sentinel-2 imagery..."
    )

    # --------------------------------------------------------
    # Find latest suitable image
    # --------------------------------------------------------

    collection = (
        ee.ImageCollection(
            SENTINEL_COLLECTION
        )
        .filterBounds(region)
        .filter(
            ee.Filter.lte(
                "CLOUDY_PIXEL_PERCENTAGE",
                MAX_CLOUD_PERCENT
            )
        )
        .sort(
            "system:time_start",
            False
        )
    )

    image_count = (
        collection
        .size()
        .getInfo()
    )

    print(
        "Suitable Sentinel-2 images found:",
        image_count
    )

    if image_count == 0:

        raise RuntimeError(
            "No Sentinel-2 imagery found."
        )

    # --------------------------------------------------------
    # Latest image
    # --------------------------------------------------------

    latest_image = ee.Image(
        collection.first()
    )

    latest_date = (
        ee.Date(
            latest_image.get(
                "system:time_start"
            )
        )
        .format(
            "YYYY-MM-dd"
        )
        .getInfo()
    )

    latest_image_id = (
        latest_image
        .id()
        .getInfo()
    )

    latest_cloud = (
        latest_image
        .get(
            "CLOUDY_PIXEL_PERCENTAGE"
        )
        .getInfo()
    )

    # --------------------------------------------------------
    # Composite date window
    # --------------------------------------------------------

    latest_date_ee = ee.Date(
        latest_date
    )

    start_date = (
        latest_date_ee
        .advance(
            -COMPOSITE_DAYS,
            "day"
        )
    )

    end_date = (
        latest_date_ee
        .advance(
            1,
            "day"
        )
    )

    # --------------------------------------------------------
    # Recent collection
    # --------------------------------------------------------

    recent_collection = (
        ee.ImageCollection(
            SENTINEL_COLLECTION
        )
        .filterBounds(region)
        .filterDate(
            start_date,
            end_date
        )
        .filter(
            ee.Filter.lte(
                "CLOUDY_PIXEL_PERCENTAGE",
                MAX_CLOUD_PERCENT
            )
        )
    )

    recent_count = (
        recent_collection
        .size()
        .getInfo()
    )

    print(
        "\nRecent Sentinel-2 window:",
        COMPOSITE_DAYS,
        "days"
    )

    print(
        "Cloud threshold:",
        MAX_CLOUD_PERCENT,
        "%"
    )

    print(
        "Images found:",
        recent_count
    )

    if recent_count == 0:

        raise RuntimeError(
            "No usable recent Sentinel-2 images."
        )

    # --------------------------------------------------------
    # Apply pixel-level masking
    # --------------------------------------------------------

    masked_collection = (
        recent_collection
        .map(
            mask_sentinel2
        )
    )

    # --------------------------------------------------------
    # Median composite
    # --------------------------------------------------------

    composite = (
        masked_collection
        .median()
        .clip(region)
    )

    # --------------------------------------------------------
    # Oldest image
    # --------------------------------------------------------

    oldest_image = ee.Image(
        recent_collection.sort(
            "system:time_start",
            True
        ).first()
    )

    oldest_date = (
        ee.Date(
            oldest_image.get(
                "system:time_start"
            )
        )
        .format(
            "YYYY-MM-dd"
        )
        .getInfo()
    )

    # --------------------------------------------------------
    # Image IDs used in composite
    # --------------------------------------------------------

    image_info = (
        recent_collection
        .aggregate_array("system:index")
        .getInfo()
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {

        "latest_image_id":
            latest_image_id,

        "latest_image_date":
            latest_date,

        "oldest_image_date":
            oldest_date,

        "latest_cloud_percentage":
            latest_cloud,

        "images_in_collection":
            image_count,

        "images_used_in_composite":
            recent_count,

        "composite_period_days":
            COMPOSITE_DAYS,

        "maximum_scene_cloud_percentage":
            MAX_CLOUD_PERCENT,

        "composite_method":
            "pixel_median",

        "pixel_mask":
            "SCL classes 4,5,6,7",

        "sentinel_collection":
            SENTINEL_COLLECTION,

        "resolution_meters":
            10,

        "image_indices_used":
            image_info
    }

    print(
        "\nSatellite composite created."
    )

    print(
        "Latest observation:",
        latest_date
    )

    print(
        "Oldest observation:",
        oldest_date
    )

    print(
        "Images used:",
        recent_count
    )

    print(
        "Composite method:",
        "pixel median"
    )

    return composite, metadata


# ============================================================
# CALCULATE SPECTRAL FEATURES
# ============================================================

def calculate_features(image):

    print(
        "\nCalculating spectral features..."
    )

    blue = image.select(
        "B2"
    ).rename("B2")

    green = image.select(
        "B3"
    ).rename("B3")

    red = image.select(
        "B4"
    ).rename("B4")

    nir = image.select(
        "B8"
    ).rename("B8")

    swir1 = image.select(
        "B11"
    ).rename("B11")

    swir2 = image.select(
        "B12"
    ).rename("B12")

    ndvi = (
        image
        .normalizedDifference(
            ["B8", "B4"]
        )
        .rename("NDVI")
    )

    ndbi = (
        image
        .normalizedDifference(
            ["B11", "B8"]
        )
        .rename("NDBI")
    )

    ndwi = (
        image
        .normalizedDifference(
            ["B3", "B8"]
        )
        .rename("NDWI")
    )

    feature_image = (
        blue
        .addBands(green)
        .addBands(red)
        .addBands(nir)
        .addBands(swir1)
        .addBands(swir2)
        .addBands(ndvi)
        .addBands(ndbi)
        .addBands(ndwi)
    )

    return feature_image


# ============================================================
# EXTRACT GRID FEATURES
# ============================================================

def extract_grid_features(
    feature_image,
    ee_grid
):

    print(
        "\nExtracting satellite features "
        "for every Bengaluru grid cell..."
    )

    bands = [
        "B2",
        "B3",
        "B4",
        "B8",
        "B11",
        "B12",
        "NDVI",
        "NDBI",
        "NDWI"
    ]

    # --------------------------------------------------------
    # Mean spectral values
    # --------------------------------------------------------

    mean_result = (
        feature_image
        .select(bands)
        .reduceRegions(
            collection=ee_grid,
            reducer=ee.Reducer.mean(),
            scale=10,
            tileScale=8
        )
    )

    # --------------------------------------------------------
    # Count valid pixels
    # --------------------------------------------------------

    count_result = (
        feature_image
        .select("B2")
        .reduceRegions(
            collection=ee_grid,
            reducer=ee.Reducer.count(),
            scale=10,
            tileScale=8
        )
    )

    # --------------------------------------------------------
    # Join results
    # --------------------------------------------------------

    joined = ee.Join.inner().apply(
        mean_result,
        count_result,
        ee.Filter.equals(
            leftField="Grid_ID",
            rightField="Grid_ID"
        )
    )

    def merge_features(pair):

        left = ee.Feature(
            pair.get("primary")
        )

        right = ee.Feature(
            pair.get("secondary")
        )

        valid_count = right.get(
            "count"
        )

        return (
            left
            .set(
                "valid_pixel_count",
                valid_count
            )
            .setGeometry(None)
        )

    result = joined.map(
        merge_features
    )

    return ee.FeatureCollection(
        result
    )


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(
    result,
    metadata
):

    print(
        "\nDownloading satellite grid results..."
    )

    data = result.getInfo()

    rows = []

    for feature in data["features"]:

        properties = feature.get(
            "properties",
            {}
        )

        properties.pop(
            "geometry",
            None
        )

        properties.pop(
            "count_feature",
            None
        )

        properties.pop(
            "id",
            None
        )

        rows.append(properties)

    output = pd.DataFrame(
        rows
    )

    if "Grid_ID" not in output.columns:

        raise RuntimeError(
            "Grid_ID missing from results."
        )

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    expected_columns = [
        "Grid_ID",
        "B2",
        "B3",
        "B4",
        "B8",
        "B11",
        "B12",
        "NDVI",
        "NDBI",
        "NDWI",
        "valid_pixel_count"
    ]

    for column in expected_columns:

        if column not in output.columns:

            output[column] = pd.NA

    # --------------------------------------------------------
    # Numeric conversion
    # --------------------------------------------------------

    numeric_columns = [
        "B2",
        "B3",
        "B4",
        "B8",
        "B11",
        "B12",
        "NDVI",
        "NDBI",
        "NDWI",
        "valid_pixel_count"
    ]

    for column in numeric_columns:

        output[column] = pd.to_numeric(
            output[column],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Satellite validity
    # --------------------------------------------------------

    output["Satellite_Valid"] = (
        output["valid_pixel_count"]
        .fillna(0)
        >= MIN_VALID_PIXELS
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    output = (
        output
        .sort_values("Grid_ID")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Reorder
    # --------------------------------------------------------

    output = output[
        [
            "Grid_ID",
            "valid_pixel_count",
            "B11",
            "B12",
            "B2",
            "B3",
            "B4",
            "B8",
            "NDBI",
            "NDVI",
            "NDWI",
            "Satellite_Valid"
        ]
    ]

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    output.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # --------------------------------------------------------
    # Coverage statistics
    # --------------------------------------------------------

    valid_count = int(
        output["Satellite_Valid"].sum()
    )

    missing_count = int(
        len(output) - valid_count
    )

    zero_pixel_count = int(
        (
            output["valid_pixel_count"]
            == 0
        ).sum()
    )

    coverage = (
        valid_count /
        len(output) *
        100
    )

    metadata[
        "extraction_timestamp"
    ] = datetime.now().isoformat()

    metadata[
        "output_rows"
    ] = len(output)

    metadata[
        "valid_satellite_rows"
    ] = valid_count

    metadata[
        "missing_satellite_rows"
    ] = missing_count

    metadata[
        "zero_pixel_rows"
    ] = zero_pixel_count

    metadata[
        "satellite_coverage_percent"
    ] = round(
        coverage,
        2
    )

    metadata[
        "minimum_valid_pixels"
    ] = MIN_VALID_PIXELS

    metadata[
        "valid_pixel_count_mean"
    ] = round(
        float(
            output[
                "valid_pixel_count"
            ].mean()
        ),
        2
    )

    metadata[
        "valid_pixel_count_median"
    ] = round(
        float(
            output[
                "valid_pixel_count"
            ].median()
        ),
        2
    )

    # --------------------------------------------------------
    # Save metadata
    # --------------------------------------------------------

    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            indent=4
        )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print(
        "\nSatellite feature dataset saved:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\nRows:",
        len(output)
    )

    print(
        "Valid satellite rows:",
        valid_count
    )

    print(
        "Missing satellite rows:",
        missing_count
    )

    print(
        "Zero-pixel rows:",
        zero_pixel_count
    )

    print(
        "Satellite coverage:",
        round(
            coverage,
            2
        ),
        "%"
    )

    print(
        "Mean valid pixels:",
        round(
            output[
                "valid_pixel_count"
            ].mean(),
            2
        )
    )

    print(
        "Median valid pixels:",
        round(
            output[
                "valid_pixel_count"
            ].median(),
            2
        )
    )

    print(
        "\nFirst 10 valid grid cells:"
    )

    valid = output[
        output["Satellite_Valid"]
    ]

    print(
        valid
        .head(10)
        .to_string(
            index=False
        )
    )

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "BENGALURU SATELLITE GRID "
        "FEATURE EXTRACTION ENGINE"
    )

    print("=" * 70)

    # 1
    initialize_earth_engine()

    # 2
    grid = load_grid()

    # 3
    ee_grid = geopandas_to_ee(
        grid
    )

    # 4
    print(
        "\nCreating Bengaluru study region..."
    )

    region = ee_grid.geometry()

    print(
        "Bengaluru study region created."
    )

    # 5
    satellite_image, metadata = (
        get_latest_sentinel_mosaic(
            region
        )
    )

    # 6
    print(
        "\nSelected satellite observation:"
    )

    print(
        "Latest image ID:",
        metadata[
            "latest_image_id"
        ]
    )

    print(
        "Latest image date:",
        metadata[
            "latest_image_date"
        ]
    )

    print(
        "Oldest image date:",
        metadata[
            "oldest_image_date"
        ]
    )

    print(
        "Latest cloud percentage:",
        metadata[
            "latest_cloud_percentage"
        ]
    )

    print(
        "Images used:",
        metadata[
            "images_used_in_composite"
        ]
    )

    print(
        "Composite window:",
        metadata[
            "composite_period_days"
        ],
        "days"
    )

    # 7
    feature_image = calculate_features(
        satellite_image
    )

    print(
        "\nSatellite features:"
    )

    print("B2  - Blue")
    print("B3  - Green")
    print("B4  - Red")
    print("B8  - Near Infrared")
    print("B11 - SWIR1")
    print("B12 - SWIR2")
    print("NDVI - Vegetation")
    print("NDBI - Built-up")
    print("NDWI - Water/Moisture")

    # 8
    result = extract_grid_features(
        feature_image,
        ee_grid
    )

    # 9
    output = save_results(
        result,
        metadata
    )

    # 10
    print(
        "\n"
        + "=" * 70
    )

    print(
        "SATELLITE GRID EXTRACTION COMPLETED"
    )

    print(
        "=" * 70
    )

    print(
        "\nTotal grid cells processed:",
        len(output)
    )

    print(
        "Valid satellite cells:",
        int(
            output[
                "Satellite_Valid"
            ].sum()
        )
    )

    print(
        "Missing satellite cells:",
        int(
            (
                ~output[
                    "Satellite_Valid"
                ]
            ).sum()
        )
    )

    print(
        "Satellite coverage:",
        round(
            output[
                "Satellite_Valid"
            ].mean() * 100,
            2
        ),
        "%"
    )

    print(
        "\nMetadata saved:"
    )

    print(
        METADATA_FILE
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()