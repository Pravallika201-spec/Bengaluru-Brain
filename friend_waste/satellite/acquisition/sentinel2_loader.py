import ee

from waste_module.satellite.config import (
    SENTINEL_COLLECTION,
    MAX_CLOUD_PERCENT,
    CENTER_LAT,
    CENTER_LON
)


def initialize_earth_engine():

    try:
        ee.Initialize()

    except Exception:

        print(
            "Earth Engine is not initialized."
        )

        print(
            "Please run:"
        )

        print(
            "earthengine authenticate"
        )

        raise


def get_bengaluru_region():

    point = ee.Geometry.Point(
        [
            CENTER_LON,
            CENTER_LAT
        ]
    )

    # Approximately 30 km radius
    # around Bengaluru center

    region = point.buffer(
        30000
    )

    return region


def get_latest_sentinel_image():

    region = get_bengaluru_region()

    collection = (
        ee.ImageCollection(
            SENTINEL_COLLECTION
        )
        .filterBounds(region)
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


def main():

    print("=" * 60)

    print(
        "BENGALURU SATELLITE "
        "ACQUISITION ENGINE"
    )

    print("=" * 60)

    initialize_earth_engine()

    print(
        "\nSearching Sentinel-2 imagery..."
    )

    image = get_latest_sentinel_image()

    image_id = image.id().getInfo()

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

    cloud_percentage = image.get(
        "CLOUDY_PIXEL_PERCENTAGE"
    ).getInfo()

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

    print(
        "\nSatellite acquisition successful."
    )


if __name__ == "__main__":
    main()