import os
import json
import math
import pandas as pd
import geopandas as gpd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium import plugins
from streamlit_folium import st_folium
from datetime import datetime

# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SATELLITE_OUTPUT  = os.path.join(BASE_DIR, "waste_module", "satellite", "outputs")
PROCESSED_DIR     = os.path.join(BASE_DIR, "waste_module", "data", "processed")

EVENT_FILE             = os.path.join(SATELLITE_OUTPUT, "bengaluru_events.csv")
EVENT_IMPACT_FILE      = os.path.join(SATELLITE_OUTPUT, "bengaluru_event_grid_impact.csv")
EVENT_WASTE_FILE       = os.path.join(SATELLITE_OUTPUT, "bengaluru_event_aware_waste_predictions.csv")
AREA_OVERFLOW_FILE     = os.path.join(PROCESSED_DIR,    "bengaluru_area_overflow_predictions.gpkg")
EVENT_AWARE_ROUTE_FILE = os.path.join(PROCESSED_DIR,    "bengaluru_event_aware_area_collection_routes.csv")
SAT_FEATURES_FILE      = os.path.join(SATELLITE_OUTPUT, "bengaluru_satellite_features.csv")
REPORTS_FILE           = os.path.join(BASE_DIR, "waste_module", "data", "citizen_reports.json")

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Bengaluru Brain — Waste Intelligence",
    page_icon="♻️", layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# STYLES
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=DM+Serif+Display&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:#f0f4f0;}

.hero{background:linear-gradient(135deg,#1b4332 0%,#2d6a4f 60%,#40916c 100%);
  border-radius:20px;padding:40px 48px;margin-bottom:32px;color:white;
  position:relative;overflow:hidden;}
.hero::before{content:"♻";position:absolute;right:40px;top:50%;
  transform:translateY(-50%);font-size:120px;opacity:0.08;}
.hero h1{font-family:'DM Serif Display',serif!important;font-size:2.4rem!important;
  font-weight:400!important;color:white!important;margin:0 0 8px 0!important;line-height:1.2!important;}
.hero p{font-size:1.05rem;opacity:0.85;margin:0;max-width:600px;line-height:1.6;}
.hero .tag{display:inline-block;background:rgba(255,255,255,0.15);
  border:1px solid rgba(255,255,255,0.3);border-radius:20px;padding:4px 14px;
  font-size:0.78rem;letter-spacing:0.05em;text-transform:uppercase;
  margin-bottom:16px;font-weight:500;}

.stat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;}
.stat-card{background:white;border-radius:14px;padding:20px 24px;
  border-left:4px solid #40916c;box-shadow:0 2px 12px rgba(0,0,0,0.06);}
.stat-card.critical{border-left-color:#e63946;}
.stat-card.high{border-left-color:#f4a261;}
.stat-card.route{border-left-color:#457b9d;}
.stat-label{font-size:0.75rem;font-weight:600;text-transform:uppercase;
  letter-spacing:0.08em;color:#888;margin-bottom:6px;}
.stat-value{font-size:2rem;font-weight:700;color:#1b4332;line-height:1;}
.stat-sub{font-size:0.8rem;color:#aaa;margin-top:4px;}

.section-header{font-family:'DM Serif Display',serif;font-size:1.5rem;
  color:#1b4332;margin:32px 0 16px 0;padding-bottom:10px;
  border-bottom:2px solid #d8f3dc;}

.info-panel{background:white;border-radius:16px;padding:20px 24px;
  box-shadow:0 4px 20px rgba(0,0,0,0.08);border-top:4px solid #40916c;
  margin-bottom:16px;}
.info-panel.critical{border-top-color:#e63946;}
.info-panel.high{border-top-color:#f4a261;}
.info-panel.medium{border-top-color:#e9c46a;}
.info-panel.low{border-top-color:#52b788;}
.info-panel h3{color:#1b4332;font-size:1.1rem;font-weight:700;margin:0 0 12px 0;}

.badge{display:inline-block;padding:4px 12px;border-radius:12px;
  font-size:0.78rem;font-weight:700;letter-spacing:0.04em;}
.badge-critical{background:#fde8e8;color:#c0392b;}
.badge-high{background:#fff0e0;color:#d35400;}
.badge-medium{background:#fef9c3;color:#92700a;}
.badge-low{background:#d8f3dc;color:#1b4332;}

[data-testid="stSidebar"]{background:#1b4332!important;}
[data-testid="stSidebar"] *{color:#d8f3dc!important;}
[data-testid="metric-container"]{background:white;border-radius:14px;
  padding:18px;border:1px solid #e8f5e9;box-shadow:0 2px 8px rgba(0,0,0,0.04);}
[data-testid="metric-container"] label{color:#888!important;font-size:0.75rem!important;
  font-weight:600!important;text-transform:uppercase!important;letter-spacing:0.07em!important;}
[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#1b4332!important;font-weight:700!important;}
.info-box{background:#d8f3dc;border-left:4px solid #40916c;border-radius:10px;
  padding:14px 18px;margin:12px 0;color:#1b4332;font-size:0.93rem;line-height:1.6;}
.success-box{background:#e8f5e9;border:1px solid #40916c;border-radius:14px;
  padding:20px 24px;margin:16px 0;color:#1b4332;}
[data-testid="stFileUploader"]{border:2px dashed #40916c!important;
  border-radius:14px!important;background:#f8fdf8!important;}
.stButton>button[kind="primary"]{background:#1b4332!important;border:none!important;
  border-radius:10px!important;font-weight:600!important;padding:10px 28px!important;}
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data():
    events        = pd.read_csv(EVENT_FILE)
    event_impact  = pd.read_csv(EVENT_IMPACT_FILE)
    event_waste   = pd.read_csv(EVENT_WASTE_FILE)
    areas         = gpd.read_file(AREA_OVERFLOW_FILE,
                                  layer="area_overflow_predictions")
    routes        = pd.read_csv(EVENT_AWARE_ROUTE_FILE)
    sat_features  = pd.read_csv(SAT_FEATURES_FILE)
    return events, event_impact, event_waste, areas, routes, sat_features

try:
    events, event_impact, event_waste, areas, routes, sat_features = load_data()
except Exception as e:
    st.error("Unable to load project output files.")
    st.code(str(e)); st.stop()

# Numeric fix
for col in ["event_aware_risk_score","distance_from_previous_km",
            "route_total_distance_km","event_affected_grids",
            "critical_grids","Latitude","Longitude"]:
    if col in routes.columns:
        routes[col] = pd.to_numeric(routes[col], errors="coerce")

# Build area centroid lookup from overflow GDF
areas_geo = areas.copy()
areas_geo = areas_geo.to_crs("EPSG:32643")
areas_geo["centroid"] = areas_geo.geometry.centroid
areas_geo = areas_geo.to_crs("EPSG:4326")
areas_geo["centroid"] = areas_geo["centroid"].to_crs("EPSG:4326")  \
    if hasattr(areas_geo["centroid"],"to_crs") else areas_geo["centroid"]
areas_geo = areas_geo.set_crs("EPSG:4326", allow_override=True)
centroids = areas_geo.copy()
centroids["Latitude"]  = areas_geo.geometry.to_crs("EPSG:4326").centroid.y
centroids["Longitude"] = areas_geo.geometry.to_crs("EPSG:4326").centroid.x

# ============================================================
# CONSTANTS
# ============================================================

RISK_COLORS = {
    "CRITICAL": "#e63946",
    "HIGH":     "#f4a261",
    "MEDIUM":   "#e9c46a",
    "LOW":      "#52b788",
}
ROUTE_COLORS = [
    "#e63946","#457b9d","#2a9d8f","#e9c46a","#f4a261",
    "#264653","#6a4c93","#1982c4","#8ac926","#ff595e",
    "#6a994e","#bc4749","#a7c957","#386641","#6c584c",
]

affected_grids   = int(event_waste["event_affected"].sum())
priority_areas   = routes["area_name"].nunique()
critical_areas   = routes[routes["overflow_risk"]=="CRITICAL"]["area_name"].nunique()
high_areas       = routes[routes["overflow_risk"]=="HIGH"]["area_name"].nunique()
total_route_dist = (
    routes.groupby("truck_id")["route_total_distance_km"]
    .first().sum()
)
baseline_waste   = event_waste["predicted_daily_waste_kg"].sum()
additional_waste = event_waste["additional_event_waste_kg"].sum()
event_inc_pct    = (additional_waste/baseline_waste*100) if baseline_waste>0 else 0

route_ids  = sorted(routes["truck_id"].unique())
labels     = {tid: f"Route {i+1}" for i,tid in enumerate(route_ids)}
rev_labels = {v:k for k,v in labels.items()}

def risk_desc(risk):
    return {
        "CRITICAL": "Overflow imminent — immediate collection required.",
        "HIGH":     "High accumulation detected — priority collection needed.",
        "MEDIUM":   "Moderate accumulation — schedule within 24 hours.",
        "LOW":      "Normal levels — routine collection schedule applies.",
    }.get(risk,"")

def collection_status(risk):
    return {
        "CRITICAL": "🔴 Dispatched — urgent",
        "HIGH":     "🟠 Queued — priority",
        "MEDIUM":   "🟡 Scheduled — normal",
        "LOW":      "🟢 Monitored — routine",
    }.get(risk,"—")

# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown("""
<div style="padding:8px 0 16px 0;">
  <div style="font-family:'DM Serif Display',serif;font-size:1.4rem;
       color:white;line-height:1.2;">Bengaluru Brain</div>
  <div style="font-size:0.78rem;opacity:0.6;margin-top:4px;
       text-transform:uppercase;letter-spacing:0.08em;">Waste Intelligence</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

page = st.sidebar.radio("", [
    "🏠  Overview",
    "🗺️  Risk Map",
    "🛣️  Optimized Routes",
    "🎉  Event Intelligence",
    "📸  Report Waste",
    "📋  Citizen Reports",
    "🌤  Weather Integration",
    "📊  Social Media Events",
    "🔧  Fleet Maintenance",
    "🏗️  Land Use Changes",
    "✅  Model Validation",
    "📊  Uncertainty Analysis",
    "🔮  Scenario Analysis",
    "🛰️  Multi-Sensor Fusion",
])
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"<div style='font-size:0.78rem;opacity:0.5;'>"
    f"Updated {datetime.now().strftime('%d %b %Y  %H:%M')}</div>",
    unsafe_allow_html=True)

# ============================================================
# PAGE — OVERVIEW
# ============================================================

if page == "🏠  Overview":

    st.markdown("""
    <div class="hero">
      <div class="tag">🛰️ Satellite-Assisted Intelligence</div>
      <h1>Urban Waste Prediction<br>& Route Optimisation</h1>
      <p>Bengaluru Brain combines Sentinel-2 satellite imagery,
      OpenStreetMap land-use data, and event-aware machine learning
      to predict where waste collection is most urgently needed
      — and routes vehicles there first.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">Grid Cells Monitored</div>
        <div class="stat-value">{len(event_waste):,}</div>
        <div class="stat-sub">500 m × 500 m per cell</div>
      </div>
      <div class="stat-card critical">
        <div class="stat-label">Critical Areas</div>
        <div class="stat-value">{critical_areas}</div>
        <div class="stat-sub">Immediate collection needed</div>
      </div>
      <div class="stat-card high">
        <div class="stat-label">High-Risk Areas</div>
        <div class="stat-value">{high_areas}</div>
        <div class="stat-sub">Priority collection</div>
      </div>
      <div class="stat-card route">
        <div class="stat-label">Optimised Route</div>
        <div class="stat-value">{total_route_dist:,.1f} km</div>
        <div class="stat-sub">Total distance covered</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-header">How It Works</div>',
                unsafe_allow_html=True)
    steps = [
        ("🛰️","Satellite Acquisition","Sentinel-2 from Google Earth Engine"),
        ("🌱","Spectral Analysis","NDVI · NDBI · NDWI per grid"),
        ("🏙️","Land-Use Fusion","OSM residential/commercial/industrial"),
        ("🤖","ML Prediction","Random Forest — 3,053 grids"),
        ("🎉","Event Adjustment","Festival calendar risk boost"),
        ("🚨","Priority Selection","CRITICAL & HIGH areas chosen"),
        ("🛣️","Route Optimisation","OR-Tools VRP optimal routes"),
    ]
    cols = st.columns(len(steps))
    for col,(icon,title,desc) in zip(cols,steps):
        col.markdown(f"""
        <div style="background:white;border-radius:14px;padding:16px;
             text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.05);height:100%;">
          <div style="font-size:1.8rem;margin-bottom:8px;">{icon}</div>
          <div style="font-weight:600;color:#1b4332;font-size:0.85rem;
               margin-bottom:6px;">{title}</div>
          <div style="font-size:0.75rem;color:#888;line-height:1.4;">{desc}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-header">System Status</div>',
                unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Areas Analysed", f"{len(areas):,}")
    c2.metric("Event-Affected Grids", f"{affected_grids:,}")
    c3.metric("Priority Areas", f"{priority_areas}")
    c4.metric("Event Risk Increase", f"{event_inc_pct:.1f}%")

# ============================================================
# PAGE — RISK MAP  (all 366 areas + click info + NDVI chart)
# ============================================================

elif page == "🗺️  Risk Map":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\','
                'serif;font-weight:400;">Overflow Risk Map — All 366 Areas</h2>',
                unsafe_allow_html=True)
    st.markdown("Showing all GBA areas. Click any marker for details "
                "and satellite analysis.")

    # ── Search bar ──
    all_area_names = sorted(
        areas["area_name"].dropna().unique().tolist()
    )
    search_area = st.selectbox(
        "🔍 Search any area",
        ["-- Select area --"] + all_area_names,
        key="risk_search"
    )

    # ── Info panel on search ──
    if search_area != "-- Select area --":
        # Get risk from areas GDF
        area_info = areas[areas["area_name"]==search_area].iloc[0]
        risk      = area_info["Area_Overflow_Risk"]
        rc        = RISK_COLORS.get(risk,"#888")
        lat_a     = centroids[centroids["area_name"]==search_area]["Latitude"].values
        lon_a     = centroids[centroids["area_name"]==search_area]["Longitude"].values
        lat_a     = float(lat_a[0]) if len(lat_a)>0 else 12.9716
        lon_a     = float(lon_a[0]) if len(lon_a)>0 else 77.5946

        # Check if in routes (priority area)
        in_routes = search_area in routes["area_name"].values
        route_row = routes[routes["area_name"]==search_area].iloc[0] \
                    if in_routes else None

        affected = int(route_row["event_affected_grids"]) \
                   if in_routes and "event_affected_grids" in routes.columns \
                   else int(area_info.get("Grid_Cell_Count",0))
        priority = route_row["collection_priority"] \
                   if in_routes else area_info.get("Collection_Priority","—")

        st.markdown(f"""
        <div class="info-panel {risk.lower()}">
          <h3>📍 {search_area}</h3>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);
               gap:16px;margin-bottom:16px;">
            <div>
              <div style="font-size:0.72rem;font-weight:600;
                   text-transform:uppercase;color:#888;margin-bottom:4px;">
                Risk Level</div>
              <span class="badge badge-{risk.lower()}">{risk}</span>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;
                   text-transform:uppercase;color:#888;margin-bottom:4px;">
                Priority</div>
              <div style="font-weight:600;color:#1b4332;">{priority}</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;
                   text-transform:uppercase;color:#888;margin-bottom:4px;">
                Grid Cells</div>
              <div style="font-weight:600;color:#1b4332;">{affected:,}</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;
                   text-transform:uppercase;color:#888;margin-bottom:4px;">
                Collection Status</div>
              <div style="font-weight:600;">{collection_status(risk)}</div>
            </div>
          </div>
          <div style="font-size:0.88rem;color:#555;font-style:italic;">
            {risk_desc(risk)}
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Satellite analysis panel ──
        st.markdown("#### 🛰️ Satellite Analysis")
        map_col, chart_col = st.columns([1,1])

        with map_col:
            # Zoomed map of that location
            zm = folium.Map(
                location=[lat_a, lon_a],
                zoom_start=15,
                tiles="OpenStreetMap"
            )
            folium.CircleMarker(
                location=[lat_a, lon_a],
                radius=14,
                color=rc, fill=True,
                fill_color=rc, fill_opacity=0.7,
                popup=search_area
            ).add_to(zm)
            st_folium(zm, width=None, height=280, key="zoom_map")

        with chart_col:
            # NDVI/NDBI/NDWI radar chart from
            # nearest grid cells in event_waste
            nearby = event_waste.copy()
            nearby["dist"] = (
                (nearby["Latitude"]-lat_a)**2 +
                (nearby["Longitude"]-lon_a)**2
            ).apply(lambda x: x**0.5)
            nearby = nearby.nsmallest(10,"dist")

            ndvi_avg = nearby["NDVI"].mean()
            ndbi_avg = nearby["NDBI"].mean()
            ndwi_avg = nearby["NDWI"].mean()

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=["NDVI","NDBI","NDWI"],
                y=[ndvi_avg, ndbi_avg, ndwi_avg],
                marker_color=["#52b788","#e63946","#457b9d"],
                text=[f"{ndvi_avg:.3f}",f"{ndbi_avg:.3f}",f"{ndwi_avg:.3f}"],
                textposition="outside"
            ))
            fig.update_layout(
                title="Satellite Indices (Nearby Grids)",
                plot_bgcolor="white", paper_bgcolor="white",
                height=280, margin=dict(t=40,b=20,l=20,r=20),
                font_family="Inter",
                yaxis=dict(range=[-1,1]),
                annotations=[
                    dict(x=0,y=-0.15,xref="x",yref="paper",
                         text="Vegetation",showarrow=False,
                         font=dict(size=9,color="#888")),
                    dict(x=1,y=-0.15,xref="x",yref="paper",
                         text="Built-up",showarrow=False,
                         font=dict(size=9,color="#888")),
                    dict(x=2,y=-0.15,xref="x",yref="paper",
                         text="Moisture",showarrow=False,
                         font=dict(size=9,color="#888")),
                ]
            )
            st.plotly_chart(fig, use_container_width=True)

            # Interpretation
            if ndvi_avg < 0.1:
                veg = "Low vegetation — dense urban area"
            elif ndvi_avg < 0.3:
                veg = "Moderate vegetation — mixed urban"
            else:
                veg = "High vegetation — green area"

            if ndbi_avg > 0.1:
                builtup = "High built-up density"
            else:
                builtup = "Moderate built-up density"

            st.markdown(f"""
            <div class="info-box" style="margin-top:0;">
              🌱 <b>NDVI {ndvi_avg:.3f}</b> — {veg}<br>
              🏙️ <b>NDBI {ndbi_avg:.3f}</b> — {builtup}<br>
              💧 <b>NDWI {ndwi_avg:.3f}</b> — moisture index
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

    # ── Risk filter ──
    show_risk = st.multiselect(
        "Filter by risk level",
        ["CRITICAL","HIGH","MEDIUM","LOW"],
        default=["CRITICAL","HIGH","MEDIUM","LOW"]
    )

    # ── Build full map with all 366 areas ──
    m = folium.Map(
        location=[12.9716,77.5946],
        zoom_start=11,
        tiles="OpenStreetMap"
    )

    # Draw route lines for priority areas
    for i,(tid,tdata) in enumerate(routes.groupby("truck_id")):
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        td    = tdata.sort_values("route_sequence")
        coords= list(zip(td["Latitude"],td["Longitude"]))
        if len(coords)>1:
            folium.PolyLine(
                coords, color=color, weight=2.5,
                opacity=0.5, tooltip=labels.get(tid,tid)
            ).add_to(m)

    # Plot ALL 366 areas from overflow GDF
    for _,row in centroids.iterrows():
        risk = row.get("Area_Overflow_Risk","LOW")
        if risk not in show_risk:
            continue
        lat_r = row["Latitude"]
        lon_r = row["Longitude"]
        name  = row.get("area_name","Unknown")
        rc    = RISK_COLORS.get(risk,"#888")

        # Check if this area is a priority (in routes)
        in_priority = name in routes["area_name"].values
        radius      = 9 if in_priority else 5
        opacity     = 0.9 if in_priority else 0.5

        # Get route info if priority
        if in_priority:
            rrow    = routes[routes["area_name"]==name].iloc[0]
            tid     = rrow["truck_id"]
            rnum    = route_ids.index(tid)+1 if tid in route_ids else "?"
            seq     = int(rrow["route_sequence"])
            affected= int(rrow.get("event_affected_grids",0))
            prio    = rrow.get("collection_priority","—")
            extra   = (f"<tr><td style='color:#888;'>Route</td>"
                       f"<td><b>{labels.get(tid,tid)}</b></td></tr>"
                       f"<tr><td style='color:#888;'>Stop #</td>"
                       f"<td><b>{seq}</b></td></tr>"
                       f"<tr><td style='color:#888;'>Affected Grids</td>"
                       f"<td><b>{affected:,}</b></td></tr>")
        else:
            prio  = row.get("Collection_Priority","—")
            extra = ""

        popup_html = f"""
        <div style='font-family:sans-serif;min-width:200px;'>
          <b style='color:#1b4332;font-size:14px;'>{name}</b><br>
          {'<span style="background:#1b4332;color:white;padding:2px 8px;'
           'border-radius:8px;font-size:10px;font-weight:600;">PRIORITY AREA</span><br>'
           if in_priority else ''}
          <br>
          <table style='width:100%;font-size:12px;'>
            <tr><td style='color:#888;'>Risk</td>
                <td><b style='color:{rc};'>{risk}</b></td></tr>
            <tr><td style='color:#888;'>Priority</td>
                <td><b>{prio}</b></td></tr>
            {extra}
            <tr><td style='color:#888;'>Status</td>
                <td>{collection_status(risk)}</td></tr>
          </table>
          <div style='margin-top:8px;font-size:11px;color:#555;font-style:italic;'>
            {risk_desc(risk)}
          </div>
        </div>
        """

        folium.CircleMarker(
            location=[lat_r, lon_r],
            radius=radius,
            color=rc, fill=True,
            fill_color=rc,
            fill_opacity=opacity,
            popup=folium.Popup(popup_html, max_width=240)
        ).add_to(m)

    # Legend
    legend = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
         background:white;padding:14px 18px;border-radius:12px;
         box-shadow:0 4px 16px rgba(0,0,0,0.12);font-family:sans-serif;">
      <div style="font-weight:700;color:#1b4332;margin-bottom:10px;font-size:13px;">
        Risk Level</div>
      <div style="display:flex;flex-direction:column;gap:6px;">
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;
             background:#e63946;margin-right:8px;"></span>
             <span style="font-size:12px;">Critical — Immediate</span></div>
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;
             background:#f4a261;margin-right:8px;"></span>
             <span style="font-size:12px;">High — Priority</span></div>
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;
             background:#e9c46a;margin-right:8px;"></span>
             <span style="font-size:12px;">Medium — Scheduled</span></div>
        <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;
             background:#52b788;margin-right:8px;"></span>
             <span style="font-size:12px;">Low — Routine</span></div>
      </div>
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid #eee;
           font-size:11px;color:#888;">
        Larger dots = priority areas<br>Smaller dots = all other areas
      </div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    st_folium(m, width=None, height=580)

    st.markdown("""
    <div class="info-box">
      💡 <b>Tip:</b> All 366 GBA areas are shown. Larger brighter dots are
      priority collection areas. Click any dot for full details.
      Use the search bar above to look up any specific area and see
      its satellite analysis.
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# PAGE — OPTIMIZED ROUTES
# (click area → highlight full route + all stops in order)
# ============================================================

elif page == "🛣️  Optimized Routes":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\','
                'serif;font-weight:400;">Optimised Collection Routes</h2>',
                unsafe_allow_html=True)

    # ── Search bar ──
    route_area_names = sorted(routes["area_name"].dropna().unique().tolist())
    route_search = st.selectbox(
        "🔍 Search an area to see its full route",
        ["-- Select area --"] + route_area_names,
        key="route_search"
    )

    # Determine selected route from search
    if route_search != "-- Select area --":
        match     = routes[routes["area_name"]==route_search]
        found_tid = match.iloc[0]["truck_id"] if not match.empty else None
        found_seq = int(match.iloc[0]["route_sequence"]) if not match.empty else None
        found_risk= match.iloc[0]["overflow_risk"] if not match.empty else "—"
        rnum      = route_ids.index(found_tid)+1 \
                    if found_tid in route_ids else "?"
        total_stops = int(
            routes[routes["truck_id"]==found_tid]["route_sequence"].max()
        ) if found_tid else 0

        rc = RISK_COLORS.get(found_risk,"#888")
        st.markdown(f"""
        <div class="info-panel {found_risk.lower()}">
          <h3>📍 {route_search}</h3>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;">
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                   color:#888;margin-bottom:4px;">Assigned Route</div>
              <div style="font-weight:700;color:#1b4332;font-size:1.2rem;">
                Route {rnum}</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                   color:#888;margin-bottom:4px;">Stop Number</div>
              <div style="font-weight:700;color:#1b4332;font-size:1.2rem;">
                #{found_seq} of {total_stops}</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                   color:#888;margin-bottom:4px;">Risk Level</div>
              <span class="badge badge-{found_risk.lower()}">{found_risk}</span>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                   color:#888;margin-bottom:4px;">Status</div>
              <div style="font-weight:600;">{collection_status(found_risk)}</div>
            </div>
          </div>
          <div style="margin-top:12px;font-size:0.88rem;color:#555;font-style:italic;">
            {risk_desc(found_risk)}
          </div>
        </div>
        """, unsafe_allow_html=True)
        # Auto-select this route
        default_route = labels.get(found_tid,"All Routes") \
                        if found_tid else "All Routes"
    else:
        default_route = "All Routes"
        found_tid     = None

    st.markdown("---")

    # ── Metrics ──
    c1,c2,c3 = st.columns(3)
    c1.metric("Priority Areas", f"{priority_areas}")
    c2.metric("Total Route Distance", f"{total_route_dist:,.1f} km")
    c3.metric("Critical → High", f"{critical_areas} → {high_areas}")

    st.markdown("---")

    # ── Route selector ──
    selected = st.selectbox(
        "Select a route to view in detail",
        options=["All Routes"] + list(labels.values()),
        index=(["All Routes"]+list(labels.values())).index(default_route)
        if default_route in ["All Routes"]+list(labels.values()) else 0
    )

    selected_tid = rev_labels.get(selected) if selected != "All Routes" else None

    # ── SPLIT: map LEFT, narration RIGHT ──
    map_col, nar_col = st.columns([3,2])

    # ── MAP ──
    with map_col:
        m2 = folium.Map(
            location=[12.9716,77.5946],
            zoom_start=11,
            tiles="OpenStreetMap"
        )

        draw_routes = (
            routes if selected=="All Routes"
            else routes[routes["truck_id"]==selected_tid]
        )

        for i,(tid,tdata) in enumerate(draw_routes.groupby("truck_id")):
            color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            td    = tdata.sort_values("route_sequence")
            coords= list(zip(td["Latitude"],td["Longitude"]))

            # Animated path
            if len(coords)>1:
                plugins.AntPath(
                    coords, color=color,
                    weight=4, opacity=0.85,
                    delay=800,
                    tooltip=labels.get(tid,tid)
                ).add_to(m2)

            for j,(_,row) in enumerate(td.iterrows()):
                risk   = row["overflow_risk"]
                rc     = RISK_COLORS.get(risk,"#888")
                lat_r  = row["Latitude"]
                lon_r  = row["Longitude"]
                is_searched = (row["area_name"]==route_search
                               and route_search!="-- Select area --")

                # Highlight searched area with star
                if is_searched:
                    folium.Marker(
                        location=[lat_r,lon_r],
                        icon=folium.DivIcon(html=f"""
                        <div style="width:38px;height:38px;border-radius:50%;
                             background:{color};border:4px solid #FFD700;
                             box-shadow:0 0 12px rgba(255,215,0,0.8);
                             display:flex;align-items:center;justify-content:center;
                             color:white;font-weight:700;font-size:13px;">
                          {j+1}
                        </div>""", icon_size=(38,38), icon_anchor=(19,19)),
                        popup=folium.Popup(
                            f"<b>⭐ {row['area_name']}</b><br>"
                            f"Stop {j+1} — {labels.get(tid,tid)}<br>"
                            f"Risk: <b style='color:{rc};'>{risk}</b>",
                            max_width=200)
                    ).add_to(m2)
                else:
                    popup_html = f"""
                    <div style='font-family:sans-serif;min-width:180px;'>
                      <b style='color:#1b4332;'>{row['area_name']}</b><br>
                      <span style='font-size:11px;color:#888;'>
                        {labels.get(tid,tid)} — Stop {j+1}
                      </span><br><br>
                      <table style='font-size:12px;width:100%;'>
                        <tr><td style='color:#888;'>Risk</td>
                            <td><b style='color:{rc};'>{risk}</b></td></tr>
                        <tr><td style='color:#888;'>Priority</td>
                            <td><b>{row.get('collection_priority','—')}</b></td></tr>
                        <tr><td style='color:#888;'>Status</td>
                            <td>{collection_status(risk)}</td></tr>
                      </table>
                    </div>"""
                    folium.Marker(
                        location=[lat_r,lon_r],
                        icon=folium.DivIcon(html=f"""
                        <div style="width:28px;height:28px;border-radius:50%;
                             background:{color};border:3px solid white;
                             box-shadow:0 2px 6px rgba(0,0,0,0.3);
                             display:flex;align-items:center;justify-content:center;
                             color:white;font-weight:700;font-size:11px;">
                          {j+1}
                        </div>""", icon_size=(28,28), icon_anchor=(14,14)),
                        popup=folium.Popup(popup_html, max_width=210)
                    ).add_to(m2)

        st_folium(m2, width=None, height=580)

    # ── WRITTEN NARRATION ──
    with nar_col:
        st.markdown('<div class="section-header" style="margin-top:0;">'
                    '📋 Route Narration</div>', unsafe_allow_html=True)

        narrate = (
            routes if selected=="All Routes"
            else routes[routes["truck_id"]==selected_tid]
        )

        for i,(tid,tdata) in enumerate(narrate.groupby("truck_id")):
            color  = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            td     = tdata.sort_values("route_sequence")
            rname  = labels.get(tid,tid)
            dist   = td["route_total_distance_km"].iloc[0]
            stops  = len(td)
            crits  = len(td[td["overflow_risk"]=="CRITICAL"])
            first  = td.iloc[0]["area_name"]
            last   = td.iloc[-1]["area_name"]
            crit_names = td[td["overflow_risk"]=="CRITICAL"]["area_name"].tolist()

            with st.expander(
                f"**{rname}** — {stops} stops · {dist:.1f} km",
                expanded=(selected!="All Routes")
            ):
                # Route summary sentence
                st.markdown(f"""
                <div style="background:#f0f7f0;border-radius:10px;
                     padding:12px 14px;margin-bottom:14px;
                     font-size:0.88rem;color:#1b4332;line-height:1.6;
                     border-left:3px solid {color};">
                  <b>🚛 {rname}</b> begins at <b>{first}</b>
                  {" — a <b>CRITICAL</b> area requiring immediate collection —"
                   if td.iloc[0]["overflow_risk"]=="CRITICAL" else ""}
                  and covers <b>{stops} stops</b> across
                  <b>{dist:.1f} km</b>, ending at <b>{last}</b>.
                  {f"<br>⚠️ <b>{crits} critical stop(s):</b> "
                   f"{', '.join(crit_names[:3])}{'...' if len(crit_names)>3 else ''}."
                   if crits>0 else ""}
                </div>
                """, unsafe_allow_html=True)

                # Stop by stop with narration
                for j,(_,row) in enumerate(td.iterrows()):
                    risk   = row["overflow_risk"]
                    rc     = RISK_COLORS.get(risk,"#888")
                    dist_p = row["distance_from_previous_km"]
                    dist_s = (f"{dist_p:.1f} km from prev"
                              if dist_p>0 else "Starting point")
                    grids  = int(row.get("event_affected_grids",0))

                    if risk=="CRITICAL":
                        action = "⚠️ Immediate collection — overflow imminent."
                        next_s = ("Proceed urgently. Do not skip this stop."
                                  if j<stops-1 else "Final stop — return to depot.")
                    elif risk=="HIGH":
                        action = "🔶 Priority collection — high accumulation."
                        next_s = (f"After collection, proceed to stop {j+2}."
                                  if j<stops-1 else "Final stop — return to depot.")
                    else:
                        action = "✅ Standard collection."
                        next_s = (f"Continue to stop {j+2}."
                                  if j<stops-1 else "Final stop — return to depot.")

                    is_searched = (row["area_name"]==route_search
                                   and route_search!="-- Select area --")
                    highlight = ("border:2px solid #FFD700;"
                                 "box-shadow:0 0 8px rgba(255,215,0,0.5);"
                                 if is_searched else "")

                    st.markdown(f"""
                    <div style="display:flex;align-items:flex-start;gap:12px;
                         padding:10px 0;border-bottom:1px solid #f0f4f0;
                         {highlight}border-radius:8px;">
                      <div style="width:28px;height:28px;border-radius:50%;
                           background:{color};color:white;font-weight:700;
                           font-size:0.8rem;display:flex;align-items:center;
                           justify-content:center;flex-shrink:0;margin-top:2px;">
                        {j+1}
                      </div>
                      <div style="flex:1;">
                        <div style="display:flex;align-items:center;
                             justify-content:space-between;">
                          <span style="font-weight:600;color:#1b4332;font-size:0.92rem;">
                            {row['area_name']}
                            {'⭐' if is_searched else ''}
                          </span>
                          <span style="background:{rc};color:white;padding:2px 8px;
                                border-radius:8px;font-size:0.7rem;font-weight:700;">
                            {risk}
                          </span>
                        </div>
                        <div style="font-size:0.78rem;color:#888;margin-top:3px;">
                          {dist_s} &nbsp;·&nbsp; {grids:,} grids affected
                        </div>
                        <div style="font-size:0.8rem;color:#444;margin-top:4px;
                             font-style:italic;">{action}</div>
                        <div style="font-size:0.78rem;color:#2d6a4f;margin-top:3px;
                             font-weight:500;">→ {next_s}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

# ============================================================
# PAGE — EVENT INTELLIGENCE
# ============================================================

elif page == "🎉  Event Intelligence":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\','
                'serif;font-weight:400;">Event Intelligence</h2>',
                unsafe_allow_html=True)

    if len(events)>0:
        event = events.iloc[0]
        st.markdown(f"""
        <div class="hero">
          <div class="tag">🎉 Upcoming Event</div>
          <h1>{event.get('event_name','Event')}</h1>
          <p>Date: {event.get('start_datetime',event.get('event_date','N/A'))}
          &nbsp;·&nbsp; Intensity: {event.get('event_intensity','N/A')}
          &nbsp;·&nbsp; {affected_grids:,} grids affected</p>
        </div>""", unsafe_allow_html=True)

    col1,col2 = st.columns(2)
    with col1:
        risk_counts = (
            event_waste["event_aware_waste_risk"]
            .value_counts()
            .reindex(["CRITICAL","HIGH","MEDIUM","LOW"],fill_value=0)
            .reset_index()
        )
        risk_counts.columns=["Risk","Count"]
        fig = px.bar(risk_counts, x="Risk", y="Count",
                     title="Risk Distribution After Event Adjustment",
                     text="Count", color="Risk",
                     color_discrete_map={
                         "CRITICAL":"#e63946","HIGH":"#f4a261",
                         "MEDIUM":"#e9c46a","LOW":"#52b788"})
        fig.update_layout(showlegend=False,plot_bgcolor="white",
                          paper_bgcolor="white",font_family="Inter")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown('<div class="section-header">Impact Summary</div>',
                    unsafe_allow_html=True)
        st.metric("Event Risk Increase",f"{event_inc_pct:.2f}%")
        st.metric("Grids Affected",f"{affected_grids:,}")
        st.metric("Priority Areas",f"{priority_areas}")
        st.markdown(f"""
        <div class="info-box">
          The event-aware module identified <b>{affected_grids:,} grid cells</b>
          likely to experience increased waste during this event.
          Routes have been recalculated automatically.
        </div>""", unsafe_allow_html=True)

# ============================================================
# PAGE — REPORT WASTE
# ============================================================

elif page == "📸  Report Waste":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\','
                'serif;font-weight:400;">Report a Waste Issue</h2>',
                unsafe_allow_html=True)
    st.markdown("Help keep Bangalore clean. Your report feeds directly "
                "into our collection priority system.")
    st.markdown("---")

    st.markdown("### 📍 Your Location")
    st.markdown("""
    <div id="gps-status" style="background:#d8f3dc;border-left:4px solid #40916c;
         padding:12px 16px;border-radius:8px;margin-bottom:12px;
         font-size:14px;color:#1b4332;">
      📡 Click below to detect your GPS location automatically
    </div>
    <button onclick="getGPS()" style="background:#1b4332;color:white;border:none;
         padding:10px 24px;border-radius:10px;cursor:pointer;
         font-size:14px;font-weight:600;margin-bottom:16px;">
      📍 Detect My Location
    </button>
    <script>
    function getGPS(){
      var s=document.getElementById('gps-status');
      s.innerHTML='⏳ Detecting...';
      if(!navigator.geolocation){
        s.innerHTML='❌ Not supported. Select area below.';return;}
      navigator.geolocation.getCurrentPosition(
        function(p){s.innerHTML='✅ Location: '
          +p.coords.latitude.toFixed(5)+', '+p.coords.longitude.toFixed(5);},
        function(){s.innerHTML='⚠️ Could not detect. Select area below.';});
    }
    </script>""", unsafe_allow_html=True)

    selected_area = st.selectbox("Or select your area",
        ["-- Select area --"]+sorted(routes["area_name"].unique().tolist()))

    st.markdown("---")
    st.markdown("### 📷 Upload Photo")
    photo = st.file_uploader("Capture or upload a photo of the waste",
        type=["jpg","jpeg","png","heic"])
    if photo:
        st.image(photo, caption="Preview", use_column_width=True)

    st.markdown("---")
    st.markdown("### 📝 Issue Details")
    issue_type = st.selectbox("Type of waste issue",[
        "-- Select --","🗑️  Overflowing bin",
        "🗓️  Missed collection (3+ days)",
        "🛣️  Waste dumped on road",
        "💧  Waste near water body",
        "🏗️  Construction debris",
        "⚠️  Hazardous waste","Other"])
    description = st.text_area("Describe the issue",
        placeholder="e.g. Large pile near junction, not collected for 4 days...",
        max_chars=500, height=100)
    severity = st.select_slider("Severity",
        options=["Minor","Moderate","Serious","Critical"],value="Moderate")
    contact  = st.text_input("Phone (optional)",placeholder="+91 XXXXX XXXXX")

    st.markdown("---")
    if st.button("📤  Submit Report", type="primary", use_container_width=True):
        if selected_area=="-- Select area --":
            st.error("Please select your area.")
        elif issue_type=="-- Select --":
            st.error("Please select the issue type.")
        elif not description.strip():
            st.error("Please describe the issue.")
        else:
            report = {
                "report_id":f"RPT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "timestamp":datetime.now().isoformat(),
                "area":selected_area,"issue_type":issue_type,
                "description":description,"severity":severity,
                "contact":contact or "Not provided",
                "has_photo":photo is not None,"status":"Pending"
            }
            rlist=[]
            if os.path.exists(REPORTS_FILE):
                try:
                    with open(REPORTS_FILE) as f: rlist=json.load(f)
                except: pass
            rlist.append(report)
            os.makedirs(os.path.dirname(REPORTS_FILE),exist_ok=True)
            with open(REPORTS_FILE,"w") as f: json.dump(rlist,f,indent=2)

            st.markdown(f"""
            <div class="success-box">
              <div style="font-size:1.2rem;font-weight:700;margin-bottom:8px;">
                ✅ Report submitted successfully</div>
              <div style="font-size:0.9rem;line-height:1.8;">
                <b>ID:</b> {report['report_id']}<br>
                <b>Area:</b> {selected_area}<br>
                <b>Issue:</b> {issue_type}<br>
                <b>Severity:</b> {severity}
              </div>
              <div style="margin-top:12px;font-size:0.85rem;color:#2d6a4f;">
                Thank you for helping keep Bangalore clean 🌿
              </div>
            </div>""", unsafe_allow_html=True)

            area_row = routes[routes["area_name"]==selected_area].dropna(
                subset=["Latitude","Longitude"])
            if not area_row.empty:
                lat=area_row.iloc[0]["Latitude"]
                lon=area_row.iloc[0]["Longitude"]
                rm=folium.Map(location=[lat,lon],zoom_start=14,
                              tiles="OpenStreetMap")
                folium.Marker([lat,lon],popup=selected_area,
                    icon=folium.Icon(color="red",icon="exclamation-sign")
                ).add_to(rm)
                st.markdown("**📍 Report location**")
                st_folium(rm,width=None,height=280)

# ============================================================
# PAGE — CITIZEN REPORTS
# ============================================================

elif page == "📋  Citizen Reports":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\','
                'serif;font-weight:400;">Citizen Reports</h2>',
                unsafe_allow_html=True)

    if not os.path.exists(REPORTS_FILE):
        st.info("No citizen reports yet. Use **📸 Report Waste** to submit one.")
    else:
        try:
            with open(REPORTS_FILE) as f: rlist=json.load(f)
            if not rlist:
                st.info("No reports yet.")
            else:
                rdf=pd.DataFrame(rlist)
                m1,m2,m3,m4=st.columns(4)
                m1.metric("Total Reports",len(rdf))
                m2.metric("Critical",
                    len(rdf[rdf["severity"]=="Critical"])
                    if "severity" in rdf.columns else 0)
                m3.metric("With Photos",
                    len(rdf[rdf["has_photo"]==True])
                    if "has_photo" in rdf.columns else 0)
                m4.metric("Areas Covered",
                    rdf["area"].nunique() if "area" in rdf.columns else 0)
                st.markdown("---")
                show_cols=[c for c in
                    ["report_id","timestamp","area","issue_type","severity","status"]
                    if c in rdf.columns]
                st.dataframe(rdf[show_cols],use_container_width=True,
                             hide_index=True,height=400)
                if "severity" in rdf.columns:
                    fig=px.bar(rdf["severity"].value_counts().reset_index(),
                        x="severity",y="count",title="Reports by Severity",
                        color="severity",
                        color_discrete_map={
                            "Critical":"#e63946","Serious":"#f4a261",
                            "Moderate":"#e9c46a","Minor":"#52b788"})
                    fig.update_layout(showlegend=False,
                        plot_bgcolor="white",paper_bgcolor="white")
                    st.plotly_chart(fig,use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.markdown(f"""
<div style="text-align:center;color:#aaa;font-size:0.8rem;padding:8px 0;">
  ♻️ Bengaluru Brain — Urban Waste Intelligence &nbsp;·&nbsp;
  Sentinel-2 · OSM · Random Forest · OR-Tools &nbsp;·&nbsp;
  {datetime.now().strftime('%d %b %Y')}
</div>
""", unsafe_allow_html=True)