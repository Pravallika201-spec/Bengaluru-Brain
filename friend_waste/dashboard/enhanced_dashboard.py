"""
=========================================================
Urban Predictive Intelligence System
Enhanced Dashboard with All New Features
=========================================================

Enhanced Streamlit dashboard integrating all 12 enhancement modules:
- Clickable area details with satellite imagery and indices
- Enhanced route optimization with nearest neighbor routing
- Weather integration display
- Citizen reporting interface
- Social media event monitoring
- Fleet maintenance dashboard
- Land use change detection
- Model validation results
- Uncertainty quantification display
- Scenario analysis interface
- Advanced temporal predictions
- Multi-sensor satellite fusion
=========================================================
"""

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
import requests

# Try to import optional dependencies
try:
    import plotly.figure_factory as ff
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("Plotly figure factory not available")

# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
SATELLITE_OUTPUT  = os.path.join(BASE_DIR, "satellite", "outputs")
PROCESSED_DIR     = os.path.join(BASE_DIR, "data", "processed")
DATA_DIR           = os.path.join(BASE_DIR, "data")
FLEET_DIR          = os.path.join(PROCESSED_DIR, "fleet")
VALIDATION_DIR      = os.path.join(PROCESSED_DIR, "validation")
SCENARIO_DIR        = os.path.join(PROCESSED_DIR, "scenarios")
UNCERTAINTY_DIR     = os.path.join(PROCESSED_DIR, "uncertainty_analysis")
LANDUSE_DIR         = os.path.join(PROCESSED_DIR, "landuse_changes")

# Original files
EVENT_FILE             = os.path.join(SATELLITE_OUTPUT, "bengaluru_events.csv")
EVENT_IMPACT_FILE      = os.path.join(SATELLITE_OUTPUT, "bengaluru_event_grid_impact.csv")
EVENT_WASTE_FILE       = os.path.join(SATELLITE_OUTPUT, "bengaluru_event_aware_waste_predictions.csv")
AREA_OVERFLOW_FILE     = os.path.join(PROCESSED_DIR,    "bengaluru_area_overflow_predictions.gpkg")
EVENT_AWARE_ROUTE_FILE = os.path.join(PROCESSED_DIR,    "bengaluru_event_aware_area_collection_routes.csv")
ORTOOLS_ROUTE_FILE     = os.path.join(SATELLITE_OUTPUT, "bengaluru_ortools_vehicle_routes.csv")
SAT_FEATURES_FILE      = os.path.join(SATELLITE_OUTPUT, "bengaluru_satellite_features.csv")
GRID_AREA_MAPPING_FILE = os.path.join(PROCESSED_DIR,    "bengaluru_grid_area_mapping.csv")
PERCAPITA_PREDICTIONS_FILE = os.path.join(PROCESSED_DIR, "bengaluru_percapita_waste_predictions.csv")
POI_REGRESSION_PREDICTIONS_FILE = os.path.join(PROCESSED_DIR, "bengaluru_poi_regression_predictions.csv")
POI_REGRESSION_CHART_FILE = os.path.join(PROCESSED_DIR, "poi_regression_comparison.png")
TREND_EARLY_WARNING_FILE = os.path.join(PROCESSED_DIR, "bengaluru_trend_early_warning.csv")
TREND_BACKTEST_CHART_FILE = os.path.join(PROCESSED_DIR, "trend_backtest_validation.png")
REPORTS_FILE           = os.path.join(BASE_DIR, "data", "citizen_reports.json")
REPORTS_PHOTOS_DIR     = os.path.join(BASE_DIR, "data", "citizen_report_photos")

# New files from enhancements
MULTI_SENSOR_FILE     = os.path.join(PROCESSED_DIR, "multi_sensor_grid_features.csv")
WEATHER_FILE           = os.path.join(PROCESSED_DIR, "bengaluru_weather_data.json")
SOCIAL_EVENTS_FILE      = os.path.join(PROCESSED_DIR, "social_events.csv")
FLEET_DATA_FILE        = os.path.join(FLEET_DIR, "fleet_data.csv")
MAINTENANCE_SCHEDULE   = os.path.join(FLEET_DIR, "maintenance_schedule.csv")
LANDUSE_CHANGES_FILE   = os.path.join(LANDUSE_DIR, "detected_landuse_changes.csv")
VALIDATION_RESULTS     = os.path.join(VALIDATION_DIR, "validation_results.json")
UNCERTAINTY_RESULTS    = os.path.join(UNCERTAINTY_DIR, "predictions_with_uncertainty.csv")
SCENARIO_RESULTS       = os.path.join(SCENARIO_DIR, "scenario_analysis_results.json")

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Bengaluru Brain — Enhanced Waste Intelligence",
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
.image-container{background:white;border-radius:12px;padding:16px;
  box-shadow:0 2px 8px rgba(0,0,0,0.06);margin:16px 0;}
.image-placeholder{background:#f8f9fa;border:2px dashed #dee2e6;border-radius:8px;
  padding:20px;text-align:center;color:#888;font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data():
    """Load all project data files."""
    try:
        events = pd.read_csv(EVENT_FILE) if os.path.exists(EVENT_FILE) else pd.DataFrame()
        event_impact = pd.read_csv(EVENT_IMPACT_FILE) if os.path.exists(EVENT_IMPACT_FILE) else pd.DataFrame()
        event_waste = pd.read_csv(EVENT_WASTE_FILE) if os.path.exists(EVENT_WASTE_FILE) else pd.DataFrame()
        areas = gpd.read_file(AREA_OVERFLOW_FILE, layer="area_overflow_predictions") if os.path.exists(AREA_OVERFLOW_FILE) else gpd.GeoDataFrame()
        routes = pd.read_csv(EVENT_AWARE_ROUTE_FILE) if os.path.exists(EVENT_AWARE_ROUTE_FILE) else pd.DataFrame()
        ortools_routes_raw = pd.read_csv(ORTOOLS_ROUTE_FILE) if os.path.exists(ORTOOLS_ROUTE_FILE) else pd.DataFrame()
        sat_features = pd.read_csv(SAT_FEATURES_FILE) if os.path.exists(SAT_FEATURES_FILE) else pd.DataFrame()
        grid_area_mapping = pd.read_csv(GRID_AREA_MAPPING_FILE) if os.path.exists(GRID_AREA_MAPPING_FILE) else pd.DataFrame()

        citizen_reports_list = []
        if os.path.exists(REPORTS_FILE):
            try:
                with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
                    citizen_reports_list = json.load(f)
            except Exception:
                citizen_reports_list = []
        citizen_reports = pd.DataFrame(citizen_reports_list) if citizen_reports_list else pd.DataFrame()

        percapita_predictions = pd.read_csv(PERCAPITA_PREDICTIONS_FILE) if os.path.exists(PERCAPITA_PREDICTIONS_FILE) else pd.DataFrame()
        poi_regression_predictions = pd.read_csv(POI_REGRESSION_PREDICTIONS_FILE) if os.path.exists(POI_REGRESSION_PREDICTIONS_FILE) else pd.DataFrame()
        trend_early_warning = pd.read_csv(TREND_EARLY_WARNING_FILE) if os.path.exists(TREND_EARLY_WARNING_FILE) else pd.DataFrame()
        
        # Load new enhancement data
        multi_sensor = pd.read_csv(MULTI_SENSOR_FILE) if os.path.exists(MULTI_SENSOR_FILE) else pd.DataFrame()
        weather_data = json.load(open(WEATHER_FILE, encoding='utf-8')) if os.path.exists(WEATHER_FILE) else {}
        social_events = pd.read_csv(SOCIAL_EVENTS_FILE) if os.path.exists(SOCIAL_EVENTS_FILE) else pd.DataFrame()
        fleet_data = pd.read_csv(FLEET_DATA_FILE) if os.path.exists(FLEET_DATA_FILE) else pd.DataFrame()
        maintenance_schedule = pd.read_csv(MAINTENANCE_SCHEDULE) if os.path.exists(MAINTENANCE_SCHEDULE) else pd.DataFrame()
        landuse_changes = pd.read_csv(LANDUSE_CHANGES_FILE) if os.path.exists(LANDUSE_CHANGES_FILE) else pd.DataFrame()
        validation_results = json.load(open(VALIDATION_RESULTS, encoding='utf-8')) if os.path.exists(VALIDATION_RESULTS) else {}
        uncertainty_results = pd.read_csv(UNCERTAINTY_RESULTS) if os.path.exists(UNCERTAINTY_RESULTS) else pd.DataFrame()
        scenario_results = json.load(open(SCENARIO_RESULTS, encoding='utf-8')) if os.path.exists(SCENARIO_RESULTS) else {}
        
        return (events, event_impact, event_waste, areas, routes, ortools_routes_raw, sat_features, 
                grid_area_mapping, citizen_reports, percapita_predictions, poi_regression_predictions,
                trend_early_warning,
                multi_sensor, weather_data, social_events, fleet_data, 
                maintenance_schedule, landuse_changes, validation_results, 
                uncertainty_results, scenario_results)
    except Exception as e:
        st.error(f"Unable to load project output files: {e}")
        return None

# Load data
data = load_data()
if data:
    (events, event_impact, event_waste, areas, routes, ortools_routes_raw, sat_features, 
     grid_area_mapping, citizen_reports, percapita_predictions, poi_regression_predictions,
     trend_early_warning,
     multi_sensor, weather_data, social_events, fleet_data, 
     maintenance_schedule, landuse_changes, validation_results, 
     uncertainty_results, scenario_results) = data
else:
    st.error("Failed to load data. Please ensure output files exist.")
    st.stop()

# Numeric fix for routes
if not routes.empty:
    for col in ["event_aware_risk_score","distance_from_previous_km",
                "route_total_distance_km","event_affected_grids",
                "critical_grids","Latitude","Longitude"]:
        if col in routes.columns:
            routes[col] = pd.to_numeric(routes[col], errors="coerce")

# Normalize the real OR-Tools capacitated-VRP output onto the same column names
# the rest of the dashboard already expects (truck_id, route_sequence, Latitude/
# Longitude, overflow_risk, route_total_distance_km) so both routing engines can
# be shown with the same display functions.
def normalize_ortools_routes(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    rename_map = {
        "vehicle_id": "truck_id",
        "route_order": "route_sequence",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "area_risk": "overflow_risk",
        "vehicle_route_distance_km": "route_total_distance_km",
        "vehicle_total_waste_kg": "route_total_waste_kg",
        "predicted_waste_kg": "event_adjusted_waste_kg",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if "truck_id" in df.columns:
        df["truck_id"] = df["truck_id"].apply(
            lambda v: f"OR_TRUCK_{int(v):02d}" if pd.notna(v) else v)
    for col in ["route_total_distance_km", "distance_from_previous_km", "Latitude", "Longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

ortools_routes = normalize_ortools_routes(ortools_routes_raw)

# Build area centroid lookup
if not areas.empty:
    areas_geo = areas.copy()
    areas_geo = areas_geo.to_crs("EPSG:32643")
    areas_geo["centroid"] = areas_geo.geometry.centroid
    areas_geo = areas_geo.to_crs("EPSG:4326")
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

AVG_TRUCK_SPEED_KMH = 22  # rough average incl. city stop-and-go, for ETA estimates

def haversine_km(lat1, lon1, lat2, lon2):
    """Real ground distance in km between two lat/lon points (not raw degree math)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def eta_minutes(distance_km):
    if distance_km is None:
        return None
    return max(1, round(distance_km / AVG_TRUCK_SPEED_KMH * 60))

# Stats calculations
areas_monitored  = areas["area_name"].nunique() if not areas.empty else 0
affected_grids   = int(event_waste["event_affected"].sum()) if not event_waste.empty else 0
priority_areas   = routes["area_name"].nunique() if not routes.empty else 0
critical_areas   = routes[routes["overflow_risk"]=="CRITICAL"]["area_name"].nunique() if not routes.empty else 0
high_areas       = routes[routes["overflow_risk"]=="HIGH"]["area_name"].nunique() if not routes.empty else 0
total_route_dist = (routes.groupby("truck_id")["route_total_distance_km"].first().sum()) if not routes.empty else 0
baseline_waste   = event_waste["predicted_daily_waste_kg"].sum() if not event_waste.empty else 0
additional_waste = event_waste["additional_event_waste_kg"].sum() if not event_waste.empty else 0
event_inc_pct    = (additional_waste/baseline_waste*100) if baseline_waste>0 else 0

# Rough estimate of waste per monitored grid cell, citywide — used to estimate an
# area's load for truck-capacity planning, since no direct per-area waste figure exists
AVG_WASTE_PER_GRID_KG = (baseline_waste / len(event_waste)) if not event_waste.empty and len(event_waste) > 0 else 0

route_ids  = sorted(routes["truck_id"].unique()) if not routes.empty else []
labels     = {tid: f"Route {i+1}" for i,tid in enumerate(route_ids)}
rev_labels = {v:k for k,v in labels.items()}

def find_col(df, candidates):
    """Case-insensitive lookup for the first matching column name in a DataFrame."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None

GRID_ID_CANDIDATES = ["Grid_ID", "grid_id", "GridID", "grid_cell_id", "cell_id"]

def classify_land_use(ndvi, ndbi, ndwi):
    """
    Rough land-cover classification from satellite indices. This is a
    SNAPSHOT classification of current land cover — not a change-over-time
    detection, since only one satellite pass is available.
    """
    if pd.isna(ndvi) or pd.isna(ndbi):
        return "Unknown"
    if pd.notna(ndwi) and ndwi > 0.15:
        return "Water / Moisture-rich"
    if ndvi > 0.35:
        return "Vegetated / Green"
    if ndbi > 0.12 and ndvi < 0.15:
        return "Dense Built-up"
    if ndbi > 0.05:
        return "Mixed Urban"
    return "Sparse / Transitional"

def build_land_use_profile():
    """
    Per-area average NDVI/NDBI/NDWI, joined via the grid-area mapping file
    (Grid_ID -> area_name) rather than a nearest-neighbor approximation —
    this is the same join the rest of the pipeline already uses, so it's
    exact rather than approximate.
    """
    if sat_features.empty or grid_area_mapping.empty:
        return pd.DataFrame()

    sf_id_col = find_col(sat_features, GRID_ID_CANDIDATES)
    gm_id_col = find_col(grid_area_mapping, GRID_ID_CANDIDATES)
    gm_area_col = find_col(grid_area_mapping, ["area_name"])

    if not (sf_id_col and gm_id_col and gm_area_col):
        return pd.DataFrame()

    merged = sat_features.merge(
        grid_area_mapping[[gm_id_col, gm_area_col]].rename(
            columns={gm_id_col: "Grid_ID", gm_area_col: "area_name"}),
        left_on=sf_id_col, right_on="Grid_ID", how="inner"
    )

    if merged.empty:
        return pd.DataFrame()

    agg_cols = {}
    if "NDVI" in merged.columns: agg_cols["NDVI"] = ("NDVI", "mean")
    if "NDBI" in merged.columns: agg_cols["NDBI"] = ("NDBI", "mean")
    if "NDWI" in merged.columns: agg_cols["NDWI"] = ("NDWI", "mean")
    if not agg_cols:
        return pd.DataFrame()

    profile = merged.groupby("area_name").agg(
        **agg_cols, Grid_Cells=("Grid_ID", "count")
    ).reset_index()

    profile["Land_Use_Category"] = profile.apply(
        lambda r: classify_land_use(
            r.get("NDVI"), r.get("NDBI"), r.get("NDWI")), axis=1)

    return profile

land_use_profile = build_land_use_profile()

def find_grid_coords_lookup():
    """
    bengaluru_satellite_features.csv has no lat/lon of its own — only Grid_ID and
    band/index values. Look across the other grid-level files already loaded for one
    that has both a grid-id column and coordinates, so we can join them in by Grid_ID.
    Returns a DataFrame with columns [Grid_ID, Latitude, Longitude], or None.
    """
    for df in (event_waste, multi_sensor, event_impact):
        if df is None or df.empty:
            continue
        id_col  = find_col(df, GRID_ID_CANDIDATES)
        lat_col = find_col(df, ["Latitude", "lat"])
        lon_col = find_col(df, ["Longitude", "lon", "lng"])
        if id_col and lat_col and lon_col:
            return (df[[id_col, lat_col, lon_col]]
                    .rename(columns={id_col: "Grid_ID", lat_col: "Latitude", lon_col: "Longitude"})
                    .dropna()
                    .drop_duplicates(subset="Grid_ID"))
    return None

def compute_area_satellite_indices(area_name, lat_a, lon_a):
    """
    Resolve NDVI/NDBI/NDWI for the 10 satellite grid cells nearest an area's centroid.
    bengaluru_satellite_features.csv has no coordinates of its own, so this borrows them
    via Grid_ID from another grid-level file when possible, and falls back to a citywide
    average (with a note) when it can't.
    Returns (ndvi_avg, ndbi_avg, ndwi_avg, coverage_note, has_data).
    """
    if sat_features.empty:
        return None, None, None, None, False

    sf_lat_col = find_col(sat_features, ["Latitude", "lat"])
    sf_lon_col = find_col(sat_features, ["Longitude", "lon", "lng"])
    working = sat_features
    coverage_note = None

    if not (sf_lat_col and sf_lon_col):
        grid_id_col = find_col(sat_features, GRID_ID_CANDIDATES)
        coord_lookup = find_grid_coords_lookup()
        if grid_id_col and coord_lookup is not None:
            working = sat_features.merge(
                coord_lookup, left_on=grid_id_col, right_on="Grid_ID", how="left"
            )
            if working["Latitude"].notna().any():
                sf_lat_col, sf_lon_col = "Latitude", "Longitude"
                working = working.dropna(subset=["Latitude", "Longitude"])

    if sf_lat_col and sf_lon_col:
        nearby = working.copy()
        nearby["dist"] = ((nearby[sf_lat_col]-lat_a)**2 + (nearby[sf_lon_col]-lon_a)**2)**0.5
        nearby = nearby.nsmallest(10, "dist")
    else:
        nearby = sat_features.copy()
        coverage_note = (
            "The satellite grid cells aren't geo-tagged, and no other file lets me "
            f"match them to {area_name} specifically — these are citywide averages "
            "across all monitored grid cells, not this ward alone."
        )

    if nearby.empty:
        return None, None, None, coverage_note, False

    ndvi_avg = nearby["NDVI"].mean() if "NDVI" in nearby.columns else None
    ndbi_avg = nearby["NDBI"].mean() if "NDBI" in nearby.columns else None
    ndwi_avg = nearby["NDWI"].mean() if "NDWI" in nearby.columns else None
    return ndvi_avg, ndbi_avg, ndwi_avg, coverage_note, True

def build_risk_factors(area_name, risk, area_info, in_priority, ndvi_avg, ndbi_avg):
    """Assemble a short, human-readable list of why an area is flagged at its current risk level."""
    factors = []

    priority = area_info.get('Collection_Priority')
    if priority is not None and pd.notna(priority):
        factors.append(f"Ranked priority {priority} in today's collection plan")

    if in_priority:
        factors.append("Included in today's optimized collection routes")

    if not events.empty and "area_name" in events.columns:
        area_events = events[events["area_name"] == area_name]
        if not area_events.empty:
            ev_col = find_col(area_events, ["event_type", "event_name"])
            if ev_col:
                names = area_events[ev_col].dropna().unique().tolist()
                if names:
                    factors.append(f"Nearby event increasing waste load: {', '.join(names[:2])}")

    if not landuse_changes.empty and "area_name" in landuse_changes.columns:
        area_changes = landuse_changes[landuse_changes["area_name"] == area_name]
        if not area_changes.empty and "waste_impact_factor" in area_changes.columns:
            up_changes = area_changes[area_changes["waste_impact_factor"] > 1.1]
            if not up_changes.empty:
                factors.append(
                    f"Recent land-use change increasing waste generation "
                    f"({len(up_changes)} change{'s' if len(up_changes) != 1 else ''})")

    if ndbi_avg is not None and ndbi_avg > 0.1:
        factors.append(f"High built-up density nearby (NDBI {ndbi_avg:.2f}) — dense development, less green buffer")
    if ndvi_avg is not None and ndvi_avg < 0.1:
        factors.append(f"Very limited vegetation cover nearby (NDVI {ndvi_avg:.2f})")

    if not factors:
        factors.append(
            f"Flagged {risk} by the overflow prediction model based on recent "
            "collection history and grid-level trends")

    return factors

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
       text-transform:uppercase;letter-spacing:0.08em;">Enhanced Waste Intelligence</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

# Sidebar shows only the modules that are actually live
page = st.sidebar.radio("", [
    "Overview",
    "Risk Map",
    "Optimized Routes",
    "Event Intelligence",
    "Early Warning & Citizen Reports",
], key="active_page")
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"<div style='font-size:0.78rem;opacity:0.5;'>"
    f"Updated {datetime.now().strftime('%d %b %Y  %H:%M')}</div>",
    unsafe_allow_html=True)

# ============================================================
# ============================================================
# HELPER FUNCTIONS
# ============================================================

def display_area_details(area_name):
    """Display detailed information for selected area including satellite imagery and indices."""
    st.markdown(f"### 📍 {area_name} - Detailed Analysis")
    
    # Get area information
    area_info = areas[areas["area_name"]==area_name].iloc[0]
    risk = area_info["Area_Overflow_Risk"]
    rc = RISK_COLORS.get(risk,"#888")
    
    lat_a = centroids[centroids["area_name"]==area_name]["Latitude"].values[0]
    lon_a = centroids[centroids["area_name"]==area_name]["Longitude"].values[0]
    
    # Risk info panel
    st.markdown(f"""
    <div class="info-panel {risk.lower()}">
      <h3>📍 {area_name}</h3>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px;">
        <div>
          <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;margin-bottom:4px;">
            Risk Level</div>
          <span class="badge badge-{risk.lower()}">{risk}</span>
        </div>
        <div>
          <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;margin-bottom:4px;">
            Priority</div>
          <div style="font-weight:600;color:#1b4332;">{area_info.get('Collection_Priority','—')}</div>
        </div>
        <div>
          <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;margin-bottom:4px;">
            Grid Cells</div>
          <div style="font-weight:600;color:#1b4332;">{area_info.get('Grid_Cell_Count','—'):,}</div>
        </div>
        <div>
          <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;margin-bottom:4px;">
            Status</div>
          <div style="font-weight:600;">{collection_status(risk)}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # "Why is this area flagged" factor breakdown
    in_priority = area_name in routes["area_name"].values if not routes.empty else False
    ndvi_avg, ndbi_avg, ndwi_avg, sat_coverage_note, has_sat_data = compute_area_satellite_indices(
        area_name, lat_a, lon_a)
    risk_factors = build_risk_factors(area_name, risk, area_info, in_priority, ndvi_avg, ndbi_avg)

    st.markdown(f"""
    <div class="info-panel {risk.lower()}">
      <h3>🧭 Why {area_name} is flagged {risk}</h3>
      <ul style="margin:0;padding-left:20px;font-size:0.92rem;color:#333;line-height:1.75;">
        {''.join(f'<li>{f}</li>' for f in risk_factors)}
      </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Enhanced Satellite Analysis Section
    st.markdown("#### 🛰️ Satellite Imagery & Analysis")
    
    tab1, tab5 = st.tabs(["Satellite Indices", "Citizen Reports"])
    
    with tab1:
        # Live satellite image of the area
        st.markdown("##### Satellite View")
        sat_map = folium.Map(
            location=[lat_a, lon_a], zoom_start=17,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery"
        )
        folium.CircleMarker(
            location=[lat_a, lon_a], radius=8, color="#ffffff", weight=2,
            fill=True, fill_color="#e63946", fill_opacity=0.9, tooltip=area_name
        ).add_to(sat_map)
        st_folium(sat_map, width=None, height=320, key=f"sat_img_{area_name}")
        st.markdown(
            f"<div style='font-size:0.75rem;color:#888;margin:4px 0 18px;'>"
            f"Live satellite basemap (Esri World Imagery) · as of "
            f"{datetime.now().strftime('%d %b %Y %H:%M')}</div>",
            unsafe_allow_html=True)

        # Satellite indices chart
        st.markdown("##### NDVI / NDBI / NDWI Analysis")

        if sat_coverage_note:
            st.info(sat_coverage_note)

        if has_sat_data:
            ndvi_avg = ndvi_avg or 0
            ndbi_avg = ndbi_avg or 0
            ndwi_avg = ndwi_avg or 0

            m1,m2,m3 = st.columns(3)
            m1.metric("NDVI — Vegetation", f"{ndvi_avg:.3f}")
            m2.metric("NDBI — Built-up", f"{ndbi_avg:.3f}")
            m3.metric("NDWI — Moisture", f"{ndwi_avg:.3f}")

            # Enhanced visualization
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=["NDVI (Vegetation)", "NDBI (Built-up)", "NDWI (Moisture)"],
                y=[ndvi_avg, ndbi_avg, ndwi_avg],
                marker_color=["#52b788","#e63946","#457b9d"],
                text=[f"{ndvi_avg:.3f}",f"{ndbi_avg:.3f}",f"{ndwi_avg:.3f}"],
                textposition="outside",
                textfont=dict(size=12, color="#1b4332")
            ))
            fig.update_layout(
                title=f"Satellite Indices - {area_name}",
                plot_bgcolor="white", paper_bgcolor="white",
                height=350, margin=dict(t=40,b=20,l=20,r=20),
                font_family="Inter",
                yaxis=dict(range=[-1,1], title="Index Value"),
                annotations=[
                    dict(x=0,y=-0.15,xref="x",yref="paper",
                         text="Vegetation Density",showarrow=False,
                         font=dict(size=11,color="#888")),
                    dict(x=1,y=-0.15,xref="x",yref="paper",
                         text="Built-up Density",showarrow=False,
                         font=dict(size=11,color="#888")),
                    dict(x=2,y=-0.15,xref="x",yref="paper",
                         text="Moisture Index",showarrow=False,
                         font=dict(size=11,color="#888")),
                ]
            )
            st.plotly_chart(fig, use_container_width=True)

            # Detailed interpretation
            st.markdown(f"""
            <div class="info-box">
              🌱 <b>NDVI {ndvi_avg:.3f}</b> — 
              {'🌳 High vegetation - green area' if ndvi_avg > 0.3 else '🏙️ Urban area - limited vegetation' if ndvi_avg > 0.1 else '🏢 Dense urban - very limited vegetation'}<br>
              🏙️ <b>NDBI {ndbi_avg:.3f}</b> — 
              {'🏢 High built-up density' if ndbi_avg > 0.1 else '🌳 Moderate built-up area'}<br>
              💧 <b>NDWI {ndwi_avg:.3f}</b> — 
              {'💧 High moisture content' if ndwi_avg > 0.1 else '🏜️ Normal moisture levels'}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("Satellite features data not available")
    
    with tab5:
        st.markdown("##### Citizen-Submitted Reports for This Ward")

        if citizen_reports.empty:
            st.info("No citizen reports have been submitted yet.")
        else:
            ward_reports = citizen_reports[citizen_reports.get("matched_ward") == area_name]
            if ward_reports.empty:
                st.info(f"No citizen reports matched to {area_name} yet.")
            else:
                ward_reports = ward_reports.sort_values("submitted_at", ascending=False)
                st.markdown(f"**{len(ward_reports)} report(s)** submitted for this ward.")
                for _, rep in ward_reports.iterrows():
                    rc1, rc2 = st.columns([1, 3])
                    with rc1:
                        if rep.get("photo_path") and os.path.exists(str(rep["photo_path"])):
                            st.image(rep["photo_path"], use_container_width=True)
                        else:
                            st.caption("No photo")
                    with rc2:
                        sev = rep.get("severity", "medium")
                        submitted_dt = rep.get("submitted_at", "")
                        st.markdown(f"""
                        <div style="padding:4px 0;">
                          <span class="badge badge-{sev}">{sev}</span>
                          <b style="margin-left:8px;color:#1b4332;">{rep.get('waste_type', 'garbage')}</b>
                          <div style="font-size:0.82rem;color:#888;margin-top:2px;">{submitted_dt}</div>
                          <div style="font-size:0.85rem;color:#555;margin-top:4px;">
                            {rep.get('landmark') or ''} {('— ' + rep.get('description')) if rep.get('description') else ''}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<hr style='margin:8px 0;border-color:#eee;'>", unsafe_allow_html=True)

# ============================================================
# PAGE — ENHANCED RISK MAP
# ============================================================


def display_enhanced_routes(start_area, routes, areas, centroids, route_ids, labels):
    """
    Dispatch-style view: a ranked list of nearby critical areas with real distance/ETA
    on the left, a live map with numbered stops in the middle, and a route-builder
    action panel on the right — mirroring a live-dispatch UI rather than a raw table.
    """
    start_info = areas[areas["area_name"]==start_area].iloc[0]
    start_lat = centroids[centroids["area_name"]==start_area]["Latitude"].values[0]
    start_lon = centroids[centroids["area_name"]==start_area]["Longitude"].values[0]
    start_risk = start_info.get("Area_Overflow_Risk", "LOW")

    st.markdown(f"""
    <div class="info-panel {start_risk.lower()}">
      <h3>📍 Starting Point: {start_area}</h3>
      <div style="font-size:0.88rem;color:#555;">
        Current risk: <span class="badge badge-{start_risk.lower()}">{start_risk}</span>
        &nbsp;·&nbsp; {start_lat:.4f}, {start_lon:.4f}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Rank every other area — either by risk severity first, or purely by distance
    RISK_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_other_areas = [a for a in routes["area_name"].dropna().unique() if a != start_area]
    distances = []
    for area in all_other_areas:
        match = centroids[centroids["area_name"]==area]
        if match.empty:
            continue  # this area isn't in the geo file — skip rather than crash
        area_lat = match["Latitude"].values[0]
        area_lon = match["Longitude"].values[0]
        area_row = routes[routes["area_name"]==area].iloc[0]
        area_geo_match = areas[areas["area_name"]==area]
        grid_count = (area_geo_match["Grid_Cell_Count"].values[0]
                      if not area_geo_match.empty and "Grid_Cell_Count" in area_geo_match.columns
                      else None)
        est_waste_kg = (grid_count * AVG_WASTE_PER_GRID_KG
                         if grid_count is not None and AVG_WASTE_PER_GRID_KG else None)
        distances.append({
            'area': area, 'lat': area_lat, 'lon': area_lon,
            'distance_km': haversine_km(start_lat, start_lon, area_lat, area_lon),
            'risk': area_row["overflow_risk"],
            'priority': (
                area_row.get("collection_priority")
                if pd.notna(area_row.get("collection_priority", None))
                else (f"score {area_row['routing_priority']:.2f}" if "routing_priority" in area_row and pd.notna(area_row.get("routing_priority")) else "—")
            ),
            'est_waste_kg': est_waste_kg,
        })

    sort_mode = st.radio(
        "Sort nearest wards by",
        ["Risk level (severity first)", "Distance (nearest first)"],
        horizontal=True,
        key=f"sort_mode_{start_area}"
    )
    if sort_mode.startswith("Distance"):
        distances.sort(key=lambda x: x['distance_km'])
        sort_note = "showing the 10 closest, regardless of risk level."
    else:
        distances.sort(key=lambda x: (RISK_RANK.get(x['risk'], 4), x['distance_km']))
        sort_note = "showing the 10 nearest, highest-risk first."
    top10 = distances[:10]

    crit_count = sum(1 for d in distances if d['risk'] == "CRITICAL")
    high_count = sum(1 for d in distances if d['risk'] == "HIGH")
    st.caption(f"{len(distances)} other wards found ({crit_count} critical, {high_count} high) — {sort_note}")


    if not top10:
        st.warning("No high-priority wards found in routes")
        return

    list_col, map_col, action_col = st.columns([1.15, 1.7, 1.05])

    # LEFT — ranked list with distance + ETA, like a dispatch panel
    with list_col:
        st.markdown("#### Nearest Critical Wards")
        for i, d in enumerate(top10):
            eta = eta_minutes(d['distance_km'])
            waste_line = f" &nbsp;·&nbsp; ~{d['est_waste_kg']:,.0f} kg" if d['est_waste_kg'] else ""
            st.markdown(f"""
            <div style="background:white;border-radius:12px;padding:11px 14px;margin-bottom:9px;
                 border-left:4px solid {RISK_COLORS.get(d['risk'],'#888')};box-shadow:0 1px 6px rgba(0,0,0,0.05);">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                <b style="color:#1b4332;font-size:0.88rem;">{i+1}. {d['area']}</b>
                <span class="badge badge-{d['risk'].lower()}" style="flex:none;">{d['risk']}</span>
              </div>
              <div style="font-size:0.76rem;color:#888;margin-top:4px;">
                {d['distance_km']:.1f} km &nbsp;·&nbsp; ETA {eta} min{waste_line}
              </div>
            </div>
            """, unsafe_allow_html=True)

    # CENTER — live map, numbered stops radiating from the start point
    with map_col:
        st.markdown("#### Live Route Map")
        route_map = folium.Map(location=[start_lat, start_lon], zoom_start=12, tiles="OpenStreetMap")
        folium.Marker(
            location=[start_lat, start_lon],
            icon=folium.Icon(color='green', icon='home'),
            tooltip=f"Start: {start_area}"
        ).add_to(route_map)
        for i, d in enumerate(top10):
            rc = RISK_COLORS.get(d['risk'], '#888')
            folium.PolyLine(
                [[start_lat, start_lon], [d['lat'], d['lon']]],
                color=rc, weight=2, opacity=0.55, dash_array="6,6"
            ).add_to(route_map)
            folium.Marker(
                location=[d['lat'], d['lon']],
                icon=folium.DivIcon(html=f"""
                    <div style="width:26px;height:26px;border-radius:50%;background:{rc};
                        border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,0.3);
                        display:flex;align-items:center;justify-content:center;
                        color:white;font-weight:700;font-size:11px;">{i+1}</div>
                """, icon_size=(26,26), icon_anchor=(13,13)),
                popup=f"{d['area']} — {d['distance_km']:.1f} km, ~{eta_minutes(d['distance_km'])} min"
            ).add_to(route_map)
        if top10:
            route_map.fit_bounds(
                [[start_lat, start_lon]] + [[d['lat'], d['lon']] for d in top10],
                padding=(30, 30)
            )
        st_folium(route_map, width=None, height=440, key=f"nearest_map_{start_area}")

    # RIGHT — build the actual multi-stop route, against a truck capacity
    with action_col:
        st.markdown("#### Build Route")

        has_waste_estimates = AVG_WASTE_PER_GRID_KG > 0
        if has_waste_estimates:
            truck_capacity_kg = st.number_input(
                "Truck capacity (kg)", min_value=500, max_value=20000,
                value=8000, step=500, key=f"capacity_{start_area}"
            )
        else:
            truck_capacity_kg = None

        selected_areas = st.multiselect(
            "Stops to include (uncheck any you don't want on this run)",
            [d['area'] for d in top10],
            default=[d['area'] for d in top10],
            key=f"route_stops_{start_area}"
        )

        if has_waste_estimates:
            selected_load_kg = sum((d['est_waste_kg'] or 0) for d in top10 if d['area'] in selected_areas)
            load_pct = (selected_load_kg / truck_capacity_kg) if truck_capacity_kg else 0
            load_color = "#e63946" if load_pct > 1 else "#f4a261" if load_pct > 0.85 else "#52b788"
            st.markdown(f"""
            <div style="margin-top:4px;">
              <div style="font-size:0.78rem;color:#888;margin-bottom:4px;">
                Estimated load: {selected_load_kg:,.0f} / {truck_capacity_kg:,.0f} kg
              </div>
              <div style="background:#eee;border-radius:6px;height:8px;overflow:hidden;">
                <div style="width:{min(load_pct,1)*100:.0f}%;background:{load_color};height:100%;"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if load_pct > 1:
                st.warning("Estimated load exceeds truck capacity — remove a stop or plan a second run.")
            st.caption("Load estimated from grid-cell count × citywide average waste per cell — not a direct measurement.")

        st.button("🚛 Optimize Route", use_container_width=True, key=f"dispatch_{start_area}")

    if selected_areas:
        display_optimized_route(start_area, selected_areas, distances, routes, centroids, start_lat, start_lon)

def display_optimized_route(start_area, selected_areas, distances, routes, centroids, start_lat, start_lon):
    """Display the optimized multi-stop route with a summary bar, map, and
    stop-by-stop cards that include real leg distance and ETA — not just a
    straight-line distance from the start."""
    selected_area_data = [d for d in distances if d['area'] in selected_areas]

    # Walk the stops in order, accumulating real ground distance leg by leg
    prev_lat, prev_lon = start_lat, start_lon
    cumulative_km = 0.0
    for area_info in selected_area_data:
        leg_km = haversine_km(prev_lat, prev_lon, area_info['lat'], area_info['lon'])
        cumulative_km += leg_km
        area_info['leg_km'] = leg_km
        area_info['cumulative_km'] = cumulative_km
        area_info['cumulative_min'] = eta_minutes(cumulative_km)
        prev_lat, prev_lon = area_info['lat'], area_info['lon']

    total_km = cumulative_km
    total_min = eta_minutes(total_km)

    # Return-to-depot leg — a real collection run comes back, it doesn't just stop
    if selected_area_data:
        last_stop = selected_area_data[-1]
        return_km = haversine_km(last_stop['lat'], last_stop['lon'], start_lat, start_lon)
    else:
        return_km = 0.0
    round_trip_km = total_km + return_km
    round_trip_min = eta_minutes(round_trip_km)

    st.markdown(f"""
    <div class="success-box" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
      <div><b>🚛 Route ready</b> — {start_area} → {len(selected_area_data)} stop{'s' if len(selected_area_data)!=1 else ''} → back to {start_area}</div>
      <div style="font-size:0.9rem;">
        Outbound {total_km:.1f} km (~{total_min} min) &nbsp;·&nbsp;
        Round trip {round_trip_km:.1f} km (~{round_trip_min} min)
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Create route map
    route_map = folium.Map(
        location=[start_lat, start_lon],
        zoom_start=12,
        tiles="OpenStreetMap"
    )

    # Add start point marker
    folium.Marker(
        location=[start_lat, start_lon],
        icon=folium.Icon(color='green', icon='play'),
        popup=f"Start: {start_area}"
    ).add_to(route_map)

    # Route line, in stop order
    route_coords = [(start_lat, start_lon)] + [(a['lat'], a['lon']) for a in selected_area_data]
    folium.PolyLine(
        route_coords,
        color='#1b4332',
        weight=4,
        opacity=0.7,
        tooltip=f"Route from {start_area}"
    ).add_to(route_map)

    # Numbered destination markers, in visiting order
    for i, area_info in enumerate(selected_area_data):
        rc = RISK_COLORS.get(area_info['risk'], "#888")
        folium.Marker(
            location=[area_info['lat'], area_info['lon']],
            icon=folium.DivIcon(html=f"""
                <div style="width:26px;height:26px;border-radius:50%;background:{rc};
                    border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,0.3);
                    display:flex;align-items:center;justify-content:center;
                    color:white;font-weight:700;font-size:11px;">{i+1}</div>
            """, icon_size=(26,26), icon_anchor=(13,13)),
            popup=f"Stop {i+1}: {area_info['area']} — {area_info['risk']}"
        ).add_to(route_map)

    # Dashed return leg from the last stop back to the depot
    if selected_area_data:
        last_stop = selected_area_data[-1]
        folium.PolyLine(
            [(last_stop['lat'], last_stop['lon']), (start_lat, start_lon)],
            color='#1b4332', weight=3, opacity=0.5, dash_array="8,8",
            tooltip=f"Return to {start_area}"
        ).add_to(route_map)

    if selected_area_data:
        route_map.fit_bounds(
            [[start_lat, start_lon]] + [[a['lat'], a['lon']] for a in selected_area_data],
            padding=(30, 30)
        )
    st_folium(route_map, width=None, height=400, key=f"optimized_map_{start_area}")

    # Route details, in visiting order, with real leg distance + running ETA
    st.markdown("### 📋 Route Details")

    for i, area_info in enumerate(selected_area_data):
        st.markdown(f"""
        <div class="info-panel {'high' if area_info['risk'] in ['CRITICAL', 'HIGH'] else 'medium'}">
          <h3>Stop {i+1}: {area_info['area']}</h3>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;">
                Leg Distance
              </div>
              <div style="font-weight:700;">{area_info['leg_km']:.2f} km</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;">
                Arriving By
              </div>
              <div style="font-weight:700;">~{area_info['cumulative_min']} min</div>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;">
                Risk Level
              </div>
              <span class="badge badge-{area_info['risk'].lower()}">{area_info['risk']}</span>
            </div>
            <div>
              <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;color:#888;">
                Priority
              </div>
              <div style="font-weight:700;">{area_info['priority']}</div>
            </div>
          </div>
          <div style="margin-top:8px;font-size:0.88rem;color:#555;font-style:italic;">
            {'⚠️ High priority collection - allocate specialized vehicle' if area_info['risk'] == 'CRITICAL' else '✅ Standard collection'}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Downloadable route sheet — something a driver can actually take with them
    sheet_lines = [
        "BENGALURU BRAIN — COLLECTION ROUTE SHEET",
        f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}",
        f"Start: {start_area}",
        "",
        f"{'Stop':<6}{'Ward':<32}{'Risk':<10}{'Leg (km)':<10}{'Arriving By':<14}",
        "-" * 72,
    ]
    for i, area_info in enumerate(selected_area_data):
        sheet_lines.append(
            f"{i+1:<6}{area_info['area']:<32}{area_info['risk']:<10}"
            f"{area_info['leg_km']:<10.2f}~{area_info['cumulative_min']} min"
        )
    sheet_lines += [
        "-" * 72,
        f"Return to {start_area}: {return_km:.2f} km",
        f"Outbound distance: {total_km:.2f} km (~{total_min} min)",
        f"Round trip: {round_trip_km:.2f} km (~{round_trip_min} min)",
    ]
    st.download_button(
        "📄 Download route sheet",
        data="\n".join(sheet_lines),
        file_name=f"route_sheet_{start_area.replace(' ', '_')}.txt",
        mime="text/plain",
        use_container_width=False,
        key=f"route_sheet_{start_area}"
    )

def display_all_routes(routes, areas, centroids, route_ids, labels):
    """Display existing collection routes — one at a time by default, since showing
    all of them together (15+ overlapping colored trails) is unreadable."""
    st.markdown("### 🛣️ Existing Collection Routes")

    if not route_ids:
        st.info("No routes available yet.")
        return

    # Build a legible label for each route: "Route 3 — 12 stops, 8.4 km"
    route_meta = {}
    for tid in route_ids:
        td = routes[routes["truck_id"] == tid]
        n_stops = td["area_name"].nunique()
        dist = (td["route_total_distance_km"].iloc[0]
                if "route_total_distance_km" in td.columns and not td.empty else None)
        opt_label = f"{labels.get(tid, tid)} — {n_stops} stops" + (f", {dist:.1f} km" if dist is not None else "")
        route_meta[opt_label] = tid

    chosen_labels = st.multiselect(
        "Choose which route(s) to show on the map",
        list(route_meta.keys()),
        default=list(route_meta.keys())[:1]  # one route at a time by default — legible over "show everything"
    )
    chosen_ids = [route_meta[l] for l in chosen_labels]

    if not chosen_ids:
        st.info("Pick at least one route above to see it on the map.")
        return

    m2 = folium.Map(location=[12.9716,77.5946], zoom_start=11, tiles="OpenStreetMap")
    legend_rows = []

    for i, tid in enumerate(route_ids):
        if tid not in chosen_ids:
            continue
        color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
        td    = routes[routes["truck_id"]==tid].sort_values("route_sequence")
        coords= list(zip(td["Latitude"],td["Longitude"]))

        if len(coords)>1:
            plugins.AntPath(
                coords, color=color, weight=4, opacity=0.9, delay=800,
                tooltip=labels.get(tid,tid)
            ).add_to(m2)

        for j,(_,row) in enumerate(td.iterrows()):
            risk   = row["overflow_risk"]
            rc     = RISK_COLORS.get(risk,"#888")
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                icon=folium.DivIcon(html=f"""
                <div style="width:28px;height:28px;border-radius:50%;
                     background:{color};border:3px solid white;
                     box-shadow:0 2px 6px rgba(0,0,0,0.3);
                     display:flex;align-items:center;justify-content:center;
                     color:white;font-weight:700;font-size:11px;">
                  {j+1}
                </div>""", icon_size=(28,28), icon_anchor=(14,14)),
                popup=folium.Popup(
                    f"<b>{row['area_name']}</b><br>"
                    f"{labels.get(tid,tid)} — Stop {j+1}<br>"
                    f"Risk: <b style='color:{rc};'>{risk}</b>",
                    max_width=200)
            ).add_to(m2)

        dist = (td["route_total_distance_km"].iloc[0]
                if "route_total_distance_km" in td.columns and not td.empty else None)
        legend_rows.append((color, labels.get(tid, tid), td["area_name"].nunique(), dist))

    st_folium(m2, width=None, height=480)

    # Color legend — the numbers on the map only make sense once you know which
    # color belongs to which route
    st.markdown("#### Legend")
    legend_html = "".join(
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px;'>"
        f"<span style='width:14px;height:14px;border-radius:50%;background:{c};"
        f"display:inline-block;flex:none;'></span>"
        f"<span style='font-size:0.88rem;color:#333;'>{lbl} — {n} stops"
        f"{f', {d:.1f} km' if d is not None else ''}</span></div>"
        for c, lbl, n, d in legend_rows
    )
    st.markdown(legend_html, unsafe_allow_html=True)

    # Stop-by-stop order in plain text, for anyone who'd rather read than hunt on the map
    st.markdown("#### Stop-by-Stop Order")
    for tid in chosen_ids:
        td = routes[routes["truck_id"]==tid].sort_values("route_sequence")
        with st.expander(f"{labels.get(tid, tid)} — {td['area_name'].nunique()} stops", expanded=len(chosen_ids)==1):
            for j,(_,row) in enumerate(td.iterrows()):
                risk = row["overflow_risk"]
                st.markdown(
                    f"**{j+1}. {row['area_name']}** — "
                    f"<span class='badge badge-{risk.lower()}'>{risk}</span>",
                    unsafe_allow_html=True)

# ============================================================
# PAGE — WEATHER INTEGRATION
# ============================================================


# PAGE — OVERVIEW
# ============================================================

if page == "Overview":

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
        <div class="stat-label">Wards Monitored</div>
        <div class="stat-value">{areas_monitored:,}</div>
        <div class="stat-sub">Across Bengaluru's 369 wards</div>
      </div>
      <div class="stat-card critical">
        <div class="stat-label">Critical Wards</div>
        <div class="stat-value">{critical_areas}</div>
        <div class="stat-sub">Immediate collection needed</div>
      </div>
      <div class="stat-card high">
        <div class="stat-label">High-Risk Wards</div>
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

    # Event intelligence summary
    st.markdown('<div class="section-header">📅 Event Intelligence</div>',
                unsafe_allow_html=True)

    c1,c2,c3 = st.columns(3)
    c1.metric("Tracked events", f"{len(events):,}" if not events.empty else "0")
    c2.metric("Grid cells affected", f"{affected_grids:,}")
    c3.metric("Extra waste from events", f"{event_inc_pct:.1f}% over baseline")

    st.markdown('<div class="section-header">📊 Module Status</div>',
                unsafe_allow_html=True)

    module_status = {
        "▦ Risk Map": not areas.empty,
        "➝ Optimized Routes": not routes.empty,
        "📅 Event Intelligence": not events.empty,
        "🏗️ Land Use Profile": not land_use_profile.empty,
        "🔬 Model Comparison": not percapita_predictions.empty or not poi_regression_predictions.empty,
        "⚠️ Early Warning": not trend_early_warning.empty,
        "📱 Citizen Reporting": True,  # Backend implemented
    }

    for module, status in module_status.items():
        status_icon = "✅" if status else "⚠️"
        st.markdown(f"{status_icon} {module}: {'Active' if status else 'Needs data'}")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

elif page == "Risk Map":

    tab_map, tab_compare, tab_landuse = st.tabs(["Map", "Model Comparison", "Land Use Profile"])
    with tab_map:

        st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Enhanced Risk Map — Click for Details</h2>',
                    unsafe_allow_html=True)
        st.markdown("Click any ward marker to see satellite imagery, NDVI/NDBI/NDWI indices, and multi-sensor data.")

        # Risk-level filter + clustering toggle — useful once you're plotting all 369 wards
        filter_col, cluster_col = st.columns([3,1])
        with filter_col:
            selected_risks = st.multiselect(
                "Show risk levels",
                ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                default=["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            )
        with cluster_col:
            cluster_markers = st.checkbox("Cluster markers", value=True)

        # Search bar
        all_area_names = sorted(areas["area_name"].dropna().unique().tolist())
        search_area = st.selectbox(
            "🔍 Search any ward",
            ["-- Select ward --"] + all_area_names,
            key="risk_search"
        )

        # Area selection state
        if 'selected_area' not in st.session_state:
            st.session_state.selected_area = None

        # Build map with click handling
        m = folium.Map(
            location=[12.9716,77.5946],
            zoom_start=11,
            tiles="OpenStreetMap"
        )

        # Draw route lines
        for i,(tid,tdata) in enumerate(routes.groupby("truck_id")):
            color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            td    = tdata.sort_values("route_sequence")
            coords= list(zip(td["Latitude"],td["Longitude"]))
            if len(coords)>1:
                folium.PolyLine(
                    coords, color=color, weight=2.5,
                    opacity=0.5, tooltip=labels.get(tid,tid)
                ).add_to(m)

        marker_target = plugins.MarkerCluster(name="Wards").add_to(m) if cluster_markers else m
        plotted_count = 0

        # Plot areas with click handlers
        for _,row in centroids.iterrows():
            risk = row.get("Area_Overflow_Risk","LOW")
            if risk not in selected_risks:
                continue
            lat_r = row["Latitude"]
            lon_r = row["Longitude"]
            name  = row.get("area_name","Unknown")
            rc    = RISK_COLORS.get(risk,"#888")

            in_priority = name in routes["area_name"].values
            diameter    = 18 if in_priority else 12
            opacity     = 0.95 if in_priority else 0.65
            plotted_count += 1

            popup_html = f"""
            <div style='font-family:sans-serif;min-width:220px;'>
              <b style='color:#1b4332;font-size:14px;'>{name}</b><br>
              <span style="background:{rc};color:white;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600;">
                {risk}
              </span><br>
              <br>
              <button onclick="selectArea('{name}')" style='background:#1b4332;color:white;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;margin-top:8px;'>
                📸 View Satellite Details
              </button>
            </div>
            """

            # A true Marker (not a vector CircleMarker) so it clusters correctly
            folium.Marker(
                location=[lat_r, lon_r],
                icon=folium.DivIcon(html=f"""
                    <div style="width:{diameter}px;height:{diameter}px;border-radius:50%;
                         background:{rc};opacity:{opacity};border:2px solid white;
                         box-shadow:0 1px 4px rgba(0,0,0,0.35);"></div>
                """, icon_size=(diameter, diameter), icon_anchor=(diameter//2, diameter//2)),
                popup=folium.Popup(popup_html, max_width=260)
            ).add_to(marker_target)

        st.markdown(
            f"<div style='font-size:0.78rem;color:#888;margin:-6px 0 10px;'>"
            f"Showing {plotted_count} of {len(centroids)} wards</div>",
            unsafe_allow_html=True)

        # Add click listener via JavaScript
        click_script = """
        <script>
        function selectArea(areaName) {
            // Send area name to Streamlit
            parent.postMessage({type: 'select_area', area: areaName}, '*');
        }
        </script>
        """
        m.get_root().html.add_child(folium.Element(click_script))


        st_folium(m, width=None, height=500)

        # Display detailed area information when selected
        if search_area != "-- Select ward --":
            st.session_state.selected_area = search_area

        if st.session_state.selected_area:
            display_area_details(st.session_state.selected_area)

    with tab_compare:

        st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Model Comparison</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            "Three independently-built predictions for the same wards, compared side by side: "
            "the satellite-based model (NDVI/NDBI/NDWI), a per-capita generation model "
            "(population × published waste rates), and a POI-density regression (OSM building/shop "
            "density). Agreement between independent approaches is a form of cross-validation; "
            "disagreement highlights wards worth a closer look."
        )

        have_satellite = not areas.empty and "Total_Predicted_Waste_kg" in areas.columns
        have_percapita = not percapita_predictions.empty
        have_poi = not poi_regression_predictions.empty

        if not (have_percapita or have_poi):
            st.warning(
                "Neither alternative model's output was found yet. Run fetch_osm_ward_features.py, "
                "then percapita_waste_model.py and/or poi_regression_model.py, to populate this page."
            )
        else:
            # Build a combined per-ward comparison table
            combined = None
            if have_satellite:
                combined = areas[["area_name", "Total_Predicted_Waste_kg", "Area_Overflow_Risk"]].rename(
                    columns={"Total_Predicted_Waste_kg": "Satellite (kg/day)", "Area_Overflow_Risk": "Satellite Risk"})
            if have_percapita:
                pc = percapita_predictions[["area_name", "total_predicted_waste_kg", "Overflow_Risk"]].rename(
                    columns={"total_predicted_waste_kg": "Per-Capita (kg/day)", "Overflow_Risk": "Per-Capita Risk"})
                combined = pc if combined is None else combined.merge(pc, on="area_name", how="outer")
            if have_poi:
                poi = poi_regression_predictions[["area_name", "poi_regression_predicted_waste_kg"]].rename(
                    columns={"poi_regression_predicted_waste_kg": "POI-Regression (kg/day)"})
                combined = poi if combined is None else combined.merge(poi, on="area_name", how="outer")

            # Summary stats
            cols = st.columns(3)
            cols[0].metric("Satellite model", "Active" if have_satellite else "Not loaded")
            cols[1].metric("Per-capita model", "Active" if have_percapita else "Not run yet")
            cols[2].metric("POI-regression model", "Active" if have_poi else "Not run yet")

            st.markdown("---")

            # Agreement between satellite and per-capita risk classifications, if both exist
            if have_satellite and have_percapita and "Satellite Risk" in combined.columns and "Per-Capita Risk" in combined.columns:
                st.markdown("### 🔍 Risk Classification Agreement")
                valid = combined.dropna(subset=["Satellite Risk", "Per-Capita Risk"])
                if not valid.empty:
                    agree = (valid["Satellite Risk"] == valid["Per-Capita Risk"]).sum()
                    st.metric("Wards where Satellite and Per-Capita models agree on risk level",
                              f"{agree} of {len(valid)} ({agree/len(valid)*100:.0f}%)")

                    if PLOTLY_AVAILABLE:
                        cross = valid.groupby(["Satellite Risk", "Per-Capita Risk"]).size().reset_index(name="count")
                        fig = px.density_heatmap(
                            cross, x="Satellite Risk", y="Per-Capita Risk", z="count",
                            category_orders={"Satellite Risk": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                                              "Per-Capita Risk": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                            color_continuous_scale="Greens",
                            title="Satellite Risk vs. Per-Capita Risk (diagonal = agreement)"
                        )
                        fig.update_layout(height=420, font_family="Inter")
                        st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # POI regression scatter, if the chart exists
            if have_poi and os.path.exists(POI_REGRESSION_CHART_FILE):
                st.markdown("### 📈 POI-Regression vs. Satellite Model")
                st.image(POI_REGRESSION_CHART_FILE, use_container_width=True)
                st.caption(
                    "Each point is one ward. Points near the dashed line mean the two independent "
                    "models agree closely; points far from it are wards where OSM-derived land-use "
                    "density and satellite land-cover signals disagree."
                )

            st.markdown("---")

            # Full comparison table
            st.markdown("### 📋 Full Ward Comparison")
            if combined is not None:
                st.dataframe(combined.sort_values("area_name"), use_container_width=True, hide_index=True)

            # Search a specific ward
            if combined is not None:
                st.markdown("### 🔍 Search a Ward")
                search_ward = st.selectbox(
                    "Select a ward", ["-- Select --"] + sorted(combined["area_name"].dropna().unique().tolist()),
                    key="model_comparison_search"
                )
                if search_ward != "-- Select --":
                    row = combined[combined["area_name"] == search_ward].iloc[0]
                    metric_cols = st.columns(3)
                    if "Satellite (kg/day)" in combined.columns:
                        metric_cols[0].metric("Satellite", f"{row.get('Satellite (kg/day)', float('nan')):.1f} kg/day"
                                               if pd.notna(row.get("Satellite (kg/day)")) else "—")
                    if "Per-Capita (kg/day)" in combined.columns:
                        metric_cols[1].metric("Per-Capita", f"{row.get('Per-Capita (kg/day)', float('nan')):.1f} kg/day"
                                               if pd.notna(row.get("Per-Capita (kg/day)")) else "—")
                    if "POI-Regression (kg/day)" in combined.columns:
                        metric_cols[2].metric("POI-Regression", f"{row.get('POI-Regression (kg/day)', float('nan')):.1f} kg/day"
                                               if pd.notna(row.get("POI-Regression (kg/day)")) else "—")

    with tab_landuse:

        st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Land Use Profile</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            "Current land cover per ward, classified from satellite NDVI/NDBI/NDWI signals. "
            "**This is a snapshot, not change-over-time detection** — only one satellite pass "
            "is available, so there's nothing to compare it against yet."
        )

        if land_use_profile.empty:
            st.warning(
                "Land use profile isn't available — this needs both "
                "bengaluru_satellite_features.csv and bengaluru_grid_area_mapping.csv "
                "to exist with matching Grid_ID columns."
            )
        else:
            category_colors = {
                "Vegetated / Green": "#52b788",
                "Dense Built-up": "#e63946",
                "Mixed Urban": "#f4a261",
                "Water / Moisture-rich": "#457b9d",
                "Sparse / Transitional": "#e9c46a",
                "Unknown": "#ccc",
            }

            c1, c2, c3 = st.columns(3)
            c1.metric("Areas classified", f"{land_use_profile['area_name'].nunique():,}")
            top_category = land_use_profile["Land_Use_Category"].mode()
            c2.metric("Most common land cover", top_category.iloc[0] if not top_category.empty else "—")
            built_up_pct = (
                (land_use_profile["Land_Use_Category"].isin(["Dense Built-up", "Mixed Urban"]).sum()
                 / len(land_use_profile) * 100) if len(land_use_profile) else 0
            )
            c3.metric("Wards with urban/built-up cover", f"{built_up_pct:.0f}%")

            st.markdown("---")

            # Category breakdown, visually — matches the "show it visually" standard set elsewhere
            st.markdown("### 🗺️ Land Cover Distribution")
            cat_counts = land_use_profile["Land_Use_Category"].value_counts().reset_index()
            cat_counts.columns = ["Land_Use_Category", "Wards"]
            if PLOTLY_AVAILABLE:
                fig = px.bar(
                    cat_counts, x="Land_Use_Category", y="Wards", color="Land_Use_Category",
                    color_discrete_map=category_colors,
                    title="Wards by Land Cover Category"
                )
                fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   height=380, font_family="Inter", showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # Map, colored by category, using the same centroids already used elsewhere
            if not centroids.empty:
                st.markdown("### 📍 Land Cover Map")
                merged_map = centroids.merge(land_use_profile, on="area_name", how="inner")
                if not merged_map.empty:
                    lu_map = folium.Map(location=[12.9716, 77.5946], zoom_start=11, tiles="OpenStreetMap")
                    cluster = plugins.MarkerCluster(name="Wards").add_to(lu_map)
                    for _, row in merged_map.iterrows():
                        color = category_colors.get(row["Land_Use_Category"], "#888")
                        folium.CircleMarker(
                            location=[row["Latitude"], row["Longitude"]],
                            radius=6, color=color, fill=True, fill_color=color, fill_opacity=0.75,
                            tooltip=f"{row['area_name']}: {row['Land_Use_Category']}"
                        ).add_to(cluster)
                    st_folium(lu_map, width=None, height=460)

                    legend_html = "".join(
                        f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:18px;'>"
                        f"<span style='width:11px;height:11px;border-radius:50%;background:{c};display:inline-block;'></span>"
                        f"<span style='font-size:0.82rem;color:#555;'>{cat}</span></span>"
                        for cat, c in category_colors.items() if cat in cat_counts["Land_Use_Category"].values
                    )
                    st.markdown(legend_html, unsafe_allow_html=True)

            st.markdown("---")

            # Cross-reference with overflow risk, if available — this is the actual payoff:
            # does built-up land cover correlate with higher waste risk?
            if not areas.empty and "Area_Overflow_Risk" in areas.columns:
                st.markdown("### ♻️ Land Cover vs. Overflow Risk")
                risk_join = areas[["area_name", "Area_Overflow_Risk"]].merge(
                    land_use_profile[["area_name", "Land_Use_Category"]], on="area_name", how="inner"
                )
                if not risk_join.empty and PLOTLY_AVAILABLE:
                    cross = risk_join.groupby(["Land_Use_Category", "Area_Overflow_Risk"]).size().reset_index(name="count")
                    fig2 = px.bar(
                        cross, x="Land_Use_Category", y="count", color="Area_Overflow_Risk",
                        color_discrete_map=RISK_COLORS,
                        title="Overflow Risk Level by Land Cover Category", barmode="stack"
                    )
                    fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                        height=400, font_family="Inter")
                    st.plotly_chart(fig2, use_container_width=True)
                    st.caption(
                        "If built-up categories skew toward CRITICAL/HIGH more than vegetated ones, "
                        "that's a real signal worth naming in your report — not just a chart for its own sake."
                    )

            st.markdown("---")
            st.markdown("### 🔍 Search a Ward")
            search_area_lu = st.selectbox(
                "Select a ward", ["-- Select --"] + sorted(land_use_profile["area_name"].unique().tolist()),
                key="landuse_search"
            )
            if search_area_lu != "-- Select --":
                row = land_use_profile[land_use_profile["area_name"] == search_area_lu].iloc[0]
                st.markdown(f"""
                <div class="info-panel">
                  <h3>{search_area_lu}</h3>
                  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">
                    <div><div style="font-size:0.72rem;color:#888;text-transform:uppercase;">Category</div>
                      <div style="font-weight:700;color:#1b4332;">{row['Land_Use_Category']}</div></div>
                    <div><div style="font-size:0.72rem;color:#888;text-transform:uppercase;">NDVI</div>
                      <div style="font-weight:700;">{row.get('NDVI', float('nan')):.3f}</div></div>
                    <div><div style="font-size:0.72rem;color:#888;text-transform:uppercase;">NDBI</div>
                      <div style="font-weight:700;">{row.get('NDBI', float('nan')):.3f}</div></div>
                    <div><div style="font-size:0.72rem;color:#888;text-transform:uppercase;">Grid Cells</div>
                      <div style="font-weight:700;">{int(row['Grid_Cells'])}</div></div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

    # ============================================================
    # PAGE — EARLY WARNING (+ CITIZEN REPORTS)
    # ============================================================


elif page == "Optimized Routes":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Enhanced Route Optimization</h2>',
                unsafe_allow_html=True)
    st.markdown("Click on any ward to see optimized routes from that location to nearest high-priority wards.")

    # Routing engine selector — OR-Tools is a real capacitated VRP solve; the
    # nearest-neighbor engine is a fast greedy fallback for when OR-Tools hasn't
    # been run or its input file doesn't exist yet.
    engine_options = ["OR-Tools (capacity-constrained optimizer)"]
    engine_choice = st.radio("Routing engine", engine_options, horizontal=True, key="routing_engine_choice")

    active_routes = routes

    active_route_ids = sorted(active_routes["truck_id"].unique()) if not active_routes.empty else []
    active_labels = {tid: f"Route {i+1}" for i, tid in enumerate(active_route_ids)}

    # Search bar — every area in the dataset, not just ones already in today's routes
    route_area_names = sorted(areas["area_name"].dropna().unique().tolist())
    selected_start_area = st.selectbox(
        "🎯 Select starting ward for route calculation",
        ["-- Select starting ward --"] + route_area_names,
        key="route_start_area"
    )

    if selected_start_area != "-- Select starting ward --":
        st.session_state.start_area = selected_start_area
        display_enhanced_routes(selected_start_area, active_routes, areas, centroids, active_route_ids, active_labels)
    else:
        # Show all routes overview
        display_all_routes(active_routes, areas, centroids, active_route_ids, active_labels)

# ============================================================
# PAGE — EVENT INTELLIGENCE
# ============================================================

elif page == "Event Intelligence":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Event Intelligence</h2>',
                unsafe_allow_html=True)
    st.markdown("Festivals, markets, and public events shift where waste piles up — before it happens.")

    # "Wards affected" needs to reflect actual grid-level impact, not a coarse
    # free-text location field in the events table (which for a citywide event
    # like "Bengaluru" with no venue would always read as just 1, regardless of
    # how many wards are genuinely touched). Join the real affected grid cells
    # through the grid-to-ward mapping instead.
    wards_with_events = 0
    if not event_waste.empty and "event_affected" in event_waste.columns and not grid_area_mapping.empty:
        ew_id_col = find_col(event_waste, GRID_ID_CANDIDATES)
        gm_id_col = find_col(grid_area_mapping, GRID_ID_CANDIDATES)
        gm_area_col = find_col(grid_area_mapping, ["area_name"])
        if ew_id_col and gm_id_col and gm_area_col:
            affected_mask = event_waste["event_affected"].astype(bool)
            affected_grid_ids = event_waste.loc[affected_mask, ew_id_col]
            matched_wards = grid_area_mapping[grid_area_mapping[gm_id_col].isin(affected_grid_ids)]
            wards_with_events = matched_wards[gm_area_col].nunique()

    c1, c2, c3 = st.columns(3)
    c1.metric("Tracked events", f"{len(events):,}" if not events.empty else "0")
    c2.metric("Wards affected", f"{wards_with_events:,}")
    c3.metric("Grid cells affected", f"{affected_grids:,}")

    with st.expander("Data column reference (for debugging)"):
        st.write("**events columns:**", list(events.columns) if not events.empty else "— empty —")
        st.write("**event_impact columns:**", list(event_impact.columns) if not event_impact.empty else "— empty —")

    st.markdown("---")

    # ---------------- Event timeline ----------------
    st.markdown("### 📅 Event Timeline")
    if not events.empty:
        date_col = find_col(events, ["event_date", "date", "start_date", "start_datetime", "end_datetime"])
        name_col = find_col(events, ["event_name", "name", "title"])
        type_col = find_col(events, ["event_type", "type", "category"])
        area_col = find_col(events, ["area_name", "area", "location", "venue", "ward", "ward_name"])

        filtered_events = events.copy()
        parsed_dates = None
        if date_col:
            parsed_dates = pd.to_datetime(filtered_events[date_col], errors="coerce")

        # Filters: upcoming/past (only meaningful if we found a date column) + event type
        filt_col1, filt_col2 = st.columns([1, 1.4])
        with filt_col1:
            if date_col:
                time_filter = st.radio("Show", ["Upcoming", "Past", "All"], horizontal=True, key="event_time_filter")
            else:
                time_filter = "All"
                st.caption("No date column found — can't filter by upcoming/past.")
        with filt_col2:
            if type_col:
                type_options = sorted(filtered_events[type_col].dropna().unique().tolist())
                selected_types = st.multiselect("Event type", type_options, default=type_options, key="event_type_filter")
            else:
                selected_types = None

        if date_col and parsed_dates is not None:
            filtered_events = filtered_events.assign(_parsed_date=parsed_dates)
            today = pd.Timestamp(datetime.now().date())
            if time_filter == "Upcoming":
                filtered_events = filtered_events[filtered_events["_parsed_date"] >= today]
            elif time_filter == "Past":
                filtered_events = filtered_events[filtered_events["_parsed_date"] < today]
        if selected_types is not None:
            filtered_events = filtered_events[filtered_events[type_col].isin(selected_types)]

        if filtered_events.empty:
            st.info("No events match the current filters.")
        else:
            plotted = False
            if date_col and PLOTLY_AVAILABLE:
                plot_df = filtered_events.dropna(subset=["_parsed_date"]) if "_parsed_date" in filtered_events.columns else pd.DataFrame()
                if not plot_df.empty:
                    y_field = area_col or name_col
                    if y_field:
                        fig = px.scatter(
                            plot_df, x="_parsed_date", y=y_field,
                            color=type_col if type_col else None,
                            hover_data=[c for c in [name_col, area_col, type_col] if c],
                            title="When and where events are happening"
                        )
                        fig.update_traces(marker=dict(size=13, line=dict(width=1, color="white")))
                        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                           height=380, font_family="Inter",
                                           xaxis_title="Date", yaxis_title="")

                        # With very few distinct dates (as few as 1), Plotly's
                        # auto-range can degenerate to a sub-millisecond-wide
                        # window and label ticks in fractions of a millisecond
                        # — meaningless for calendar dates. Force a sensible
                        # fixed window instead of trusting auto-range here.
                        date_span = plot_df["_parsed_date"].max() - plot_df["_parsed_date"].min()
                        if date_span < pd.Timedelta(days=14):
                            center = plot_df["_parsed_date"].min() + date_span / 2
                            fig.update_xaxes(
                                range=[center - pd.Timedelta(days=15), center + pd.Timedelta(days=15)],
                                tickformat="%d %b %Y"
                            )
                        else:
                            fig.update_xaxes(tickformat="%d %b %Y")

                        st.plotly_chart(fig, use_container_width=True)
                        plotted = True

            # Card list — always shown, includes lead-time countdown and a jump to Risk Map
            cols = st.columns(3)
            for i, (_, ev) in enumerate(filtered_events.head(12).iterrows()):
                with cols[i % 3]:
                    name = ev.get(name_col, "Event") if name_col else "Event"
                    area_txt = ev.get(area_col, None) if area_col else None
                    type_txt = ev.get(type_col, None) if type_col else None

                    lead_txt = ""
                    if date_col and pd.notna(ev.get("_parsed_date")):
                        delta_days = (ev["_parsed_date"].normalize() - pd.Timestamp(datetime.now().date())).days
                        if delta_days > 1:
                            lead_txt = f"in {delta_days} days"
                        elif delta_days == 1:
                            lead_txt = "tomorrow"
                        elif delta_days == 0:
                            lead_txt = "today"
                        elif delta_days == -1:
                            lead_txt = "yesterday"
                        else:
                            lead_txt = f"{abs(delta_days)} days ago"
                        date_display = ev["_parsed_date"].strftime("%d %b %Y")
                    else:
                        date_display = ev.get(date_col, "") if date_col else ""

                    st.markdown(f"""
                    <div style="background:white;border-radius:10px;padding:12px 14px;margin-bottom:6px;
                         border:1px solid #e8f5e9;">
                      <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:0.72rem;color:#888;">{date_display}</span>
                        {f'<span style="font-size:0.7rem;color:#40916c;font-weight:600;">{lead_txt}</span>' if lead_txt else ''}
                      </div>
                      <div style="font-weight:600;color:#1b4332;margin-top:2px;">{name}</div>
                      <div style="font-size:0.8rem;color:#555;">{area_txt or ''}</div>
                      {f'<span class="badge badge-medium" style="margin-top:4px;display:inline-block;">{type_txt}</span>' if type_txt else ''}
                    </div>
                    """, unsafe_allow_html=True)

                    if area_txt and not areas.empty and area_txt in areas["area_name"].values:
                        if st.button(f"View {area_txt} on Risk Map", key=f"jump_risk_{i}", use_container_width=True):
                            st.session_state.active_page = "Risk Map"
                            st.session_state.selected_area = area_txt
                            st.rerun()
    else:
        st.warning("No tracked events found. Run the event scraper to populate bengaluru_events.csv.")

    st.markdown("---")

    # ---------------- Impact visualization — relative severity, no kg figures ----------------
    st.markdown("### 🌍 Where Events Are Pushing Up Waste Risk")
    if not event_impact.empty:
        lat_col = find_col(event_impact, ["Latitude", "latitude", "lat"])
        lon_col = find_col(event_impact, ["Longitude", "longitude", "lon", "lng"])
        impact_col = next((c for c in event_impact.columns
                            if "impact" in c.lower() or "waste" in c.lower() or "risk" in c.lower()), None)
        area_col = find_col(event_impact, ["area_name", "area", "location", "venue", "ward", "ward_name"])

        working_impact = event_impact
        # No coordinates and no ward-name column of its own — try joining through
        # Grid_ID to grid_area_mapping, same approach used for the satellite features
        # and Land Use Profile, instead of only working when the file already has them.
        if not (lat_col and lon_col) and not area_col:
            ei_id_col = find_col(event_impact, GRID_ID_CANDIDATES)
            gm_id_col = find_col(grid_area_mapping, GRID_ID_CANDIDATES) if not grid_area_mapping.empty else None
            gm_area_col = find_col(grid_area_mapping, ["area_name"]) if not grid_area_mapping.empty else None
            if ei_id_col and gm_id_col and gm_area_col:
                joined = event_impact.merge(
                    grid_area_mapping[[gm_id_col, gm_area_col]].rename(
                        columns={gm_id_col: ei_id_col, gm_area_col: "_matched_ward"}),
                    on=ei_id_col, how="left"
                )
                if joined["_matched_ward"].notna().any():
                    working_impact = joined
                    area_col = "_matched_ward"

        work = pd.DataFrame()
        if impact_col:
            work = working_impact.copy()
            work[impact_col] = pd.to_numeric(work[impact_col], errors="coerce")
            work = work.dropna(subset=[impact_col])

        if not work.empty:
            # Bucket into relative Low/Medium/High bands — never show the raw underlying number.
            # Equal-WIDTH bins on the actual value (not equal-frequency/rank-based), so if most
            # cells genuinely have low impact, the chart shows that instead of forcing ~33/33/33.
            try:
                work["severity"] = pd.cut(work[impact_col], bins=3, labels=["Low", "Medium", "High"])
                if work["severity"].isna().any():
                    work["severity"] = work["severity"].fillna("Low")
            except ValueError:
                work["severity"] = "Medium"  # all values identical — can't split into bands
            severity_color = {"Low": "#52b788", "Medium": "#f4a261", "High": "#e63946"}

            if lat_col and lon_col:
                impact_map = folium.Map(location=[12.9716,77.5946], zoom_start=11, tiles="OpenStreetMap")
                radius_map = {"Low": 4, "Medium": 7, "High": 11}
                for _, row in work.iterrows():
                    if pd.isna(row[lat_col]) or pd.isna(row[lon_col]):
                        continue
                    sev = row["severity"]
                    color = severity_color.get(sev, "#888")
                    folium.CircleMarker(
                        location=[row[lat_col], row[lon_col]],
                        radius=radius_map.get(sev, 5),
                        color=color, fill=True, fill_color=color, fill_opacity=0.65,
                        tooltip=f"{row.get(area_col, 'Grid cell') if area_col else 'Grid cell'}: {sev} impact"
                    ).add_to(impact_map)
                st_folium(impact_map, width=None, height=440)
                legend_html = "".join(
                    f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:20px;'>"
                    f"<span style='width:11px;height:11px;border-radius:50%;background:{c};display:inline-block;'></span>"
                    f"<span style='font-size:0.82rem;color:#555;'>{lvl} impact</span></span>"
                    for lvl, c in severity_color.items()
                )
                st.markdown(legend_html, unsafe_allow_html=True)
            elif area_col and PLOTLY_AVAILABLE:
                counts = work.groupby([area_col, "severity"], observed=True).size().reset_index(name="grid_cells")
                fig = px.bar(counts, x=area_col, y="grid_cells", color="severity",
                             color_discrete_map=severity_color,
                             title="Wards by event impact severity (grid cells affected)")
                fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   height=400, font_family="Inter")
                st.plotly_chart(fig, use_container_width=True)
            elif PLOTLY_AVAILABLE:
                # No coordinates AND no area name — still show *something* visual:
                # just the overall severity distribution, no location breakdown
                sev_counts = work["severity"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0).reset_index()
                sev_counts.columns = ["severity", "grid_cells"]
                fig = px.bar(sev_counts, x="severity", y="grid_cells", color="severity",
                             color_discrete_map=severity_color,
                             title="Event impact severity across all monitored grid cells")
                fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   height=340, font_family="Inter", showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                st.caption("No coordinates or ward names in this file, so this can't be broken down by location yet.")
            else:
                st.info("Impact data doesn't have coordinates or a ward name to visualize.")
        else:
            st.info("No usable impact values found in the event-grid-impact file.")
    else:
        st.info("No event impact data available yet.")

elif page == "Weather Integration":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Weather Integration Module</h2>',
                unsafe_allow_html=True)
    
    if weather_data:
        st.markdown("### 🌤 Current Weather Conditions")
        
        if 'current_weather' in weather_data:
            current = weather_data['current_weather']
            c1,c2,c3,c4 = st.columns(4)
            
            c1.metric("Temperature", f"{current.get('temperature_c', 'N/A')}°C")
            c2.metric("Humidity", f"{current.get('humidity_percent', 'N/A')}%")
            c3.metric("Precipitation", f"{current.get('precipitation_mm', 'N/A')} mm")
            c4.metric("Wind Speed", f"{current.get('wind_speed_kmh', 'N/A')} km/h")
        
        st.markdown("---")
        
        # Weather forecast
        if 'forecast' in weather_data and weather_data['forecast']:
            st.markdown("### 📅 7-Day Weather Forecast")
            
            forecast_df = pd.DataFrame(weather_data['forecast'])
            
            st.dataframe(
                forecast_df[['date', 'temperature_max_c', 'temperature_min_c', 'precipitation_mm']],
                column_config={
                    'date': st.column_config.TextColumn('Date'),
                    'temperature_max_c': st.column_config.NumberColumn('Max Temp (°C)'),
                    'temperature_min_c': st.column_config.NumberColumn('Min Temp (°C)'),
                    'precipitation_mm': st.column_config.NumberColumn('Precipitation (mm)')
                },
                hide_index=True
            )
            
            # Visualize temperature trend
            if PLOTLY_AVAILABLE:
                fig = px.line(forecast_df, x='date', y=['temperature_max_c', 'temperature_min_c'],
                            title="Temperature Forecast", labels={'value': 'Temperature (°C)'})
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Weather data not available. Run weather_integration.py to generate data.")

# ============================================================
# PAGE — CITIZEN REPORTING
# ============================================================

elif page == "Social Media Events":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Social Media Event Detection</h2>',
                unsafe_allow_html=True)
    
    if not social_events.empty:
        st.markdown(f"### 📱 Detected Events: {len(social_events)}")
        
        st.dataframe(
            social_events[['event_type', 'predicted_waste_impact', 'confidence_score']],
            column_config={
                'event_type': st.column_config.TextColumn('Event Type'),
                'predicted_waste_impact': st.column_config.TextColumn('Waste Impact'),
                'confidence_score': st.column_config.NumberColumn('Confidence')
            },
            hide_index=True
        )
        
        # Event impact chart
        if PLOTLY_AVAILABLE:
            event_impact = social_events.groupby('event_type')['predicted_waste_impact'].mean()
            fig = px.bar(event_impact, title="Average Waste Impact by Event Type")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No social media events detected. Run social_event_detector.py to collect event data.")

# ============================================================
# PAGE — FLEET MAINTENANCE
# ============================================================

elif page == "Fleet Maintenance":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Predictive Fleet Maintenance</h2>',
                unsafe_allow_html=True)
    
    if not fleet_data.empty:
        st.markdown(f"### 🚛 Fleet Overview: {fleet_data['vehicle_id'].nunique()} vehicles")
        
        # Vehicle health summary
        avg_engine_health = fleet_data['engine_health_percent'].mean()
        avg_transmission_health = fleet_data['transmission_health_percent'].mean()
        avg_brake_health = fleet_data['brake_health_percent'].mean()
        
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Avg Engine Health", f"{avg_engine_health:.1f}%")
        c2.metric("Avg Transmission Health", f"{avg_transmission_health:.1f}%")
        c3.metric("Avg Brake Health", f"{avg_brake_health:.1f}%")
        c4.metric("Vehicles Needing Maintenance", 
                 f"{fleet_data[fleet_data['needs_routine_maintenance']==1]['vehicle_id'].nunique()}")
        
        st.markdown("---")
        
        # Maintenance schedule
        if not maintenance_schedule.empty:
            st.markdown("### 📅 Maintenance Schedule")
            
            priority_maintenance = maintenance_schedule[maintenance_schedule['urgency'] >= 0.7]
            
            st.dataframe(
                priority_maintenance[['vehicle_id', 'maintenance_type', 'urgency', 'estimated_cost']],
                column_config={
                    'vehicle_id': st.column_config.TextColumn('Vehicle'),
                    'maintenance_type': st.column_config.TextColumn('Type'),
                    'urgency': st.column_config.NumberColumn('Urgency'),
                    'estimated_cost': st.column_config.NumberColumn('Estimated Cost')
                },
                hide_index=True
            )
        else:
            st.warning("No maintenance schedule available. Run predictive_maintenance.py to generate schedule.")
    else:
        st.warning("Fleet data not available. Run predictive_maintenance.py to generate synthetic fleet data.")

# ============================================================
# PAGE — LAND USE CHANGES
# ============================================================

elif page == "Early Warning & Citizen Reports":

    tab_warn, tab_citizen = st.tabs(["Early Warning", "Citizen Reports"])
    with tab_warn:

        st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Early Warning</h2>',
                    unsafe_allow_html=True)
        st.markdown(
            "Every other model in this dashboard classifies a ward's risk as of right now. "
            "This one is different: it looks at 7 days of real prediction history, learns each "
            "ward's trend, and flags wards heading toward CRITICAL before they arrive — validated "
            "by backtesting against real held-out data, not just asserted."
        )

        if trend_early_warning.empty:
            st.warning(
                "Trend early warning output not found yet. Run fetch_osm_ward_features.py's sibling "
                "script, trend_early_warning_model.py (or trend_early_warning.py), to populate this page."
            )
        else:
            already_critical_count = int((trend_early_warning["days_to_critical"] == 0).sum())
            approaching = trend_early_warning[
                (trend_early_warning["days_to_critical"].notna()) & (trend_early_warning["days_to_critical"] > 0)
            ].sort_values("days_to_critical")

            cols = st.columns(4)
            cols[0].metric("Wards tracked", f"{len(trend_early_warning):,}")
            cols[1].metric("Already critical today", f"{already_critical_count:,}")
            cols[2].metric("Approaching within 5 days", f"{(approaching['days_to_critical'] <= 5).sum():,}")
            rising_fast = int((trend_early_warning["trend_status"] == "Rising Fast").sum())
            cols[3].metric("Rising Fast", f"{rising_fast:,}")

            st.markdown("---")

            # Backtest validation — shown prominently since this is what makes
            # this model different from every other prediction in the project
            st.markdown("### ✅ Backtest Validation")
            st.markdown(
                "Trained on the first 5 days, tested against a real day it never saw during training. "
                "This is genuine out-of-sample validation — something none of the other models in this "
                "project can claim, since there's no ground truth to check them against."
            )
            if os.path.exists(TREND_BACKTEST_CHART_FILE):
                bt_col1, bt_col2 = st.columns([1, 1.3])
                with bt_col1:
                    st.image(TREND_BACKTEST_CHART_FILE, use_container_width=True)
                with bt_col2:
                    st.markdown(
                        """
                        <div style="background:#f0f7f2;border-radius:12px;padding:20px;margin-top:20px;">
                        <b>How to read this:</b><br><br>
                        The model was trained on days 1–5 only, then asked to predict which wards would
                        <b>newly</b> cross into CRITICAL by day 7 — a day it never saw during training.<br><br>
                        <b>Correctly early-warned</b> — wards the model flagged in advance that genuinely
                        crossed.<br>
                        <b>False alarms</b> — flagged, but didn't actually cross.<br>
                        <b>Missed</b> — crossed, but weren't flagged.<br><br>
                        A high bar on the left with nothing elsewhere means the model's day-of-week-aware
                        trend detection is working, not just getting lucky.
                        </div>
                        """, unsafe_allow_html=True
                    )
            else:
                st.info("Backtest chart not found — run the trend model script to generate it.")

            st.markdown("---")

            # Trend status breakdown
            st.markdown("### 📊 Trend Status Across All Wards")
            status_counts = trend_early_warning["trend_status"].value_counts()
            if PLOTLY_AVAILABLE:
                status_colors = {"Rising Fast": "#c0392b", "Rising": "#e67e22", "Stable": "#7f8c8d", "Declining": "#27ae60"}
                fig = px.bar(
                    x=status_counts.index, y=status_counts.values,
                    labels={"x": "Trend Status", "y": "Number of Wards"},
                    color=status_counts.index,
                    color_discrete_map=status_colors,
                    title="How many wards are trending which way"
                )
                fig.update_layout(showlegend=False, height=380, font_family="Inter")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(status_counts)

            st.markdown("---")

            # Wards approaching critical soon (the actual early-warning list)
            st.markdown("### ⚠️ Wards Approaching CRITICAL (not yet there)")
            if approaching.empty:
                st.success(
                    "No wards are currently projected to newly cross into CRITICAL within the near "
                    "term. Growth rates across the city are essentially flat right now."
                )
            else:
                display_cols = ["area_name", "latest_waste_kg", "pct_growth_per_day", "trend_status", "days_to_critical"]
                display_cols = [c for c in display_cols if c in approaching.columns]
                st.dataframe(
                    approaching[display_cols].head(20).rename(columns={
                        "area_name": "Ward", "latest_waste_kg": "Latest (kg/day)",
                        "pct_growth_per_day": "Growth %/day", "trend_status": "Trend",
                        "days_to_critical": "Days to Critical"
                    }),
                    use_container_width=True, hide_index=True
                )

            st.markdown("---")

            # Already-critical wards, shown separately with clear labeling
            st.markdown("### 🔴 Already Critical Today")
            already = trend_early_warning[trend_early_warning["days_to_critical"] == 0].sort_values(
                "latest_waste_kg", ascending=False)
            if already.empty:
                st.info("No wards are currently critical.")
            else:
                st.dataframe(
                    already[["area_name", "latest_waste_kg", "trend_status"]].head(20).rename(columns={
                        "area_name": "Ward", "latest_waste_kg": "Latest (kg/day)", "trend_status": "Trend"
                    }),
                    use_container_width=True, hide_index=True
                )

            st.markdown("---")

            # Search a specific ward
            st.markdown("### 🔍 Search a Ward")
            search_ward = st.selectbox(
                "Select a ward", ["-- Select --"] + sorted(trend_early_warning["area_name"].dropna().unique().tolist()),
                key="early_warning_search"
            )
            if search_ward != "-- Select --":
                row = trend_early_warning[trend_early_warning["area_name"] == search_ward].iloc[0]
                search_cols = st.columns(4)
                search_cols[0].metric("Latest (kg/day)", f"{row['latest_waste_kg']:,.0f}")
                search_cols[1].metric("Growth %/day", f"{row['pct_growth_per_day']:.3f}%")
                search_cols[2].metric("Trend", row["trend_status"])
                days_val = row["days_to_critical"]
                search_cols[3].metric(
                    "Days to Critical",
                    "Already there" if days_val == 0 else (f"{days_val:.1f}" if pd.notna(days_val) else "Not approaching")
                )

    with tab_citizen:

        st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Citizen Reporting System</h2>',
                    unsafe_allow_html=True)
    
        st.markdown("### 📝 Submit Waste Report")

        # Read any coordinates the browser already detected via the button below
        def _get_detected_coords():
            try:
                qp = st.query_params
                lat = float(qp["lat"]) if "lat" in qp else None
                lon = float(qp["lon"]) if "lon" in qp else None
                return lat, lon
            except Exception:
                try:
                    qp = st.experimental_get_query_params()
                    lat = float(qp["lat"][0]) if "lat" in qp else None
                    lon = float(qp["lon"][0]) if "lon" in qp else None
                    return lat, lon
                except Exception:
                    return None, None

        detected_lat, detected_lon = _get_detected_coords()

        components.html("""
        <div style="margin-bottom:6px;">
          <button onclick="detectLocation()" style="background:#1b4332;color:white;border:none;
            padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-family:sans-serif;">
            📍 Use my current location
          </button>
          <span id="geo-status" style="margin-left:10px;font-size:12px;color:#888;font-family:sans-serif;"></span>
        </div>
        <script>
        function detectLocation() {
          const status = document.getElementById('geo-status');
          if (!navigator.geolocation) {
            status.innerText = "Geolocation isn't supported by this browser.";
            return;
          }
          status.innerText = "Detecting your location…";
          navigator.geolocation.getCurrentPosition(function(pos) {
            const lat = pos.coords.latitude.toFixed(6);
            const lon = pos.coords.longitude.toFixed(6);
            const params = new URLSearchParams(window.parent.location.search);
            params.set('lat', lat);
            params.set('lon', lon);
            window.parent.location.search = params.toString();
          }, function(err) {
            if (err.code === 1) {
              status.innerText = "Location permission denied — enter coordinates manually.";
            } else if (err.code === 2) {
              status.innerText = "Position unavailable — check Location Services is on.";
            } else if (err.code === 3) {
              status.innerText = "Timed out waiting for a location fix — enter a landmark instead.";
            } else {
              status.innerText = "Couldn't get your location — enter coordinates manually.";
            }
          }, {
            timeout: 8000,
            maximumAge: 0
          });
        }
        </script>
        """, height=50)

        if detected_lat is not None and detected_lon is not None:
            st.success(f"📍 Your location has been detected and will be attached to this report.")
        else:
            st.caption("Tap \"Use my current location\" above so we can pinpoint your report precisely — or just describe the landmark below.")

        # Report form — no raw coordinates shown to the citizen; location comes from
        # the geolocation button above (captured silently) plus a plain-language landmark
        with st.form("waste_report_form"):
            col1, col2 = st.columns(2)
        
            with col1:
                landmark = st.text_input(
                    "Landmark or address (optional)", "",
                    placeholder="e.g. Near HSR Layout Sector 2 market")
                waste_type = st.selectbox("Waste Type", 
                                         ["garbage", "overflow", "illegal_dumping", "construction_debris", "container_damage"])
                severity = st.selectbox("Severity", ["low", "medium", "high", "critical"])
        
            with col2:
                phone_number = st.text_input(
                    "Phone number (optional)", "",
                    placeholder="For follow-up only — not required")
                description = st.text_area("Description (optional)", "")
                photo_upload = st.file_uploader("Upload Photo (optional)", type=["jpg", "png"])
        
            submitted = st.form_submit_button("Submit Report")
    
        if submitted:
            latitude, longitude = detected_lat, detected_lon
            if latitude is None or longitude is None:
                st.warning("No precise location was detected, so this report was saved with only the landmark/description you gave — "
                           "click \"Use my current location\" next time for a pinpointed report.")

            # Match to the nearest ward if we have coordinates, so Risk Map can show this
            # report when someone views that ward — same nearest-point approach used
            # throughout the routing pages.
            matched_ward = None
            if latitude is not None and longitude is not None and not centroids.empty:
                distances = centroids.apply(
                    lambda row: haversine_km(latitude, longitude, row["Latitude"], row["Longitude"]), axis=1)
                nearest_idx = distances.idxmin()
                if distances.loc[nearest_idx] < 5:  # within 5 km — otherwise don't force a match
                    matched_ward = centroids.loc[nearest_idx, "area_name"]

            # No GPS match — fall back to matching the typed landmark text against
            # real ward names (exact match first, then "landmark contains ward name")
            if matched_ward is None and landmark and not areas.empty:
                landmark_norm = landmark.strip().lower()
                ward_names = areas["area_name"].dropna().unique().tolist()
                exact = [w for w in ward_names if w.strip().lower() == landmark_norm]
                if exact:
                    matched_ward = exact[0]
                else:
                    contains = [w for w in ward_names if w.strip().lower() in landmark_norm]
                    if contains:
                        # prefer the longest match — avoids a short ward name like "Agara"
                        # accidentally matching inside an unrelated longer landmark string
                        matched_ward = max(contains, key=len)

            # Save the photo to disk, if one was uploaded
            photo_path = None
            if photo_upload is not None:
                os.makedirs(REPORTS_PHOTOS_DIR, exist_ok=True)
                ext = os.path.splitext(photo_upload.name)[1] or ".jpg"
                report_id = f"RPT_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                photo_filename = f"{report_id}{ext}"
                photo_full_path = os.path.join(REPORTS_PHOTOS_DIR, photo_filename)
                with open(photo_full_path, "wb") as f:
                    f.write(photo_upload.getbuffer())
                photo_path = photo_full_path
            else:
                report_id = f"RPT_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

            new_report = {
                "report_id": report_id,
                "submitted_at": datetime.now().isoformat(),
                "latitude": latitude,
                "longitude": longitude,
                "matched_ward": matched_ward,
                "landmark": landmark,
                "waste_type": waste_type,
                "severity": severity,
                "phone_number": phone_number,
                "description": description,
                "photo_path": photo_path,
            }

            # Append to the reports file — load what's there, add this one, save it back
            existing_reports = []
            if os.path.exists(REPORTS_FILE):
                try:
                    with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
                        existing_reports = json.load(f)
                except Exception:
                    existing_reports = []
            existing_reports.append(new_report)
            os.makedirs(os.path.dirname(REPORTS_FILE), exist_ok=True)
            with open(REPORTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_reports, f, indent=2, default=str)

            # Force a fresh reload so this report shows up immediately elsewhere in the app
            load_data.clear()

            st.success("Report submitted successfully! Thank you for helping keep Bengaluru clean.")
            if matched_ward:
                st.info(f"This report will now appear under **{matched_ward}** on the Risk Map.")
            else:
                st.info("Your report will be reviewed and appropriate action will be taken. "
                        "It couldn't be matched to a specific ward without a detected location.")

        st.markdown("---")
        st.markdown("### 📋 Recent Reports")

        if citizen_reports.empty:
            st.caption("No reports submitted yet — be the first.")
        else:
            recent = citizen_reports.sort_values("submitted_at", ascending=False).head(10)
            for _, rep in recent.iterrows():
                rep_col1, rep_col2 = st.columns([1, 3])
                with rep_col1:
                    if rep.get("photo_path") and os.path.exists(str(rep["photo_path"])):
                        st.image(rep["photo_path"], use_container_width=True)
                    else:
                        st.caption("No photo")
                with rep_col2:
                    sev = rep.get("severity", "medium")
                    ward_txt = rep.get("matched_ward") or "Unmatched location"
                    st.markdown(f"""
                    <div style="padding:4px 0;">
                      <span class="badge badge-{sev}">{sev}</span>
                      <b style="margin-left:8px;color:#1b4332;">{rep.get('waste_type', 'garbage')}</b>
                      <span style="color:#888;font-size:0.82rem;"> — {ward_txt}</span>
                      <div style="font-size:0.85rem;color:#555;margin-top:4px;">{rep.get('landmark') or rep.get('description') or ''}</div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("<hr style='margin:8px 0;border-color:#eee;'>", unsafe_allow_html=True)

    # ============================================================
    # PAGE — SOCIAL MEDIA EVENTS
    # ============================================================


elif page == "Model Validation":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Model Validation Framework</h2>',
                unsafe_allow_html=True)
    
    if validation_results:
        st.markdown("### 📊 Validation Results")
        
        if 'performance' in validation_results:
            perf = validation_results['performance']
            st.markdown("#### Overall Performance Metrics")
            
            if 'overall' in perf:
                overall = perf['overall']
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("MAE", f"{overall.get('MAE', 0):.2f} kg")
                c2.metric("RMSE", f"{overall.get('RMSE', 0):.2f} kg")
                c3.metric("MAPE", f"{overall.get('MAPE', 0):.2f}%")
                c4.metric("R² Score", f"{overall.get('R2', 0):.3f}")
            
            # Performance thresholds
            st.markdown("#### Performance Thresholds")
            thresholds = {"MAE": 500, "MAPE": 20, "R2": 0.7}
            
            for metric, threshold in thresholds.items():
                actual = overall.get(metric, 0)
                status = "✅ PASS" if actual <= threshold else "❌ FAIL"
                st.markdown(f"{status} {metric}: {actual:.2f} / {threshold}")
    else:
        st.warning("Validation results not available. Run model_validation_framework.py to generate validation data.")

# ============================================================
# PAGE — UNCERTAINTY ANALYSIS
# ============================================================

elif page == "Uncertainty Analysis":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Uncertainty Quantification</h2>',
                unsafe_allow_html=True)
    
    if not uncertainty_results.empty:
        st.markdown("### 📊 Prediction Uncertainty Analysis")
        
        # Uncertainty statistics
        st.markdown("#### Uncertainty Statistics")
        
        avg_uncertainty = uncertainty_results['uncertainty_width'].mean()
        avg_relative_uncertainty = uncertainty_results['relative_uncertainty'].mean()
        
        c1,c2,c3 = st.columns(3)
        c1.metric("Avg Uncertainty Width", f"{avg_uncertainty:.2f} kg")
        c2.metric("Avg Relative Uncertainty", f"{avg_relative_uncertainty:.2%}")
        c3.metric("High Uncertainty Predictions", 
                 f"{(uncertainty_results['uncertainty_width'] > uncertainty_results['ensemble_prediction']).sum():,}")
        
        st.markdown("---")
        
        # Uncertainty distribution
        st.markdown("#### Uncertainty Distribution")
        
        if PLOTLY_AVAILABLE:
            fig = px.histogram(uncertainty_results['uncertainty_width'], 
                             title="Uncertainty Width Distribution",
                             nbins=20,
                             labels={'value': 'Uncertainty Width (kg)'})
            st.plotly_chart(fig, use_container_width=True)
        
        # Confidence score distribution
        st.markdown("#### Confidence Score Distribution")
        
        if PLOTLY_AVAILABLE:
            fig = px.histogram(uncertainty_results['confidence_score'],
                             title="Prediction Confidence Distribution",
                             nbins=10,
                             labels={'value': 'Confidence Score'})
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Uncertainty results not available. Run uncertainty_quantification.py to generate uncertainty data.")

# ============================================================
# PAGE — SCENARIO ANALYSIS
# ============================================================

elif page == "Scenario Analysis":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Scenario Analysis & What-If Modeling</h2>',
                unsafe_allow_html=True)
    
    if scenario_results:
        st.markdown("### 🔮 Scenario Analysis Results")
        
        if 'comparison' in scenario_results:
            comparison = scenario_results['comparison']
            
            st.markdown("#### Comparative Scenario Performance")
            
            st.markdown(f"**Best Scenario:** {comparison.get('best_scenario', 'N/A')}")
            st.markdown(f"**Worst Scenario:** {comparison.get('worst_scenario', 'N/A')}")
            
            # Show comparison table
            comparison_df = pd.DataFrame(comparison.get('comparison', {}))
            if not comparison_df.empty:
                st.dataframe(comparison_df, hide_index=True)
        
        if 'recommendations' in scenario_results:
            st.markdown("#### 💡 Decision Support Recommendations")
            
            for rec in scenario_results['recommendations']:
                action = rec.get('action', '')
                priority = rec.get('priority', 'medium')
                
                priority_emoji = "🔴" if priority == 'high' else "🟡" if priority == 'medium' else "🟢"
                
                st.markdown(f"{priority_emoji} {action}")
    else:
        st.warning("Scenario results not available. Run scenario_analysis.py to generate scenario analysis.")

# ============================================================
# PAGE — MULTI-SENSOR FUSION
# ============================================================

elif page == "Multi-Sensor Fusion":

    st.markdown('<h2 style="color:#1b4332;font-family:\'DM Serif Display\';serif;font-weight:400;">Multi-Sensor Satellite Data Fusion</h2>',
                unsafe_allow_html=True)
    
    if not multi_sensor.empty:
        st.markdown("### 🛰️ Multi-Sensor Data Overview")
        
        # Sensor availability
        sensor_cols = [col for col in multi_sensor.columns if col.startswith('satellite_')]
        available_sensors = [col.replace('satellite_', '').replace('_quality', '') for col in sensor_cols]
        
        st.markdown(f"**Available Sensors:** {', '.join(set(available_sensors))}")
        
        # Sensor quality dashboard
        st.markdown("#### Sensor Quality Dashboard")
        
        sensor_quality = {}
        for col in sensor_cols:
            if 'quality' in col:
                sensor = col.replace('satellite_', '').replace('_quality', '')
                avg_quality = multi_sensor[col].mean()
                sensor_quality[sensor] = avg_quality
        
        if sensor_quality:
            sensor_df = pd.DataFrame([
                {'Sensor': sensor, 'Quality Score': f"{quality * 100:.1f}%"}
                for sensor, quality in sensor_quality.items()
            ])
            
            fig = px.bar(sensor_df, x='Sensor', y='Quality Score',
                         title="Sensor Quality Scores",
                         color='Quality Score',
                         color_continuous_scale='RdYlGn')
            st.plotly_chart(fig, use_container_width=True)
        
        # Confidence scores
        if 'sensor_confidence' in multi_sensor.columns:
            st.markdown("#### Sensor Confidence Scores")
            
            fig = px.histogram(multi_sensor['sensor_confidence'],
                             title="Sensor Confidence Distribution",
                             nbins=10,
                             labels={'value': 'Confidence Score'})
            st.plotly_chart(fig, use_container_width=True)
        
        # Fused indices
        if 'fusion_results' in multi_sensor.columns:
            st.markdown("#### Fused Satellite Indices")
            st.json(multi_sensor['fusion_results'].iloc[0] if not multi_sensor['fusion_results'].empty else {})
    else:
        st.warning("Multi-sensor data not available. Run multi_sensor_fusion.py to generate fused satellite data.")

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.markdown("""
<div style='text-align:center;font-size:0.75rem;color:#888;padding:20px 0;'>
  <span style='color:#1b4332;'>Bengaluru Brain — Waste Intelligence</span>
</div>
""", unsafe_allow_html=True)