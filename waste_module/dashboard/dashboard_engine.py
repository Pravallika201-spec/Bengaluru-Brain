from pathlib import Path
import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ROUTE_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_collection_routes.gpkg"
)


def load_route_data():

    if not ROUTE_FILE.exists():
        raise FileNotFoundError(
            f"Route dataset not found:\n{ROUTE_FILE}"
        )

    gdf = gpd.read_file(
        ROUTE_FILE,
        layer="collection_routes"
    )

    return gdf


def get_dashboard_data():

    gdf = load_route_data()

    total_locations = len(gdf)

    total_waste = float(
        gdf["predicted_daily_waste_kg"].sum()
    )

    total_distance = float(
        gdf["distance_from_previous_km"].sum()
    )

    trucks = (
        gdf["truck_id"]
        .dropna()
        .unique()
        .tolist()
    )

    total_trucks = len(trucks)

    priority_counts = (
        gdf["collection_priority"]
        .value_counts()
        .to_dict()
    )

    truck_summary = (
        gdf.groupby("truck_id")
        .agg(
            collection_points=("Grid_ID", "count"),
            total_waste_kg=(
                "predicted_daily_waste_kg",
                "sum"
            ),
            total_distance_km=(
                "distance_from_previous_km",
                "sum"
            ),
            utilization_percent=(
                "route_utilization_percent",
                "max"
            )
        )
        .reset_index()
    )

    truck_summary = truck_summary.round(2)

    return {
        "gdf": gdf,
        "total_locations": total_locations,
        "total_waste": round(total_waste, 2),
        "total_distance": round(total_distance, 2),
        "total_trucks": total_trucks,
        "priority_counts": priority_counts,
        "truck_summary": truck_summary.to_dict(
            orient="records"
        )
    }