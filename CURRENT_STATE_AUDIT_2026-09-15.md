# Bengaluru Brain — Current State Audit (2026-09-15)

Prepared by reading the actual code, saved model artifacts, training reports, and the project's own prior audit documents on disk at `D:\major project`. No files were changed, deleted, or refactored to produce this. One environment limitation: a Windows update broke the shell bridge into your machine (`device_bash`) for this session, so file *contents* were inspected via direct file reads/staging rather than by executing `grep`/`pytest`/`git status` live. Anywhere that matters, it's flagged below as "not independently re-run this session."

Your project already contains an unusually thorough internal audit trail — `README.md`, `FINAL_PROJECT_AUDIT.md`, `FINAL_PROJECT_STATUS.md`, `MODEL_CARD.md`, `REAL_DATA_STATUS.md`, and `TEST_REPORT.md`, all at the repo root. This audit cross-checked your brief against those documents *and* against the live source files, and found one important thing those older docs don't yet reflect: **the Random Forest T+120 model has since been trained and wired into the UI/API** (README/TEST_REPORT predate it). Everything below reflects the actual current file state.

---

## A. What is already implemented

- **End-to-end traffic prediction pipeline**: OSMnx-derived Bengaluru road graph → real TomTom-observed traffic on a subset of edges → trained GNN (`traffic_model_real_v1.pth`) for spatial/current-state prediction → OSRM for real route geometry/distance/duration → a fused route result (`/api/predict-enhanced`).
- **A separate, preliminary T+120 Random Forest forecast**, trained on genuine T→T+120 TomTom pairs collected from 8 fixed corridors, now served live via `/api/traffic/forecast-t120/for-route` and `/api/traffic/forecast-t120/model-info`, and rendered in the UI (`TrafficForecastT120.jsx`, behind a "Predict After 2 Hours" button in `TrafficPredictionPanel.jsx`).
- **A second, independent 2-hour route forecast** (`traffic_forecast_service.py`, `/api/traffic/forecast-2h`) — a transparent hybrid extrapolation (real current GNN state × a real historical hour-of-day ratio), explicitly *not* a trained model, kept separate from the RF above.
- **Real-time-style incident/anomaly detection** (`traffic_incident_service.py`) with the exact hierarchy your brief describes: `NORMAL_CONGESTION → HEAVY_CONGESTION → TRAFFIC_ANOMALY → POSSIBLE_TRAFFIC_BLOCKAGE → PROVIDER_CONFIRMED_INCIDENT`.
- **A citizen-alert eligibility layer** (`traffic_alert_eligibility.py`) sitting on top of the detector: cooldown/dedup (30 min), severity-increase and location-change overrides, radius-based user matching, and bilingual (English/Kannada) message assembly via `kannada_messages.py`.
- **USI (Urban Stress Index)** fusing Traffic + Waste (`integration/usi_engine.py`), currently `0.5×traffic + 0.5×waste` with a documented compounding bonus.
- **Weather integration** (`weather_logic.py`, OpenWeatherMap) as contextual/downstream information, not a GNN input.
- **369-ward registry** with a real OSM-derived ward boundary/identity system (`ward_registry_service.py`, `ward_stress.py`), simulated per-ward traffic *score* on top of that real identity.
- **A full React dashboard** (`traffic_module/frontend`) with 6 tabs (Overview/Traffic/Waste/USI/Alerts/Routing), and the Traffic tab's section order is enforced by an explicit comment block in `App.js` (see §I and §G).
- **A `waste_module/` directory already exists** in the repo (your friend's or an earlier placeholder — not inspected in depth per your instruction not to touch Waste). Its presence is noted here only so you know it's already on disk; nothing about it was analyzed or changed.

## B. What is working (verified by reading the actual code/artifacts, not just docs)

- `traffic_model_real_v1.pth` loads and its checkpoint carries `node_feature_mean/std`, `scalar_feature_mean/std` inline (no separate scaler file to drift) — confirmed in `real_gnn_service.py` and `MODEL_CARD.md`.
- The RF model file `traffic_module/backend/forecasting/models/t120_preliminary_rf_model.joblib` exists (3.5MB) alongside its metrics report, and is loaded read-only for inference by `t120_preliminary_service.py`, which explicitly states in its own docstring: "Never retrains or modifies the model... Never forecasts for any road other than the exact 8 real OSM segments the model was trained on."
- `app.py` (111KB, single canonical backend, confirmed live) registers 30+ real routes including `/api/predict-enhanced`, `/api/traffic/forecast-t120/*`, `/api/traffic/forecast-2h`, `/api/traffic/incidents`, `/api/usi/*`, `/api/alerts/*`, `/api/waste/*`, `/api/wards/*`, `/api/health` — a full list is in §I.
- `main.py` still exists but is confirmed deprecated (both by its own docstring per your prior audit and by `app.py` being the file every current script/README points to).
- The Traffic page's five-section order is enforced in code, not just convention — `App.js` has an explicit inline comment: *"FIXED Traffic-page section order — do not reorder..."* listing exactly your five sections in your exact order (see §G).
- The incident classification vocabulary never includes the word "accident" — confirmed directly in `traffic_incident_service.py` and cross-referenced against a unit test name (`test_never_classifies_as_accident_string`) in `tests/test_traffic_forecasting_and_incidents.py`.
- `PROVIDER_CONFIRMED_INCIDENT` is real, tested code that is **honestly unreachable in production** — no TomTom incidents-feed endpoint exists in this project's TomTom integration, and every incident API response says `provider_incident_feed_configured: false`.
- The RF's chronological train/val/test split (779/167/168 = 1,114) has an explicit, checked leakage guard in `train_t120_preliminary_model.py` (`verify_no_leakage()`), and the saved metrics report confirms `leakage_detected: false`.

## C. What is partially working

- **T+120 RF forecast on the Traffic page**: works, but only for the exact 8 trained corridors (Outer Ring Road, Hosur Road, Bellary Road, Old Madras Road, Tumkur Road, Bangalore-Mysore Road, Marathahalli Underpass, Silk Board Flyover) and only when the route's real monitored-segment coverage is ≥95% of route distance (per `TrafficPredictionPanel.jsx`'s own comment). For every other route, the UI honestly falls back to a "GNN BASELINE ESTIMATE" (today's GNN current-state prediction, explicitly labeled as *not* a learned forecast) rather than hiding the panel or fabricating a number.
- **RF vs. persistence baseline**: on the held-out chronological test set, the RF does *not* clearly beat a naive "future speed = current speed" baseline (MAE 2.901 vs. 2.738 km/h; RF wins on RMSE and R² only). `t120_preliminary_metrics.json` records this honestly (`beats_baseline_overall: false`), and the frontend surfaces the same "NOT YET" label rather than hiding it.
- **`/api/wards/full/schema`**: real per-ward traffic/waste/USI, but per your prior audit takes ~10-12s per call (369 direct GNN lookups) — fine for a dedicated table view, not for polling.
- **Alerts module + Traffic incident alerts**: `traffic_alert_eligibility.py` explicitly reads from, but never re-computes, the incident detector's output, and is deliberately kept separate from the pre-existing `integration/alert_state.py` USI-alert cooldown system. Two parallel alert/cooldown systems currently exist (USI-based and traffic-incident-based) — both real, neither fake, but worth knowing they are not unified.

## D. What is simulated

- **Ward-level `traffic_score`** in `ward_stress.py` — random-based (`random.randint`/`random.uniform`), regenerated per request. Ward *identity* (369 real OSM wards, boundaries, IDs) is real; the *score* is not. Labeled `SIMULATED_WARD_STRESS` end-to-end into USI and the UI, per your instruction.
- **SMS/alert delivery** — every alert is composed for real (English+Kannada, real trigger conditions) but delivery is `SIMULATED_NOT_SENT` / previewed only. No SMS provider is wired in, by design.
- **`PeakHoursChart.jsx`** — labeled in the code itself as "illustrative, not a live forecast."
- **Waste scoring** (only mentioned here because USI depends on it) — per your prior audit, the currently-served waste number is a land-use-density heuristic (`WASTE_HEURISTIC_MODEL`), not the trained satellite RandomForest that also exists in the codebase but isn't wired into the live path. This is Waste's own concern, not something this audit touched or recommends touching now.

## E. What is genuinely trained

- **`traffic_model_real_v1.pth`** — 3× GCNConv + edge MLP, trained offline (`train_gnn_real_v1.py`, seed 42), loaded once for inference. This session could not re-run the training script live (no shell bridge), but the checkpoint file, its stored metrics, and the inference code path (`real_gnn_service.py`) were all read directly and are internally consistent with the metrics you quoted:
  - Train: MAE 3.9116 / RMSE 5.9681 / R² 0.6950
  - Spatial val: MAE 6.2367 / RMSE 8.3979 / R² 0.6367
  - Spatial test: MAE 5.9246 / RMSE 7.6847 / R² 0.6224
  - Temporal test: MAE 3.0188 / RMSE 4.6394 / R² 0.7407
  (These are byte-identical to the numbers you gave, and to `traffic_model_real_v1_metrics.json` on disk.)
- **`t120_preliminary_rf_model.joblib`** — `RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)`, trained on 1,114 genuine T→T+120 pairs from 8 segments, chronological 70/15/15 split (779/167/168), confirmed via `t120_preliminary_metrics.json`:
  - Train: MAE 1.143 / RMSE 1.572 / R² 0.9684
  - Validation: MAE 2.421 / RMSE 3.148 / R² 0.8664
  - Test: MAE 2.901 / RMSE 3.674 / R² 0.8384
  - Persistence baseline (test): MAE 2.738 / RMSE 3.695 / R² 0.8364
  These match your brief exactly. Both models are static, offline-trained artifacts loaded read-only at inference time — neither is retrained per request.

## F. What data currently exists

| Dataset | Location | Size / count |
|---|---|---|
| Bengaluru OSM road graph | `traffic_module/data/{edges,nodes}.csv`, `backend/data/bengaluru_graph.pkl` | ~393,090 edges citywide |
| GNN training subgraph | referenced by `train_gnn_real_v1.py` / `real_gnn_service.py` | 4,304 real nodes, 5,819 real edges; 749 labeled with real TomTom ground truth |
| 8-segment forecasting collector output | `backend/forecasting/data/forecast_segments_history.csv` (+ `_clean.csv`) | 1,432 raw rows → 1,410 OK / 22 ERROR, 8 unique OSM edges, span 2026-09-10 09:56 → 2026-09-11 13:39 (~27.7h), median revisit ~5.2 min |
| T→T+120 pairs | `backend/forecasting/data/forecast_segments_pairs_t120.json` | 1,114 pairs (matches your brief exactly) |
| Older, separate 24h ward-rotation collection | `backend/bengaluru_traffic_history.csv` (31MB) / `data/forecast/bengaluru_traffic_history_clean.csv` | 946 raw / 930 valid rows, 369 distinct edges, **0 valid T+120 pairs** — this is why a *second*, fixed-8-segment collector had to be built; the two datasets are intentionally kept separate |
| Expanded 21-segment collector | `backend/forecasting/collect_forecast_segments_expanded.py` | **Built but not yet run** — no `bengaluru_t120_expanded_history.csv` output file exists yet anywhere on disk |
| Ward registry | `integration/geo/ward_registry.json` (per prior audit) | 369 real Bengaluru wards from OSM Overpass |

## G. What should NOT be changed

Everything your brief lists, confirmed as currently true in the code — plus one addition:

1. **Traffic page section order** — enforced by an explicit code comment in `App.js` (lines ~279-292): AI/T+120 Prediction → Route Map → Historical Context → Live Traffic Status → Bengaluru Traffic Map. This is not just a convention to remember; it's already annotated in the source as fixed.
2. **`app.py` as the canonical backend entry** — `main.py` is deprecated and superseded; every live script, README, and run instruction points at `app.py`.
3. **GNN/RF separation** — both models' own docstrings explicitly state they don't touch or retrain each other. `t120_preliminary_service.py`'s docstring: *"Never retrains or modifies the model... This is completely separate from... the existing current-state GNN prediction."*
4. **The 8-segment forecasting dataset must stay separate from the 369-ward rotation dataset** — `collect_forecast_segments.py` and its expanded sibling both write to their own CSVs specifically so the trained RF's exact training data never silently changes underneath it.
5. **OSRM routing must stay real road geometry** — confirmed still the case in `routing_service.py`.
6. **Incident vocabulary must never say "accident"** — enforced by a named unit test, not just a style rule.
7. **Weather stays out of the GNN's own feature set** — confirmed: `real_gnn_service.py`'s node/scalar features are graph-structural + time-of-day only, no weather field.
8. **Do not touch `waste_module/`** — present on disk, not inspected, not to be modified until you hand off your friend's version.
9. **Two backup folders (`traffic_module_backup/`, `traffic_module_backup - Copy/`) exist at the project root** and were preserved untouched by prior sessions per your standing rule — this audit did not touch them either.

## H. What should be improved after collecting more data

- **The 8-segment RF is explicitly "preliminary" by its own saved metadata** (`t120_preliminary_metrics.json`'s own `model_type` field says so verbatim) and does not clearly beat a persistence baseline on MAE. More real T→T+120 pairs — ideally spanning multiple days/weekday-weekend cycles rather than ~27.7 hours — is the stated path to a defensible "final" model.
- **The expanded 21-segment collector is built and ready but has never been run** — this is the concrete, already-implemented next step for broadening real coverage beyond the original 8 corridors, exactly matching your "we now want to collect more real data" instruction. No new code would be needed to start it; it needs to actually run for an extended period.
- **Citywide GNN coverage remains ~0.2% ground-truth-validated** (749/393,090 edges) plus an extrapolated-but-unvalidated tier (per `MODEL_CARD.md`, ~1.4% total real-model-reachable). Expanding this requires more TomTom collection over time, not an architecture change.
- **Ward-level `traffic_score` stays simulated** until the "road-level predictions → map to wards → aggregate" pipeline your brief describes in §10 is actually built — it is not implemented today (see §D).

## I. Exact files responsible for each major component

| Component | File(s) |
|---|---|
| Backend entry point | `traffic_module/backend/app.py` (canonical); `main.py` (deprecated, do not use) |
| GNN inference | `traffic_module/backend/real_gnn_service.py` → loads `traffic_module/models/traffic_model_real_v1.pth` |
| GNN training | `traffic_module/models/train_gnn_real_v1.py`, `prepare_real_traffic_dataset.py` |
| RF (T+120) training | `traffic_module/backend/forecasting/train_t120_preliminary_model.py` |
| RF (T+120) inference | `traffic_module/backend/forecasting/t120_preliminary_service.py` → loads `forecasting/models/t120_preliminary_rf_model.joblib` |
| T+120 data collection (8 fixed segments) | `traffic_module/backend/forecasting/collect_forecast_segments.py` |
| T+120 data collection (21-segment expansion, not yet run) | `traffic_module/backend/forecasting/collect_forecast_segments_expanded.py` |
| T→T+120 pairing | `traffic_module/backend/forecasting/forecast_dataset_builder.py`, `csv_validator.py` |
| Alternate hybrid 2h forecast (non-ML) | `traffic_module/backend/traffic_forecast_service.py`, `forecasting/historical_pattern.py` |
| OSRM/routing | `traffic_module/backend/routing_service.py` |
| Weather | `traffic_module/backend/weather_logic.py` |
| Incident/anomaly detection | `traffic_module/backend/traffic_incident_service.py` |
| Citizen alert eligibility | `traffic_module/backend/traffic_alert_eligibility.py` |
| Bilingual messages | `traffic_module/backend/kannada_messages.py` |
| Ward registry / stress | `traffic_module/backend/ward_registry_service.py`, `ward_stress.py` |
| USI fusion | `integration/usi_engine.py` (root-level `integration/` package) |
| Frontend app shell + tab/section order | `traffic_module/frontend/src/App.js` |
| Traffic tab: AI/T+120 panel | `components/TrafficPredictionPanel.jsx`, `components/TrafficForecastT120.jsx` |
| Traffic tab: Route Map | `components/RouteMap.jsx` |
| Traffic tab: Historical Context + Live Traffic Status | `components/TrafficForecastAndIncidents.jsx` |
| Traffic tab: Bengaluru Traffic Map | `components/WardMap.jsx` |
| Traffic tab: Ward Stress Monitor | `components/WardStressGrid.jsx` |
| Backend tests | `traffic_module/backend/tests/*.py` (9 files, incl. `test_t120_preliminary_forecast.py`, `test_traffic_alert_eligibility_and_location.py`, `test_incident_alerts_architecture.py`) |

## J. Recommended next steps, in priority order

1. **Do nothing to the code yet** — you asked for understanding first; this document is that. Review it before anything else happens.
2. **Re-verify current test/build status live**, since the shell bridge to your machine was unavailable this session: `cd traffic_module\backend && python -m pytest tests\ -v` and `cd traffic_module\frontend && npm run build`. The "117/117" figure is inherited from the project's own prior `TEST_REPORT.md`/session history, not re-executed by this audit.
3. **Check `git status`** — a prior internal audit (`FINAL_PROJECT_AUDIT.md`, §11) flagged that a large amount of working-tree progress was uncommitted at that time, plus a `.gitignore` gap around large model/CSV files. Worth a quick look before any further work, independent of anything traffic-related.
4. **Decide whether to start the already-built 21-segment expanded collector** (`collect_forecast_segments_expanded.py`) now, since more real T+120 data is your stated next priority and the tooling for it already exists and has simply never been run.
5. **Only after your review/approval**: any actual code changes, in small increments, with tests re-run after each one — per your own stated principles.

---

*This audit is a snapshot from direct file inspection today. Two things it could not do this session: execute `pytest`/`npm run build` live, and check `git status`, because the shell bridge into your machine (`device_bash`) is currently broken by a recent Windows update on this session's side — file reads and directory listings worked normally throughout, so the content above is accurate, just not test-execution-verified.*
