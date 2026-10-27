import ee

from waste_module.satellite.config import (
    SENTINEL_COLLECTION,
    MAX_CLOUD_PERCENT,
    CENTER_LAT,
    CENTER_LON
)


# =========================================================
# EARTH ENGINE INITIALIZATION
# =========================================================

def initialize_earth_engine():
    """
    Initialize Google Earth Engine using the
    authenticated project configured earlier.
    """

    try:

        ee.Initialize()

        print(
            "Earth Engine initialized successfully."
        )

    except Exception as e:

        print(
            "Earth Engine initialization failed."
        )

        print(
            "Please make sure Earth Engine authentication "
            "and project configuration are complete."
        )

        raise e


# =========================================================
# BENGALURU REGION
# =========================================================

def get_bengaluru_region():
    """
    Create the Bengaluru study region.
    """

    point = ee.Geometry.Point(
        [
            CENTER_LON,
            CENTER_LAT
        ]
    )

    # Approximately 30 km around Bengaluru center

    region = point.buffer(
        30000
    )

    return region


# =========================================================
# GET LATEST SENTINEL-2 IMAGE
# =========================================================

def get_latest_image(region):
    """
    Retrieve the latest suitable Sentinel-2
    surface reflectance image.
    """

    collection = (
        ee.ImageCollection(
            SENTINEL_COLLECTION
        )
        .filterBounds(
            region
        )
        .filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                MAX_CLOUD_PERCENT
            )
        )
        .sort(
            "system:time_start",
            False
        )
    )

    image = ee.Image(
        collection.first()
    )

    return image


# =========================================================
# CALCULATE SPECTRAL FEATURES
# =========================================================

def calculate_indices(image):
    """
    Calculate satellite spectral indices.

    Sentinel-2 reflectance values are scaled by 10,000,
    so they are converted to reflectance before
    calculating the indices.
    """

    # -----------------------------------------------------
    # Convert Sentinel-2 reflectance
    # -----------------------------------------------------

    image = image.divide(
        10000
    )

    # -----------------------------------------------------
    # NDVI
    #
    # NDVI = (NIR - RED) / (NIR + RED)
    #
    # Useful for vegetation information.
    # -----------------------------------------------------

    ndvi = (
        image
        .normalizedDifference(
            [
                "B8",
                "B4"
            ]
        )
        .rename(
            "NDVI"
        )
    )

    # -----------------------------------------------------
    # NDBI
    #
    # NDBI = (SWIR - NIR) / (SWIR + NIR)
    #
    # Useful for built-up surface information.
    # -----------------------------------------------------

    ndbi = (
        image
        .normalizedDifference(
            [
                "B11",
                "B8"
            ]
        )
        .rename(
            "NDBI"
        )
    )

    # -----------------------------------------------------
    # NDWI
    #
    # NDWI = (GREEN - NIR) / (GREEN + NIR)
    #
    # Useful for water/moisture information.
    # -----------------------------------------------------

    ndwi = (
        image
        .normalizedDifference(
            [
                "B3",
                "B8"
            ]
        )
        .rename(
            "NDWI"
        )
    )

    # -----------------------------------------------------
    # Add indices to image
    # -----------------------------------------------------

    result = image.addBands(
        [
            ndvi,
            ndbi,
            ndwi
        ]
    )

    return result


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)

    print(
        "SENTINEL-2 SPECTRAL FEATURE ENGINE"
    )

    print("=" * 60)

    # -----------------------------------------------------
    # STEP 1
    # Initialize Earth Engine
    # -----------------------------------------------------

    initialize_earth_engine()

    # -----------------------------------------------------
    # STEP 2
    # Create Bengaluru region
    # -----------------------------------------------------

    print(
        "\nCreating Bengaluru study region..."
    )

    region = get_bengaluru_region()

    print(
        "Bengaluru study region created."
    )

    # -----------------------------------------------------
    # STEP 3
    # Find latest Sentinel-2 image
    # -----------------------------------------------------

    print(
        "\nSearching Sentinel-2 imagery..."
    )

    image = get_latest_image(
        region
    )

    # -----------------------------------------------------
    # STEP 4
    # Get image information
    # -----------------------------------------------------

    image_id = (
        image
        .id()
        .getInfo()
    )

    image_date = (
        ee.Date(
            image.get(
                "system:time_start"
            )
        )
        .format(
            "YYYY-MM-dd"
        )
        .getInfo()
    )

    cloud_percentage = (
        image
        .get(
            "CLOUDY_PIXEL_PERCENTAGE"
        )
        .getInfo()
    )

    print(
        "\nLatest suitable Sentinel-2 image:"
    )

    print(
        "Image ID:",
        image_id
    )

    print(
        "Image date:",
        image_date
    )

    print(
        "Cloud percentage:",
        cloud_percentage
    )

    # -----------------------------------------------------
    # STEP 5
    # Calculate spectral features
    # -----------------------------------------------------

    print(
        "\nCalculating satellite spectral features..."
    )

    feature_image = calculate_indices(
        image
    )

    # -----------------------------------------------------
    # STEP 6
    # Display features
    # -----------------------------------------------------

    print(
        "\nSatellite features created:"
    )

    print(
        "B2  - Blue reflectance"
    )

    print(
        "B3  - Green reflectance"
    )

    print(
        "B4  - Red reflectance"
    )

    print(
        "B8  - Near Infrared reflectance"
    )

    print(
        "B11 - SWIR1 reflectance"
    )

    print(
        "B12 - SWIR2 reflectance"
    )

    print(
        "NDVI - Vegetation index"
    )

    print(
        "NDBI - Built-up index"
    )

    print(
        "NDWI - Water/moisture index"
    )

    # -----------------------------------------------------
    # STEP 7
    # Verify the resulting bands
    # -----------------------------------------------------

    bands = (
        feature_image
        .bandNames()
        .getInfo()
    )

    print(
        "\nAvailable feature bands:"
    )

    for band in bands:

        print(
            " -",
            band
        )

    print(
        "\nSpectral feature generation successful."
    )


if __name__ == "__main__":

    main()