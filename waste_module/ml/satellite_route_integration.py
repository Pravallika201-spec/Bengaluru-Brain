import os
import pandas as pd
import numpy as np


# ============================================================
# FILE PATHS
# ============================================================

SATELLITE_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_production_waste_predictions.csv"
)

OLD_ROUTE_FILE = (
    "waste_module/data/processed/"
    "bengaluru_collection_routes.csv"
)

OUTPUT_FILE = (
    "waste_module/satellite/outputs/"
    "bengaluru_satellite_dynamic_routes.csv"
)


# ============================================================
# PRIORITY CONVERSION
# ============================================================

PRIORITY_MAP = {
    "CRITICAL": "P2 - Urgent",
    "HIGH": "P3 - High",
    "MEDIUM": "P4 - Normal",
    "LOW": "P5 - Low"
}


# ============================================================
# LOAD SATELLITE PREDICTIONS
# ============================================================

def load_satellite_predictions():

    print("\nLoading satellite predictions...")

    if not os.path.exists(SATELLITE_FILE):

        raise FileNotFoundError(
            f"\nSatellite prediction file not found:\n"
            f"{SATELLITE_FILE}"
        )

    df = pd.read_csv(
        SATELLITE_FILE
    )

    print(
        "Satellite prediction rows:",
        len(df)
    )

    required_columns = [
        "Grid_ID",
        "predicted_daily_waste_kg",
        "waste_risk",
        "collection_priority"
    ]

    missing = [
        c for c in required_columns
        if c not in df.columns
    ]

    if missing:

        raise ValueError(
            f"Missing satellite columns: {missing}"
        )

    return df


# ============================================================
# LOAD EXISTING ROUTES
# ============================================================

def load_existing_routes():

    print("\nLoading existing route data...")

    # Your existing route data is a GPKG.
    # We use geopandas here.

    import geopandas as gpd

    gpkg = (
        "waste_module/data/processed/"
        "bengaluru_collection_routes.gpkg"
    )

    if not os.path.exists(gpkg):

        raise FileNotFoundError(
            f"\nExisting route file not found:\n{gpkg}"
        )

    routes = gpd.read_file(
        gpkg,
        layer="collection_routes"
    )

    print(
        "Existing route rows:",
        len(routes)
    )

    return routes


# ============================================================
# MERGE SATELLITE DATA WITH ROUTES
# ============================================================

def merge_predictions(
    routes,
    satellite
):

    print(
        "\nMatching satellite predictions "
        "with existing routes..."
    )

    # Remove duplicate Grid_ID values if any.

    satellite = satellite.drop_duplicates(
        subset="Grid_ID"
    )

    merged = routes.merge(
        satellite[
            [
                "Grid_ID",
                "Latitude",
                "Longitude",
                "predicted_daily_waste_kg",
                "waste_risk",
                "collection_priority"
            ]
        ],
        on="Grid_ID",
        how="left",
        suffixes=(
            "_old",
            "_satellite"
        )
    )

    matched = merged[
        "predicted_daily_waste_kg_satellite"
    ].notna().sum()

    print(
        "Matched route grids:",
        matched
    )

    print(
        "Unmatched route grids:",
        len(merged) - matched
    )

    return merged


# ============================================================
# UPDATE ROUTING PRIORITY
# ============================================================

def update_priority(
    df
):

    print(
        "\nUpdating routing priorities..."
    )

    df[
        "satellite_collection_priority"
    ] = df[
        "waste_risk"
    ].map(
        PRIORITY_MAP
    )

    # Use satellite-derived priority
    # wherever a prediction exists.

    mask = df[
        "satellite_collection_priority"
    ].notna()

    df.loc[
        mask,
        "collection_priority"
    ] = df.loc[
        mask,
        "satellite_collection_priority"
    ]

    return df


# ============================================================
# UPDATE WASTE VALUES
# ============================================================

def update_waste_values(
    df
):

    print(
        "\nUpdating predicted waste values..."
    )

    mask = df[
        "predicted_daily_waste_kg_satellite"
    ].notna()

    df.loc[
        mask,
        "old_predicted_daily_waste_kg"
    ] = df.loc[
        mask,
        "predicted_daily_waste_kg_old"
    ]

    df.loc[
        mask,
        "predicted_daily_waste_kg"
    ] = df.loc[
        mask,
        "predicted_daily_waste_kg_satellite"
    ]

    return df


# ============================================================
# REORDER ROUTES
# ============================================================

def reorder_routes(
    df
):

    print(
        "\nReordering routes using "
        "satellite priority..."
    )

    priority_order = {
        "P2 - Urgent": 1,
        "P3 - High": 2,
        "P4 - Normal": 3,
        "P5 - Low": 4
    }

    df[
        "_priority_order"
    ] = df[
        "collection_priority"
    ].map(
        priority_order
    ).fillna(99)

    df = df.sort_values(
        by=[
            "_priority_order",
            "predicted_daily_waste_kg"
        ],
        ascending=[
            True,
            False
        ]
    )

    # Recalculate route sequence
    # separately for each truck.

    if "truck_id" in df.columns:

        df[
            "route_sequence"
        ] = (
            df.groupby(
                "truck_id"
            ).cumcount() + 1
        )

    df = df.drop(
        columns=[
            "_priority_order"
        ]
    )

    return df


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_output(
    df
):

    print(
        "\nSaving satellite-driven routes..."
    )

    os.makedirs(
        os.path.dirname(
            OUTPUT_FILE
        ),
        exist_ok=True
    )

    # Remove temporary/duplicate columns.

    drop_columns = [
        "predicted_daily_waste_kg_old",
        "predicted_daily_waste_kg_satellite",
        "collection_priority_old",
        "collection_priority_satellite",
        "satellite_collection_priority"
    ]

    for column in drop_columns:

        if column in df.columns:

            df = df.drop(
                columns=[column]
            )

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nSatellite dynamic route file saved:"
    )

    print(
        OUTPUT_FILE
    )

    return df


# ============================================================
# SUMMARY
# ============================================================

def display_summary(
    df
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "SATELLITE DYNAMIC ROUTING SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        "\nTotal route records:",
        len(df)
    )

    if "truck_id" in df.columns:

        print(
            "Number of trucks:",
            df["truck_id"].nunique()
        )

    print(
        "\nRouting priority:"
    )

    print(
        df[
            "collection_priority"
        ].value_counts()
    )

    if "waste_risk" in df.columns:

        print(
            "\nSatellite risk:"
        )

        print(
            df[
                "waste_risk"
            ].value_counts()
        )

    print(
        "\nTop 20 satellite-driven "
        "collection locations:"
    )

    columns = [
        "Grid_ID",
        "predicted_daily_waste_kg",
        "waste_risk",
        "collection_priority",
        "truck_id",
        "route_sequence"
    ]

    available = [
        c for c in columns
        if c in df.columns
    ]

    print(
        df[
            available
        ].head(20).to_string(
            index=False
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU SATELLITE "
        "DYNAMIC ROUTE INTEGRATION"
    )

    print("=" * 60)

    # 1. Satellite predictions

    satellite = (
        load_satellite_predictions()
    )

    # 2. Existing routes

    routes = (
        load_existing_routes()
    )

    # 3. Match predictions

    merged = merge_predictions(
        routes,
        satellite
    )

    # 4. Update priority

    merged = update_priority(
        merged
    )

    # 5. Update waste values

    merged = update_waste_values(
        merged
    )

    # 6. Reorder

    merged = reorder_routes(
        merged
    )

    # 7. Save

    result = save_output(
        merged
    )

    # 8. Summary

    display_summary(
        result
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "SATELLITE DYNAMIC ROUTING COMPLETED"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()