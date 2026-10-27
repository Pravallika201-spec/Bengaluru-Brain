# Bengaluru Brain — Final Data Truth Report

Every claim below was verified by actually running code in this session (live inference, live API calls, direct file inspection) — not inferred from reading code alone. Where a number could not be verified, that is stated explicitly rather than assumed.

---

## TRAFFIC

### Real source
- **Routing**: real OSRM (`router.project-osrm.org`), live HTTP call per request, real road-network distance/duration. Verified for 6 routes this session (see Test Matrix).
- **Coordinates**: single canonical source, `traffic_module/backend/location_data.py`. Hebbal/Silk Board corrected this project to their actual junction coordinates (verified against real OSM road nodes) after a prior bug where a 3-decimal-rounded centroid caused OSRM to silently route via the wrong corridor (17.24 km via Sankey/Millers Road) instead of the real one (20.87 km via Hebbal Flyover → Bellary Road → Outer Ring Road → Bannerghatta Road).
- **Weather**: real OpenWeatherMap call when `OPENWEATHER_API_KEY`/`OWM_API_KEY` is set; explicitly labeled `FALLBACK` when not (no key configured in this environment — verified live, `data_sources.weather` returns `"Estimated fallback (FALLBACK)"`).
- **GNN**: real, retrained `traffic_model_real_v1.pth` — re-verified this session directly from the checkpoint file:
  - Architecture: 3× `GCNConv` (node embedding) + a 2-layer edge MLP (`edge_mlp.0`/`edge_mlp.2`), `node_in_dim=3`, `scalar_dim=14`.
  - Node features (order verified to match `real_gnn_service.py`'s inference code exactly): `degree, avg_incident_maxspeed_kph, avg_incident_length_m`.
  - Scalar/edge features (order verified to match exactly): `edge_length_m, base_speed_kph, hour_sin, hour_cos, is_weekend, frc_FRC0..frc_UNKNOWN` (9 one-hot road-class dummies).
  - Target: `current_speed_kmh` (real TomTom-observed speed).
  - Normalization: mean/std stored **inside the checkpoint** (`node_feature_mean/std`, `scalar_feature_mean/std`) and loaded directly at inference — no separate/divergent scaler file, no risk of train/inference mismatch.
  - Training data: 760 real TomTom-observed OSM edges (single spatial snapshot, 2026-08-27) + 13 real segments polled repeatedly over ~3 days. `trained_at: 2026-09-03T07:47:51`.
  - **Stored test metrics** (read directly from the checkpoint, not re-derived): spatial-test MAE=5.92 km/h, RMSE=7.68, **R²=0.622** (n=125, unseen edges); temporal-test MAE=3.02, RMSE=4.64, **R²=0.741** (n=185, unseen future timestamps, small sample — flagged as such).
  - **Live inference re-verified this session**: ran `predict_edge()` directly with full logging (edge id, road name, all 5 base scalar inputs + one-hot, output). The neural network's `forward()` genuinely executes and returns a non-hardcoded value that varies per edge/time — not a lookup table.

### Coverage — three different, now clearly distinguished, numbers
1. **Edge-count coverage**: ~750 of 393,090 total Bengaluru OSM edges have real ground-truth (~0.2%).
2. **Route-level coverage** (`coverage.percentage_real` in every `/api/predict-enhanced` response): what fraction of ~40 sampled points along *this specific route* fall within 200m of a real monitored edge. Measured at **11.9%–12.2%** across all 6 test routes this session.
3. **Ward-level coverage** (`/api/wards`, new this phase): of 369 real Bengaluru wards, how many contain at least one real signal. **368/369 wards have some real signal** (13 REAL_HISTORICAL + 249–265 ML_PREDICTION + 90–106 LIMITED_COVERAGE-only); only 1 ward has none. This number is *much* higher than #1 because the ~750 edges are spread across many different wards rather than clustered — a real, verified, non-contradictory fact, not an inflation of #1.

**Explicit distinction the audit required**: ward existing ≠ ward mapped ≠ real traffic data ≠ GNN coverage ≠ prediction available. `ward_registry.json` records each separately per ward: `waste_data_available`, `traffic_named_locations`, `real_gnn_edges_count`, `real_gnn_temporal_edge`, `tomtom_collector_targets`, and only then a derived `coverage_class`. A ward with `LIMITED_COVERAGE` has a waste-area or named-location match but **zero** traffic-model signal — the API says so plainly, it does not imply a prediction exists.

### ETA/Speed formula — traced number-by-number
- **Distance**: `primary_route["distance_km"]` — OSRM's own reported route distance. Never recalculated, never straight-line.
- **Free-flow/base speed**: `distance_km / base_time_min × 60`, where `base_time_min` is OSRM's static duration (OSRM has no separate "current" duration — verified in `routing_service.py`).
- **Current speed**: `distance_km / current_time_min × 60`, where `current_time_min = base_time_min × weather_multiplier (+ incident minutes if any)`. Verified live this session: `distance/current_time×60` equals the reported `current_speed_kmh` to 1 decimal for all 6 test routes — **exact**, not approximate.
- **Predicted speed** (when `traffic_source=REAL_GNN`): **directly the real GNN's `avg_predicted_speed_kmh`** for the nearest real monitored segment(s) — not `current_speed × 1.10`, not any fixed multiplier. That old formula (`build_model_prediction()` in `app.py`, `current_speed × (0.92 + 0.18×(1-weather_factor))`) is **no longer in the live `/api/predict-enhanced` path** — confirmed by reading the current code and by the fact that all 6 test routes' predicted speeds (24.9–33.9 km/h) are materially *lower* than current speed (43.6–50.7 km/h), the opposite direction a `×1.10` formula would produce.
- **Predicted ETA**: `current_time_min ÷ slowdown_ratio`, where `slowdown_ratio = real_avg_speed / free_flow_speed_est` (clipped to [0.2, 1.3]). Verified algebraically and numerically this session: this construction guarantees `predicted_time_min == distance_km / predicted_speed_kmh × 60` exactly whenever weather is clear (true for all 6 test routes, confirmed to the reported decimal). **Known, documented, currently-inactive edge case**: if weather is non-clear *and* the GNN covers the route, the weather multiplier compounds on top of the GNN's ratio, so the identity would not hold exactly in that specific combination — not observable right now since no live weather key is configured, but recorded here rather than silently left unexamined.
- **Confidence**: literally `real_gnn_signal.model_metrics.spatial_test.R2` (0.62) when GNN-covered — not an invented formula. `0.3` fixed when falling back to `HEURISTIC_FALLBACK` (no live/ML signal at all).
- **Congestion score / "AI Congestion Score"**: the backend does not compute a continuous congestion percentage. The frontend gauge maps the discrete `traffic` level (LOW/MODERATE/HIGH/SEVERE — itself derived from the real slowdown ratio when GNN-covered, or from delay vs. base time otherwise) to a fixed midpoint (15/45/70/90%) purely for the gauge's visual fill. This is disclosed in the component's own comment and via the "Estimated Congestion"/heuristic-vs-AI header switch, not hidden — but it remains a *display* score, not an independently computed metric. This is the one number in the traffic pipeline that is a **display convenience, not a first-class computed value** — flagged explicitly rather than presented as precise.
- **`traffic_source` / `model_info.model`**: `"REAL_GNN"` only when `real_gnn_service.get_route_traffic_signal()` actually found a real matched segment (verified: `covered=True` and non-empty `matched_segments`); otherwise `"HEURISTIC_FALLBACK"` with `model_info.model` explicitly stating "no live traffic or real-GNN coverage for this route" — verified live this session by forcibly disabling the GNN lookup and confirming `current_speed_kmh == predicted_speed_kmh` (no fabricated divergence) and `confidence == 0.3`.

### Real-time collection status (verified live via `/api/traffic/data-status`)
```
collector_configured: false   (no TOMTOM_API_KEY in this environment)
mapping_targets: 39, mapping_matched: 35   (real OSM-node-snapped targets)
feed_status: STALE   (last real observation ~6700+ minutes old)
```
The collector script (`collect_live_traffic_history.py`) supports `--once` (cron-friendly) and continuous modes, both real TomTom API calls, both append real timestamped rows. **No live traffic is fabricated in its absence** — every response that would need it says `STALE`/`HEURISTIC_FALLBACK` instead.

---

## WASTE — corrected after this session's audit found a real mislabeling

### What actually generates the displayed numbers
Traced the full chain: `bengaluru_grid.csv` (real OSM-derived grid, land-use polygons) → `prediction/waste_estimator.py` → `analytics/area_overflow_predictor.py` → `bengaluru_area_overflow_predictions.csv` (the file the dashboard reads).

**Finding**: the number displayed is **not** output from the trained satellite RandomForest model that also exists in this codebase (`ml/satellite_waste_model.py`, `ml/satellite_waste_random_forest.joblib` — a real, 20.9MB trained model file, confirmed to exist, but **not in this live data path**). Instead:
1. `waste_estimator.py` computes `estimated_daily_waste_kg = grid_area_km² × Σ(landuse_ratio × WASTE_INTENSITY_weight) × 1000`, where `WASTE_INTENSITY` (residential=0.80, commercial=1.50, industrial=1.20, …) are **hand-picked constants**, not empirically fit or sourced from published BBMP generation-rate data.
2. `temporal_predictor.py` multiplies this by a **fixed** `DAY_MULTIPLIERS` table (Mon=1.00 … Sat=1.15) that repeats identically every week.
3. `area_overflow_predictor.py` then rank-normalizes `Total_Predicted_Waste_kg`/`Maximum_Predicted_Waste_kg`/`Average_Temporal_Score` **within each date** (percentile rank, not an absolute threshold) into `Overflow_Risk_Score = 0.50×waste_pctile + 0.30×peak_pctile + 0.20×score_pctile`.

**Verified directly** (not inferred): for grid `BG_000001`, `estimated_daily_waste_kg = 382.256924` is **byte-identical across all 7 stored dates** (2026-08-23 through 2026-08-29) — only the day-of-week multiplier differs (1.10, 1.00, 1.00, 1.02, 1.03, 1.08, 1.15). This is conclusive: the "7 days of predictions" are one static spatial estimate replayed through a fixed weekly pattern, not 7 independent forecasts.

**Consequence for interpretation**: `Overflow_Risk_Score` is a real, deterministic, land-use-density-based **relative ranking** (genuinely useful as a prioritization signal — commercial/industrial-dense areas do plausibly generate more waste than parks) but it is **not** a validated ML prediction and **not** a live day-to-day forecast. It was previously labeled `WASTE_MODEL_REAL` throughout the codebase, which overstated it. **Fixed this session**: relabeled to `WASTE_HEURISTIC_MODEL` everywhere (`integration/waste_signal.py`, `integration_bridge.py`, `UsiPanel.jsx`, `WastePanel.jsx`, `ModuleStatusBar.jsx`, `OverviewPanel.jsx`), with the `detail` field now explicitly saying **"MODEL PREDICTION USING LAST AVAILABLE DATA"** rather than implying a live model run.

### Data integrity checks (all real, all verified this session)
- **Duplicates**: zero duplicate `(area_osm_id, prediction_date)` or `(area_name, prediction_date)` pairs across 2,562 rows.
- **Column-swap check**: `Total_Predicted_Waste_kg ÷ Grid_Cell_Count` matches `Average_Predicted_Waste_kg` to floating-point precision (~1e-13) for every row — no swapped columns.
- **Area-to-ward mapping**: `area_osm_id` **is** the real OSM ward relation ID directly (not a fuzzy match) — verified 366/366 exact matches against a live Overpass fetch of the 369 real Bengaluru wards. All 366 area names are real Bengaluru locality names (Talagattapura, Hemmigepura, Agaram, …), not placeholders.
- **Units**: kilograms, consistently, from grid area (km²) × intensity × 1000. `Overflow_Risk_Score` is a unitless 0–100 percentile score, not kg — the dashboard does not conflate the two (verified: `Total_Predicted_Waste_kg` and `Overflow_Risk_Score` are shown as separate fields everywhere checked).
- **Citizen reports**: real JSON persistence (`waste_module/waste_module/data/citizen_reports.json`), a bounded (+5/report, capped +15) escalation onto `Overflow_Risk_Score`, always reported separately as `citizen_report_bonus`/`citizen_report_count_7d` — never merged invisibly into the base score. Labeled `CITIZEN REPORTED` in the raw record, distinct from the model's own `model_score`.

### Real-time waste data
None exists (no IoT sensors, no BBMP live feed — none invented). The architecture (citizen report store, area-level aggregation) is ready for future ingestion; current status is honestly `MODEL PREDICTION USING LAST AVAILABLE DATA`, not live.

### OR-Tools routing (unchanged from prior verification, re-confirmed available)
Real capacitated VRP solve exists and was previously verified live (8 vehicles, 50 real areas, 120.9 km total). Feeds off `bengaluru_priority_areas.csv` via the column-mapping fix from an earlier session.

---

## USI

Formula (`integration/usi_engine.py`, unchanged in logic, re-verified live): `USI = 0.5×traffic_score + 0.5×waste_score`, +10 compounding bonus when both scores ≥60 (documented rationale: congested roads impede waste-truck access), band cutoffs Green≤40/Yellow≤60/Orange≤80/Red>80. Every result carries `traffic.score/level/source/detail`, `waste.score/level/source/detail` (now correctly `WASTE_HEURISTIC_MODEL`), `coverage_status`, `partial_data`, `compounding_bonus_applied`, `reason`, `timestamp`. Verified live for HSR Layout: `Traffic: 17.2 (REAL_GNN)`, `Waste: 72.4 (WASTE_HEURISTIC_MODEL)`, `USI: 44.8`, `Band: Yellow` — matches the exact transparency format requested.

Geographic coverage: 24/25 curated traffic locations joined to a real waste area (6 exact-name, 18 real spatial nearest-neighbor within 3km); Electronic City has no waste area within range and is honestly reported as unmapped, not forced.

---

## ALERTS

Event-driven classification (`URGENT_COMBINED`/`TRAFFIC_ONLY`/`WASTE_ONLY`/`GENERAL`/`ESCALATION`) confirmed live this session. Cooldown/dedup (`alert_state.py`, 30-minute window per area+band, escalation always overrides) re-verified: a repeat call for the same area/band within the window returns `status: "SUPPRESSED_DEDUP"` with a `dedup_reason`, not a duplicate send. **Generated vs. delivered, explicitly distinguished**: every simulated send returns `status: "SIMULATED_NOT_SENT"` — no code path anywhere claims an SMS was actually delivered. No real SMS provider is connected (by design, per project rules).

---

## FINAL PROJECT STATUS

| Domain | Status |
|---|---|
| Traffic | **PARTIAL — real where covered.** Real routing/weather/GNN inference confirmed by direct re-verification; real coverage 12% route-level / 368-of-369-ward-level; honest `HEURISTIC_FALLBACK` elsewhere. |
| Waste | **PARTIAL — real data, heuristic (not ML) scoring, corrected this session.** Real OSM land-use data, real area→ward mapping, deterministic (not live) temporal pattern, now labeled accurately. |
| USI | **REAL fusion, PARTIAL coverage** (24/25 locations) — formula and provenance genuinely computed, not fixed. |
| Alerts | **REAL logic, SIMULATED delivery** — always labeled as such. |
| Routing (OR-Tools) | **REAL** — genuine capacitated VRP solve on real data. |
| 369 Wards | **REAL registry, PARTIAL data coverage** — 369 real wards confirmed via live OSM fetch; 368/369 have *some* real signal; 0 have `REAL_LIVE` (needs `TOMTOM_API_KEY`). |
| Real-time | **NOT ACTIVE** (no API key in this environment) — architecture is real and ready, status is honestly reported as `STALE`/`MISSING`, never fabricated. |
| GNN | **REAL inference, re-verified live** this session with explicit logging; weak-but-real accuracy (R²=0.62 spatial). |
| Frontend | Builds clean (verified this session). |
| Tests | pytest 3/3 passed (re-run after every change this session); all 6 requested routes tested live with passing consistency checks; edge cases (invalid location, unknown area, forced no-coverage) tested and handled without crashing. |
