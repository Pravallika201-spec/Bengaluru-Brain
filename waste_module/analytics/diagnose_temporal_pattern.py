"""
Diagnostic: shows the day-by-day 85th-percentile threshold across all 7
days, and the raw daily values for whichever wards newly crossed into
CRITICAL between day 5 and day 7 — to see whether growth is smooth
(which a trend model could predict) or a discontinuous jump on a specific
day (which no smooth trend model ever could, since the signal isn't in
the earlier days at all).

USAGE (from waste_module/analytics/, same as the other scripts):
    python diagnose_temporal_pattern.py
"""

import os
import pandas as pd
import geopandas as gpd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCESSED_DIR = os.path.join(BASE_DIR, "waste_module", "data", "processed")
TEMPORAL_FILE = os.path.join(PROCESSED_DIR, "bengaluru_temporal_predictions.gpkg")
GRID_AREA_MAPPING_FILE = os.path.join(PROCESSED_DIR, "bengaluru_grid_area_mapping.csv")


def find_col(df, candidates):
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


GRID_ID_CANDIDATES = ["Grid_ID", "grid_id", "GridID", "grid_cell_id", "cell_id"]

temporal = gpd.read_file(TEMPORAL_FILE, layer="temporal_predictions")
mapping = pd.read_csv(GRID_AREA_MAPPING_FILE)
temporal["prediction_date"] = pd.to_datetime(temporal["prediction_date"])

t_id = find_col(temporal, GRID_ID_CANDIDATES)
m_id = find_col(mapping, GRID_ID_CANDIDATES)
m_area = find_col(mapping, ["area_name"])

merged = temporal.merge(
    mapping[[m_id, m_area]].rename(columns={m_id: t_id, m_area: "area_name"}),
    on=t_id, how="inner"
)
ward_day = merged.groupby(["area_name", "prediction_date"])["predicted_daily_waste_kg"].sum().reset_index()

dates = sorted(ward_day["prediction_date"].unique())

print("=" * 70)
print("DAY-BY-DAY THRESHOLD TRAJECTORY (85th percentile of ward totals)")
print("=" * 70)
for d in dates:
    day_vals = ward_day[ward_day["prediction_date"] == d]["predicted_daily_waste_kg"]
    threshold = day_vals.quantile(0.85)
    day_name = pd.Timestamp(d).day_name()
    print(f"{pd.Timestamp(d).date()} ({day_name}): 85th percentile = {threshold:,.1f}  "
          f"| total city waste = {day_vals.sum():,.0f}  | mean ward = {day_vals.mean():,.1f}")

print("\n" + "=" * 70)
print("WARDS THAT NEWLY CROSSED INTO CRITICAL (day5 threshold vs day7 actual)")
print("=" * 70)
day5, day7 = dates[4], dates[-1]
day5_threshold = ward_day[ward_day["prediction_date"] == day5]["predicted_daily_waste_kg"].quantile(0.85)
already_critical = set(
    ward_day[(ward_day["prediction_date"] == day5) &
             (ward_day["predicted_daily_waste_kg"] >= day5_threshold)]["area_name"]
)
day7_data = ward_day[ward_day["prediction_date"] == day7]
newly_critical = day7_data[
    (day7_data["predicted_daily_waste_kg"] >= day5_threshold) &
    (~day7_data["area_name"].isin(already_critical))
]["area_name"].tolist()

print(f"Wards newly crossing: {newly_critical}\n")

for ward in newly_critical:
    print(f"\n--- {ward} — full 7-day trajectory ---")
    ward_data = ward_day[ward_day["area_name"] == ward].sort_values("prediction_date")
    for _, row in ward_data.iterrows():
        day_name = pd.Timestamp(row["prediction_date"]).day_name()
        print(f"  {pd.Timestamp(row['prediction_date']).date()} ({day_name}): "
              f"{row['predicted_daily_waste_kg']:,.1f} kg")