import os
import pandas as pd
import folium
from folium.plugins import AntPath


INPUT_FILE = "waste_module/data/processed/bengaluru_area_collection_routes.csv"
OUTPUT_DIR = "waste_module/data/processed"
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bengaluru_area_optimized_route_map.html"
)


def load_route_data():
    print("Loading optimized area route...")
    df = pd.read_csv(INPUT_FILE)

    required_columns = [
        "route_sequence",
        "area_name",
        "Latitude",
        "Longitude",
        "predicted_daily_waste_kg",
        "overflow_risk",
        "overflow_risk_score",
        "distance_from_previous_km",
        "cumulative_route_distance_km",
    ]

    missing = [c for c in required_columns if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.sort_values("route_sequence").reset_index(drop=True)

    return df


def risk_color(risk):
    if risk == "CRITICAL":
        return "red"
    elif risk == "HIGH":
        return "orange"
    elif risk == "MEDIUM":
        return "blue"
    return "green"


def create_route_map(df):

    # Center around the average of the routed areas
    center_lat = df["Latitude"].mean()
    center_lon = df["Longitude"].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        control_scale=True
    )

    # ---------------------------------------------------------
    # TITLE
    # ---------------------------------------------------------
    title_html = """
    <div style="
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        background-color: white;
        padding: 10px 18px;
        border: 2px solid black;
        border-radius: 8px;
        font-size: 18px;
        font-weight: bold;
    ">
        Bengaluru Area-Level Optimized Waste Collection Route
    </div>
    """

    m.get_root().html.add_child(
        folium.Element(title_html)
    )

    # ---------------------------------------------------------
    # ROUTE LINE
    # ---------------------------------------------------------
    route_coordinates = [
        [row["Latitude"], row["Longitude"]]
        for _, row in df.iterrows()
    ]

    AntPath(
        locations=route_coordinates,
        delay=800,
        weight=4,
        opacity=0.8,
        tooltip="Optimized collection sequence"
    ).add_to(m)

    # ---------------------------------------------------------
    # AREA MARKERS
    # ---------------------------------------------------------
    for _, row in df.iterrows():

        risk = row["overflow_risk"]
        color = risk_color(risk)

        waste = row["predicted_daily_waste_kg"]
        score = row["overflow_risk_score"]
        sequence = int(row["route_sequence"])
        distance = row["distance_from_previous_km"]
        cumulative = row["cumulative_route_distance_km"]

        popup_html = f"""
        <div style="width:280px">

            <h4>{row['area_name']}</h4>

            <b>Route Sequence:</b> {sequence}<br>
            <b>Predicted Daily Waste:</b> {waste:,.2f} kg<br>
            <b>Overflow Risk:</b> {risk}<br>
            <b>Overflow Risk Score:</b> {score:.2f}<br>
            <b>Distance from Previous Area:</b> {distance:.2f} km<br>
            <b>Cumulative Route Distance:</b> {cumulative:.2f} km

        </div>
        """

        tooltip = (
            f"#{sequence} | {row['area_name']} | "
            f"{risk} | {waste:,.0f} kg"
        )

        folium.CircleMarker(
            location=[
                row["Latitude"],
                row["Longitude"]
            ],
            radius=7,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            tooltip=tooltip,
            popup=folium.Popup(
                popup_html,
                max_width=350
            )
        ).add_to(m)

        # Route sequence label
        folium.Marker(
            location=[
                row["Latitude"],
                row["Longitude"]
            ],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    font-size:10px;
                    font-weight:bold;
                    color:black;
                    background:white;
                    border:1px solid black;
                    border-radius:4px;
                    padding:1px 3px;
                ">
                    {sequence}
                </div>
                """
            )
        ).add_to(m)

    # ---------------------------------------------------------
    # START MARKER
    # ---------------------------------------------------------
    first = df.iloc[0]

    folium.Marker(
        location=[
            first["Latitude"],
            first["Longitude"]
        ],
        popup=f"START: {first['area_name']}",
        tooltip=f"START: {first['area_name']}",
        icon=folium.Icon(
            color="green",
            icon="play"
        )
    ).add_to(m)

    # ---------------------------------------------------------
    # END MARKER
    # ---------------------------------------------------------
    last = df.iloc[-1]

    folium.Marker(
        location=[
            last["Latitude"],
            last["Longitude"]
        ],
        popup=f"END: {last['area_name']}",
        tooltip=f"END: {last['area_name']}",
        icon=folium.Icon(
            color="red",
            icon="stop"
        )
    ).add_to(m)

    # ---------------------------------------------------------
    # LEGEND
    # ---------------------------------------------------------
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index: 9999;
        background-color: white;
        padding: 12px;
        border: 2px solid grey;
        border-radius: 8px;
        font-size: 13px;
    ">

    <b>Overflow Risk</b><br><br>

    <span style="color:red;">●</span>
    CRITICAL<br>

    <span style="color:orange;">●</span>
    HIGH<br>

    <span style="color:blue;">●</span>
    MEDIUM<br>

    <span style="color:green;">●</span>
    LOW

    </div>
    """

    m.get_root().html.add_child(
        folium.Element(legend_html)
    )

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    m.save(OUTPUT_FILE)

    return OUTPUT_FILE


def main():

    print("=" * 70)
    print("BENGALURU AREA-LEVEL ROUTE VISUALIZATION")
    print("=" * 70)

    df = load_route_data()

    print(f"Areas in route: {len(df)}")
    print(
        f"Total predicted waste: "
        f"{df['predicted_daily_waste_kg'].sum():,.2f} kg"
    )

    print(
        f"Total route distance: "
        f"{df['cumulative_route_distance_km'].max():,.2f} km"
    )

    print("\nRisk distribution:")
    print(
        df["overflow_risk"]
        .value_counts()
        .to_string()
    )

    output = create_route_map(df)

    print("\n" + "=" * 70)
    print("ROUTE VISUALIZATION COMPLETED")
    print("=" * 70)

    print(f"\nMap saved to:")
    print(output)


if __name__ == "__main__":
    main()