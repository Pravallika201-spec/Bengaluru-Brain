# Bengaluru Brain — Urban Predictive Intelligence

Traffic prediction + waste intelligence, fused into one Urban Severity Index
(USI), driving bilingual (English + Kannada) citizen alerts. Built on a
retrained real GNN, a real satellite/GIS waste model, and a real OR-Tools
routing solve.

**This README is the single source of truth for running the project.**
For the full technical audit (what's real, simulated, broken, or legacy, and
why), see [FINAL_PROJECT_AUDIT.md](FINAL_PROJECT_AUDIT.md). For the current
end-to-end verified status, see [FINAL_PROJECT_STATUS.md](FINAL_PROJECT_STATUS.md),
[REAL_DATA_STATUS.md](REAL_DATA_STATUS.md), [MODEL_CARD.md](MODEL_CARD.md),
and [TEST_REPORT.md](TEST_REPORT.md).

---

## Architecture

```
 TomTom API (needs TOMTOM_API_KEY)      OpenWeatherMap API (needs key, has fallback)
        │ (collector, currently STALE                │
        │  — see "Real-time status" below)            │
        ▼                                              ▼
traffic_module/data/collect_live_traffic_history.py   traffic_module/backend/weather_logic.py
        │ (timestamped, appended)
        ▼
traffic_module/data/live_traffic_history.csv  ──┐
traffic_module/data/{edges,nodes}.csv (real OSM)│
                                                  ▼
                            traffic_module/models/train_gnn_real_v1.py
                                    (retrained GNN: spatial R²=0.62,
                                     temporal R²=0.74, ~750 real edges)
                                                  │
                                                  ▼
                    traffic_module/backend/real_gnn_service.py
                                                  │
        ┌─────────────────────────────────────────┼───────────────────────────┐
        ▼                                          ▼                           ▼
traffic_module/backend/app.py (FastAPI, :8000) ◄── ward_stress.py (SIMULATED   routing_service.py
   /predict-route  /api/predict-enhanced           fallback outside real GNN)  (real OSRM/ORS)
   /api/usi/*  /api/alerts/*  /api/waste/*
   /api/traffic/data-status  /api/health
        │
        │ imports (bridge, no logic of its own)
        ▼
traffic_module/backend/integration_bridge.py
        │
        ▼
integration/ package:
   traffic_signal.py ── real_gnn_service.py (traffic severity)
   waste_signal.py   ── waste_module CSV + citizen_reports_store.py (waste severity + citizen escalation)
   build_area_mapping.py ── real geographic join (exact name + spatial nearest-neighbor ≤3km)
   usi_engine.py     ── fuses the two into USI + band + reason + confidence
   alerts.py + alert_state.py ── event-driven bilingual alerts, dedup/cooldown
        │
        ▼
waste_module/waste_module/ (real satellite/GIS pipeline, 366 areas)
   route/ortools_area_route_optimizer.py (real capacitated VRP)
        │
        ▼
        ├── traffic_module/frontend/ (React, :3000) — unified dashboard
        │      Overview | Traffic | Waste | USI | Alerts | Routing
        └── waste_module/waste_module/dashboard/enhanced_dashboard.py
               (Streamlit, :8501) — Risk Map, satellite indices, Event
               Intelligence, Citizen Reports, OR-Tools route sheets
```

---

## How to run it

### 1. Traffic + USI + Alerts backend (required for the React dashboard)
```bash
cd traffic_module/backend
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Do **not** run `main.py` — it's deprecated (see its own docstring); `app.py`
is the single canonical backend.

**Optional environment variables** (the system runs and is honest about
their absence without them — nothing is faked):
| Variable | Enables | Without it |
|---|---|---|
| `TOMTOM_API_KEY` | Live traffic collection (`traffic_module/data/collect_live_traffic_history.py`) | Traffic outside the ~5,556 real-model-reachable edges uses the labeled `SIMULATED_WARD_STRESS` fallback; `/api/traffic/data-status` reports `NO_LIVE_FEED` |
| `OPENWEATHER_API_KEY` (or `OWM_API_KEY`) | Live weather | Falls back to an explicitly-labeled `FALLBACK`/`ESTIMATED` weather reading |
| `ORS_API_KEY` / `OPENROUTESERVICE_API_KEY` | OpenRouteService routing | Falls back to OSRM (also real, just a different free provider) |

### 2. React unified dashboard
```bash
cd traffic_module/frontend
npm install   # first time only
npm start     # http://localhost:3000, proxies /api/* to :8000
```

**`/api/waste/routes` query parameters** (all optional — the endpoint genuinely re-solves via OR-Tools whenever any of these change, see REAL_DATA_STATUS.md):
| Param | Meaning |
|---|---|
| `num_vehicles` | Override the auto-determined vehicle count |
| `vehicle_capacity_kg` | Override the default 10,000kg per-vehicle capacity |
| `areas` | Pipe-separated (`\|`, not comma — area names contain literal commas) area names to restrict routing to |
| `force_refresh` | `true` to bypass the cache and force a fresh solve |
| `time_limit_seconds` | Real OR-Tools search budget (default 8s for interactive use; the offline CLI script uses 30s) |

Example: `GET /api/waste/routes?num_vehicles=6&vehicle_capacity_kg=12000&force_refresh=true`

### 3. Waste Streamlit dashboard (separate, optional but recommended)
```bash
cd waste_module/waste_module
streamlit run dashboard/enhanced_dashboard.py
```
Use **`enhanced_dashboard.py`** specifically — it is the only one of the
three dashboard files in that folder actually wired to the real OR-Tools
output; `app.py` and `final_dashboard.py` will not show the real routing
solve. If this machine's `waste_module/.venv` doesn't launch (a known
broken interpreter path — see audit §6), run Streamlit with a working
Python that has `waste_module/waste_module/requirements.txt` installed
(the main project's `.venv` already has most of them; add `streamlit`,
`streamlit-folium`, `geopandas`, `folium`, `plotly` if missing).

### 4. (Optional) Real-time traffic collection
Requires `TOMTOM_API_KEY`. Two modes:
```bash
cd traffic_module/data
# Continuous (default, 5-min interval, Ctrl+C to stop):
python collect_live_traffic_history.py
# Single snapshot, for an OS scheduler (cron / Windows Task Scheduler):
python collect_live_traffic_history.py --once
```
Targets 39 real Bengaluru locations (35 successfully node-matched — see
`traffic_module/data/traffic_location_mapping.csv`). Appends timestamped
rows to `live_traffic_history.csv`; `/api/traffic/data-status` reports
freshness (LIVE / STALE / MISSING) from that file directly.

### 5. Run the tests
```bash
# Backend pytest suite
cd traffic_module/backend && python -m pytest tests/ -v

# Frontend production build (also a compile/lint check)
cd traffic_module/frontend && npm run build

# USI + bilingual alerts end-to-end (CLI demo, real data)
cd integration && python demo_usi_pipeline.py

# Rebuild the real spatial area mapping (if waste/traffic location data changes)
cd integration && python build_area_mapping.py
```

---

## What's REAL, LIVE BUT LIMITED, SIMULATED, or PLANNED

| Component | Status | Detail |
|---|---|---|
| GNN traffic prediction (validated) | **REAL, LIVE BUT LIMITED** | Retrained on real TomTom/OSM data; spatial-test R²=0.62 (MAE 5.9 km/h), temporal-test R²=0.74. Covers 749 of 393,090 OSM edges (~0.19%) with ground-truth validation |
| GNN traffic prediction (extrapolated) | **REAL model, UNVALIDATED coverage** | Same trained model run on 4,807 additional real OSM edges from its own subgraph with no TomTom label — genuine inference, but no test-set accuracy claim applies. Labeled `REAL_GNN_V1_EXTRAPOLATED`, confidence capped at 0.25. Raises total real-model-reachable coverage to ~1.4% |
| OSRM/ORS routing | **REAL** | Genuine external routing API calls, real distances/polylines |
| Weather | **REAL, with labeled fallback** | OpenWeatherMap when configured; `FALLBACK` clearly tagged otherwise |
| TomTom live collector | **PLANNED (architecture built, not running)** | `--once`/loop modes both implemented, 39 real targets mapped; needs `TOMTOM_API_KEY` to actually run |
| Ward stress | **SIMULATED** | `ward_stress.py`, random-based — labeled `SIMULATED_WARD_STRESS` everywhere it's used |
| Incidents | **SIMULATED** | In-memory manual entries, API labels this `Simulated/Demo` |
| Waste satellite/GIS model | **REAL** | 366 areas, 7 real prediction dates, real NDVI/NDBI/NDWI where available |
| OR-Tools waste routing | **REAL** | Genuine capacitated VRP solve, verified: 8 trucks / 50 areas / 120.9 km |
| Citizen reports | **REAL (persisted)** | Real JSON persistence + a bounded (+5/report, capped +15) severity escalation — not simulated, not fabricated. `/api/usi/{area}` now exposes the exact breakdown: `Base waste score / Citizen report contribution / Final score` |
| 369-ward exact schema | **REAL, PARTIAL** | `/api/wards/full/schema` returns all 369 real OSM wards with live-computed `traffic_score`/`waste_score`/`USI`, checked directly against each ward's own centroid. Waste covers 366/369; traffic is 39 REAL_GNN + 34 REAL_GNN_EXTRAPOLATED + 296 SIMULATED_WARD_STRESS + 0 NO_DATA — reported as separate counts, never merged into one "has traffic" number |
| Waste routing (dynamic) | **REAL, genuinely re-solved** | `/api/waste/routes` accepts `num_vehicles`, `vehicle_capacity_kg`, `areas` (pipe-separated), `force_refresh` and actually re-runs OR-Tools when any of them change; an exact-input cache hit is labeled `CACHED_MATCHING_INPUTS` with the original solve's real timestamp, never presented as fresh |
| Ward identity | **UNIFIED** | One canonical model: real OSM `ward_id` everywhere (`location_data.py`'s `canonical_ward_id`, `ward_stress.py`'s real 369-ward registry, `/api/wards/*`, waste's `area_osm_id`). The old arbitrary numbering is kept only as `legacy_ward_id` for backward-compat documentation, never used live |
| Prediction identity | **REAL** | Every `/api/predict-enhanced` response carries a unique `prediction_id` (uuid4) and a deterministic `route_hash` — verified 20/20 unique IDs across sequential/repeated requests |
| USI fusion | **REAL, LIVE BUT LIMITED** | 24 of 25 curated traffic locations joined to a real waste area (6 exact name + 18 real spatial nearest-neighbor ≤3km); Electronic City has none within range and is honestly reported as such |
| Bilingual alerts | **REAL logic, SIMULATED delivery** | Natural (non-translated) Kannada composition, event-driven classification, real dedup/cooldown state; SMS is logged as `SIMULATED_NOT_SENT`, no provider connected. `/api/alerts/active` now also carries a real per-area `reason` string, computed live via `compute_usi()` |
| USI Search / "Use My Location" | **REAL** | USI tab search hits `/api/usi/{name}` directly; "Use My Location" reuses the real `/api/reverse-geocode` + a 5km match-radius check — never substitutes a wrong area, honestly reports "coverage unavailable" or "nearest area is Xkm away" when outside range. A matched location fetches the real alert for that area, not a fabricated one |
| Water / Power / Flood modules | **PLANNED** | Not built this phase |

---

## Known limitations (stated, not hidden)

- Real GNN coverage is narrow (0.2% of the OSM graph) — this is a data
  coverage limit, not a modeling shortcut; expanding it means running the
  TomTom collector continuously with a real API key over time.
- USI's 1 uncovered location (Electronic City) has no waste area within
  3km; forcing a match would mean fabricating a join.
- The waste module's other "Phase" modules (weather integration, social
  media, fleet maintenance, land use, model validation, uncertainty,
  scenario analysis) are real, substantial code but not wired into the
  active pipeline — see audit §5.
- ~~`/api/waste/routes` serves a pre-computed CSV~~ — **fixed**: it now
  genuinely re-solves via OR-Tools whenever the inputs change, with a
  proper input-keyed cache (see REAL_DATA_STATUS.md). One consequence: the
  Waste tab's summary now takes ~8-10s on a cache-cold load (a real solve
  costs real time) with no loading indicator yet — a disclosed minor UX gap.
- ~~The Traffic tab's "Ward Stress Monitor" grid uses a separate, unrelated
  numbering scheme~~ — **fixed**: ward identity is now unified on the real
  OSM `ward_id` everywhere (see REAL_DATA_STATUS.md's "Ward identity —
  RESOLVED this pass" section).
- All 5 tabs (Traffic/Waste/USI/Alerts/Routing) now share the same
  hero-header + control-center-grid layout as Overview — verified live in
  a real browser across all 6 tabs after a fresh page load.
- `/api/wards/full/schema`'s per-ward direct GNN centroid check takes
  ~10-12s (369 real GNN lookups) — fine for a dedicated ward-table view,
  not for frequent polling.
- Two backup folders (`traffic_module_backup/`, `traffic_module_backup -
  Copy/`) are preserved (per project rules, not deleted) and excluded from
  git via `.gitignore`. Their `realtime_data.py` copies previously held the
  same hardcoded OpenWeatherMap key that was exposed in the repo's original
  first commit — **as of 2026-09-03 this has been fully remediated**: all 5
  on-disk copies now read only from `OPENWEATHER_API_KEY`/`OWM_API_KEY`, and
  the key has been scrubbed from git history (rewritten + force-pushed; the
  old commit is no longer reachable on GitHub). See
  [FINAL_PROJECT_STATUS.md](FINAL_PROJECT_STATUS.md) for the full remediation
  record. The key itself must still be rotated on OpenWeatherMap's side —
  that is the project owner's action, not something this repo can do.

- The Traffic result card is now decluttered to the essential fields
  (distance, ETAs, speeds, congestion, confidence, GNN coverage, weather,
  incident, recommendation); the full technical breakdown (matched
  segments, coverage %, data status, model string, alternative routes) is
  still there, just moved into a collapsible "Data & Model Details"
  section rather than removed.
- A real horizontal-overflow bug on phone-width screens (the top bar
  didn't wrap) was found via live DOM measurement and fixed — verified
  `document.documentElement.scrollWidth === clientWidth` at 375px after
  the fix.

See [FINAL_PROJECT_AUDIT.md](FINAL_PROJECT_AUDIT.md) for the complete
folder-by-folder breakdown, what's duplicated/legacy, and prioritized next
steps.
