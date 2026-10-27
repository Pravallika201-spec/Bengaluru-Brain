import os
import pandas as pd
import geopandas as gpd
import streamlit as st
import plotly.express as px


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

SATELLITE_OUTPUT = os.path.join(
    BASE_DIR,
    "waste_module",
    "satellite",
    "outputs"
)

PROCESSED_DIR = os.path.join(
    BASE_DIR,
    "waste_module",
    "data",
    "processed"
)


# ============================================================
# INPUT FILES
# ============================================================

EVENT_FILE = os.path.join(
    SATELLITE_OUTPUT,
    "bengaluru_events.csv"
)

EVENT_IMPACT_FILE = os.path.join(
    SATELLITE_OUTPUT,
    "bengaluru_event_grid_impact.csv"
)

EVENT_WASTE_FILE = os.path.join(
    SATELLITE_OUTPUT,
    "bengaluru_event_aware_waste_predictions.csv"
)

AREA_OVERFLOW_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_area_overflow_predictions.gpkg"
)


# ============================================================
# IMPORTANT:
# USE EVENT-AWARE ROUTE OUTPUT
# ============================================================

EVENT_AWARE_ROUTE_FILE = os.path.join(
    PROCESSED_DIR,
    "bengaluru_event_aware_area_collection_routes.csv"
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Urban Predictive Intelligence",
    page_icon="♻️",
    layout="wide"
)


# ============================================================
# TITLE
# ============================================================

st.title(
    "♻️ Urban Predictive Intelligence System"
)

st.subheader(
    "Event-Aware Waste Prediction & Dynamic Collection Routing"
)

st.markdown(
    """
    **Urban Waste Management Intelligence Platform**

    The system combines satellite-derived spatial features,
    land-use information, upcoming-event intelligence,
    event-aware waste prediction, overflow-risk assessment,
    area-level prioritization and dynamic truck routing
    to identify where waste collection should be prioritized.
    """
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data():

    # --------------------------------------------------------
    # Events
    # --------------------------------------------------------

    events = pd.read_csv(
        EVENT_FILE
    )

    # --------------------------------------------------------
    # Event → Grid impact
    # --------------------------------------------------------

    event_impact = pd.read_csv(
        EVENT_IMPACT_FILE
    )

    # --------------------------------------------------------
    # Event-aware waste predictions
    # --------------------------------------------------------

    event_waste = pd.read_csv(
        EVENT_WASTE_FILE
    )

    # --------------------------------------------------------
    # Area overflow predictions
    # --------------------------------------------------------

    areas = gpd.read_file(
        AREA_OVERFLOW_FILE,
        layer="area_overflow_predictions"
    )

    # --------------------------------------------------------
    # Event-aware area routes
    # --------------------------------------------------------

    routes = pd.read_csv(
        EVENT_AWARE_ROUTE_FILE
    )

    return (
        events,
        event_impact,
        event_waste,
        areas,
        routes
    )


# ============================================================
# LOAD DATA SAFELY
# ============================================================

try:

    (
        events,
        event_impact,
        event_waste,
        areas,
        routes
    ) = load_data()

except Exception as e:

    st.error(
        "Unable to load project output files."
    )

    st.code(
        str(e)
    )

    st.stop()


# ============================================================
# DATA VALIDATION
# ============================================================

required_route_columns = [
    "area_osm_id",
    "area_name",
    "truck_id",
    "route_sequence",
    "Latitude",
    "Longitude",
    "event_adjusted_waste_kg",
    "additional_event_waste_kg",
    "event_aware_risk_score",
    "overflow_risk",
    "collection_priority",
    "event_affected_grids",
    "critical_grids",
    "distance_from_previous_km",
    "route_total_distance_km",
    "route_total_waste_kg",
    "route_area_count"
]


missing_route_columns = [
    column
    for column in required_route_columns
    if column not in routes.columns
]


if missing_route_columns:

    st.error(
        "The event-aware route file is missing required columns."
    )

    st.write(
        "Missing columns:"
    )

    st.code(
        "\n".join(
            missing_route_columns
        )
    )

    st.write(
        "Available columns:"
    )

    st.code(
        "\n".join(
            routes.columns.tolist()
        )
    )

    st.stop()


# ============================================================
# NUMERIC CONVERSIONS
# ============================================================

numeric_columns = [
    "event_adjusted_waste_kg",
    "additional_event_waste_kg",
    "event_aware_risk_score",
    "distance_from_previous_km",
    "route_total_distance_km",
    "route_total_waste_kg",
    "route_area_count",
    "event_affected_grids",
    "critical_grids",
    "Latitude",
    "Longitude"
]


for column in numeric_columns:

    if column in routes.columns:

        routes[column] = pd.to_numeric(
            routes[column],
            errors="coerce"
        )


# ============================================================
# KEY SYSTEM METRICS
# ============================================================

# ------------------------------------------------------------
# Baseline waste
# ------------------------------------------------------------

baseline_waste = event_waste[
    "predicted_daily_waste_kg"
].sum()


# ------------------------------------------------------------
# Event-adjusted waste
# ------------------------------------------------------------

event_waste_total = event_waste[
    "event_adjusted_waste_kg"
].sum()


# ------------------------------------------------------------
# Additional event waste
# ------------------------------------------------------------

additional_waste = event_waste[
    "additional_event_waste_kg"
].sum()


# ------------------------------------------------------------
# Event affected grids
# ------------------------------------------------------------

affected_grids = int(
    event_waste[
        "event_affected"
    ].sum()
)


# ------------------------------------------------------------
# Priority areas
# ------------------------------------------------------------

priority_areas = routes[
    "area_name"
].nunique()


# ------------------------------------------------------------
# Number of trucks
# ------------------------------------------------------------

trucks = routes[
    "truck_id"
].nunique()


# ------------------------------------------------------------
# Priority waste
# ------------------------------------------------------------

priority_waste = routes[
    "event_adjusted_waste_kg"
].sum()


# ------------------------------------------------------------
# Critical areas
# ------------------------------------------------------------

critical_areas = routes[
    routes[
        "overflow_risk"
    ] == "CRITICAL"
][
    "area_name"
].nunique()


# ------------------------------------------------------------
# High-risk areas
# ------------------------------------------------------------

high_areas = routes[
    routes[
        "overflow_risk"
    ] == "HIGH"
][
    "area_name"
].nunique()


# ------------------------------------------------------------
# Total route distance
# ------------------------------------------------------------

if "route_total_distance_km" in routes.columns:

    total_route_distance = routes[
        "route_total_distance_km"
    ].max()

else:

    total_route_distance = routes[
        "distance_from_previous_km"
    ].sum()


# ============================================================
# SYSTEM OVERVIEW
# ============================================================

st.markdown("---")

st.markdown(
    "## 📊 System Overview"
)


c1, c2, c3, c4 = st.columns(4)


c1.metric(
    "Grid Cells",
    f"{len(event_waste):,}"
)


c2.metric(
    "Areas Analyzed",
    f"{areas['area_name'].nunique() if 'area_name' in areas.columns else 366:,}"
)


c3.metric(
    "Event-Affected Grids",
    f"{affected_grids:,}"
)


c4.metric(
    "Priority Areas",
    f"{priority_areas:,}"
)


# ============================================================
# SECOND METRIC ROW
# ============================================================

c5, c6, c7, c8 = st.columns(4)


c5.metric(
    "Baseline Waste",
    f"{baseline_waste:,.0f} kg/day"
)


c6.metric(
    "Event-Adjusted Waste",
    f"{event_waste_total:,.0f} kg/day"
)


c7.metric(
    "Additional Event Waste",
    f"{additional_waste:,.0f} kg/day"
)


c8.metric(
    "Trucks Used",
    f"{trucks}"
)


# ============================================================
# EVENT INTELLIGENCE
# ============================================================

st.markdown("---")

st.markdown(
    "## 🎉 Event Intelligence"
)


if len(events) > 0:

    event = events.iloc[0]

    e1, e2, e3, e4 = st.columns(4)


    # --------------------------------------------------------
    # Event name
    # --------------------------------------------------------

    e1.metric(
        "Upcoming Event",
        str(
            event.get(
                "event_name",
                "N/A"
            )
        )
    )


    # --------------------------------------------------------
    # Event date
    # --------------------------------------------------------

    e2.metric(
        "Event Date",
        str(
            event.get(
                "start_datetime",
                event.get(
                    "event_date",
                    "N/A"
                )
            )
        )
    )


    # --------------------------------------------------------
    # Event intensity
    # --------------------------------------------------------

    e3.metric(
        "Event Intensity",
        str(
            event.get(
                "event_intensity",
                "N/A"
            )
        )
    )


    # --------------------------------------------------------
    # Affected grids
    # --------------------------------------------------------

    e4.metric(
        "Affected Grids",
        f"{affected_grids:,}"
    )


    # --------------------------------------------------------
    # Event information box
    # --------------------------------------------------------

    st.info(
        f"""
        **{event.get('event_name', 'Upcoming Event')}**

        The event-aware spatial intelligence module identified
        **{affected_grids:,} grid cells** that may experience
        increased waste generation.

        The event impact is incorporated into the waste prediction
        and collection-priority pipeline.
        """
    )


else:

    st.warning(
        "No upcoming event information was found."
    )


# ============================================================
# EVENT-AWARE RISK DISTRIBUTION
# ============================================================

col1, col2 = st.columns(2)


with col1:

    risk_counts = (
        event_waste[
            "event_aware_waste_risk"
        ]
        .value_counts()
        .reset_index()
    )


    risk_counts.columns = [
        "Risk",
        "Count"
    ]


    fig = px.bar(
        risk_counts,
        x="Risk",
        y="Count",
        title="Event-Aware Waste Risk Distribution",
        text="Count"
    )


    fig.update_layout(
        showlegend=False
    )


    st.plotly_chart(
        fig,
        use_container_width=True
    )


# ============================================================
# BASELINE VS EVENT-ADJUSTED WASTE
# ============================================================

with col2:

    comparison = pd.DataFrame(
        {
            "Scenario": [
                "Baseline",
                "Event Adjusted"
            ],

            "Waste": [
                baseline_waste,
                event_waste_total
            ]
        }
    )


    fig2 = px.bar(
        comparison,
        x="Scenario",
        y="Waste",
        title="Baseline vs Event-Adjusted Waste",
        text="Waste"
    )


    fig2.update_traces(
        texttemplate="%{text:,.0f} kg",
        textposition="outside"
    )


    st.plotly_chart(
        fig2,
        use_container_width=True
    )


# ============================================================
# EVENT WASTE INCREASE
# ============================================================

if baseline_waste > 0:

    event_increase_percent = (
        additional_waste
        /
        baseline_waste
        *
        100
    )

else:

    event_increase_percent = 0


st.metric(
    "Event-Driven Waste Increase",
    f"{event_increase_percent:.2f}%"
)


# ============================================================
# PRIORITY COLLECTION AREAS
# ============================================================

st.markdown("---")

st.markdown(
    "## 🚨 Priority Collection Areas"
)


p1, p2, p3, p4 = st.columns(4)


p1.metric(
    "Critical Areas",
    f"{critical_areas}"
)


p2.metric(
    "High-Risk Areas",
    f"{high_areas}"
)


p3.metric(
    "Priority Areas",
    f"{priority_areas}"
)


p4.metric(
    "Priority Waste",
    f"{priority_waste:,.0f} kg/day"
)


# ============================================================
# TOP PRIORITY AREAS
# ============================================================

top_areas = (
    routes
    .sort_values(
        "event_adjusted_waste_kg",
        ascending=False
    )
    .drop_duplicates(
        "area_name"
    )
    .head(15)
)


fig3 = px.bar(
    top_areas.sort_values(
        "event_adjusted_waste_kg"
    ),
    x="event_adjusted_waste_kg",
    y="area_name",
    orientation="h",
    title="Top Priority Collection Areas",
    text="event_adjusted_waste_kg"
)


fig3.update_traces(
    texttemplate="%{text:,.0f} kg",
    textposition="outside"
)


fig3.update_layout(
    xaxis_title="Event-Adjusted Waste (kg/day)",
    yaxis_title="Area"
)


st.plotly_chart(
    fig3,
    use_container_width=True
)


# ============================================================
# PRIORITY AREA TABLE
# ============================================================

st.markdown(
    "### Priority Area Details"
)


priority_table = routes[
    [
        "route_sequence",
        "area_name",
        "event_adjusted_waste_kg",
        "additional_event_waste_kg",
        "event_aware_risk_score",
        "overflow_risk",
        "collection_priority",
        "event_affected_grids",
        "critical_grids"
    ]
].sort_values(
    "event_aware_risk_score",
    ascending=False
)


st.dataframe(
    priority_table,
    use_container_width=True,
    height=400
)


# ============================================================
# DYNAMIC TRUCK ROUTING
# ============================================================

st.markdown("---")

st.markdown(
    "## 🚛 Dynamic Truck Routing"
)


r1, r2, r3, r4 = st.columns(4)


r1.metric(
    "Collection Areas",
    f"{priority_areas}"
)


r2.metric(
    "Trucks",
    f"{trucks}"
)


r3.metric(
    "Priority Waste",
    f"{priority_waste:,.0f} kg/day"
)


r4.metric(
    "Route Distance",
    f"{total_route_distance:,.2f} km"
)


# ============================================================
# TRUCK SUMMARY
# ============================================================

truck_summary = (
    routes
    .groupby(
        "truck_id"
    )
    .agg(
        areas=(
            "area_name",
            "count"
        ),

        waste_kg=(
            "event_adjusted_waste_kg",
            "sum"
        ),

        distance_km=(
            "route_total_distance_km",
            "first"
        )
    )
    .reset_index()
    .sort_values(
        "waste_kg",
        ascending=False
    )
)


# ============================================================
# TRUCK WASTE CHART
# ============================================================

fig4 = px.bar(
    truck_summary,
    x="truck_id",
    y="waste_kg",
    title="Event-Adjusted Waste Assigned to Each Truck",
    text="waste_kg"
)


fig4.update_traces(
    texttemplate="%{text:,.0f} kg",
    textposition="outside"
)


fig4.update_layout(
    xaxis_title="Truck",
    yaxis_title="Assigned Event-Adjusted Waste (kg/day)"
)


st.plotly_chart(
    fig4,
    use_container_width=True
)


# ============================================================
# TRUCK SUMMARY TABLE
# ============================================================

st.markdown(
    "### 🚛 Truck Assignment Summary"
)


truck_display = truck_summary.copy()


truck_display.columns = [
    "Truck ID",
    "Areas",
    "Event-Adjusted Waste (kg)",
    "Route Distance (km)"
]


st.dataframe(
    truck_display,
    use_container_width=True
)


# ============================================================
# GENERATED COLLECTION ROUTES
# ============================================================

st.markdown("---")

st.markdown(
    "## 🗺️ Generated Collection Routes"
)


display_routes = routes[
    [
        "truck_id",
        "route_sequence",
        "area_name",
        "event_adjusted_waste_kg",
        "additional_event_waste_kg",
        "event_aware_risk_score",
        "overflow_risk",
        "collection_priority",
        "distance_from_previous_km"
    ]
].sort_values(
    [
        "truck_id",
        "route_sequence"
    ]
)


st.dataframe(
    display_routes,
    use_container_width=True,
    height=500
)


# ============================================================
# ROUTE MAP
# ============================================================

st.markdown(
    "### 📍 Collection Route Map"
)


map_data = routes[
    [
        "Latitude",
        "Longitude",
        "area_name",
        "truck_id",
        "route_sequence",
        "overflow_risk",
        "event_adjusted_waste_kg"
    ]
].dropna(
    subset=[
        "Latitude",
        "Longitude"
    ]
)


if not map_data.empty:

    fig_map = px.scatter_map(
        map_data,
        lat="Latitude",
        lon="Longitude",
        hover_name="area_name",
        hover_data={
            "truck_id": True,
            "route_sequence": True,
            "overflow_risk": True,
            "event_adjusted_waste_kg": ":,.2f",
            "Latitude": False,
            "Longitude": False
        },
        zoom=10,
        height=600
    )


    fig_map.update_layout(
        map_style="open-street-map"
    )


    st.plotly_chart(
        fig_map,
        use_container_width=True
    )

else:

    st.warning(
        "No valid geographic coordinates available for route mapping."
    )


# ============================================================
# ROUTE STATISTICS
# ============================================================

st.markdown(
    "### Route Statistics"
)


s1, s2, s3, s4 = st.columns(4)


s1.metric(
    "Total Route Distance",
    f"{total_route_distance:,.2f} km"
)


s2.metric(
    "Total Routed Areas",
    f"{priority_areas}"
)


s3.metric(
    "Critical Areas",
    f"{critical_areas}"
)


s4.metric(
    "High-Risk Areas",
    f"{high_areas}"
)


# ============================================================
# END-TO-END SYSTEM PIPELINE
# ============================================================

st.markdown("---")

st.markdown(
    "## 🔄 End-to-End System Pipeline"
)


st.markdown(
    """
    ### 1. Upcoming Events
    ↓

    ### 2. Event Ingestion
    ↓

    ### 3. Event → Grid Spatial Impact
    ↓

    ### 4. Satellite + Land-Use Waste Prediction
    ↓

    ### 5. Event-Aware Waste Adjustment
    ↓

    ### 6. Overflow-Risk Prediction
    ↓

    ### 7. Grid → Area Aggregation
    ↓

    ### 8. Event-Aware Area Prioritization
    ↓

    ### 9. Dynamic Truck Assignment
    ↓

    ### 10. Geographical Route Optimization
    ↓

    ### 11. Collection Route Output
    """
)


# ============================================================
# SYSTEM DATA FLOW
# ============================================================

st.markdown(
    "### System Data Flow"
)


flow_data = pd.DataFrame(
    {
        "Stage": [
            "Event Intelligence",
            "Spatial Impact",
            "Waste Prediction",
            "Event Adjustment",
            "Overflow Prediction",
            "Area Aggregation",
            "Route Optimization"
        ],

        "Output": [
            "Upcoming events",
            "Affected grids",
            "Baseline waste",
            "Event-adjusted waste",
            "Overflow risk",
            "Priority areas",
            "Truck routes"
        ]
    }
)


st.dataframe(
    flow_data,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# FINAL RESULT
# ============================================================

st.markdown("---")

st.markdown(
    "## ✅ Final System Result"
)


st.success(
    f"""
    The event-aware urban waste intelligence system identified
    **{priority_areas} high/critical collection areas** and dynamically
    assigned them to **{trucks} trucks**.

    **Total event-adjusted priority waste:**
    {priority_waste:,.2f} kg/day

    **Additional event-related waste:**
    {additional_waste:,.2f} kg/day

    **Critical areas:**
    {critical_areas}

    **High-risk areas:**
    {high_areas}

    **Total optimized route distance:**
    {total_route_distance:,.2f} km
    """
)


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Urban Predictive Intelligence System | "
    "Event-Aware Waste Prediction + "
    "Overflow Risk Assessment + "
    "Dynamic Collection Routing"
)