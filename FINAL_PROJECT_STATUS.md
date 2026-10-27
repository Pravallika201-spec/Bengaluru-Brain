# Bengaluru Brain — Final Project Status

**As of:** 2026-09-03 (production-readiness pass — GNN reproducibility re-verification, new USI location-based features, Traffic page decluttering, visual polish, full acceptance test matrix)
**Previous pass:** final engineering pass — 10 priorities, all treated as engineering problems, not documentation problems
**Implemented domains:** Traffic, Waste, USI (Urban Severity Index), Alerts, Routing.
**Explicitly NOT implemented:** Power, Water, Flood. Confirmed nowhere in the UI or API.

This document reports what is genuinely real, what is a labeled heuristic/simulation, and what is missing — verified by actually running the system, not by builds/tests passing alone.

---

## 1. Final status table

| Component | Status | Real Data | Coverage | Fallback | Verified |
|---|---|---|---|---|---|
| Traffic routing (distance/ETA) | LIVE | Real (OSRM) | Citywide | None needed | ✅ 8-route sanity test, ETA=distance/speed×60 exact |
| Traffic (validated GNN) | LIVE, PARTIAL | Real (749 TomTom-labeled edges) | 749/393,090 edges (~0.19%) | Extrapolated → simulated | ✅ Live inference, R²=0.62 |
| Traffic (extrapolated GNN) | LIVE | Real, unvalidated | +4,807 edges | Simulated fallback | ✅ Verified genuine forward-pass |
| Traffic (ward-level, direct centroid match — NEW) | LIVE | Real/extrapolated GNN checked against every ward's own centroid | 39 real + 34 extrapolated + 296 simulated + **0 no-data** across all 369 wards | — | ✅ Coverage counts separated explicitly, never merged |
| Waste (heuristic scoring) | LIVE | Real land-use data | 366/369 areas | NO_DATA | ✅ 20/20 areas traced exactly, zero randomness in scoring code |
| Waste (OR-Tools routing) | **LIVE, DYNAMIC (fixed this pass)** | Real solver, genuinely re-solves per input | 50 areas / configurable vehicles &amp; capacity | Honest `NO_FEASIBLE_SOLUTION` | ✅ A–G test matrix + live browser re-solve confirmed different inputs → different real outputs |
| Ward identity | **UNIFIED (fixed this pass)** | Single canonical model: real OSM ward_id everywhere | 369/369 wards, 25/25 named locations | `legacy_ward_id` kept only for backward-compat, never used live | ✅ 0 mismatches across locations/ward-stress/wards-full endpoints |
| USI fusion | LIVE | Real weighted fusion | 24/25 named + 366/369 wards | `partial_data: true` | ✅ 20/20 areas match backend math exactly |
| Ward-level exact schema | LIVE | Real per-ward traffic/waste/USI | See traffic coverage above; waste 366/369 | Honest `NO_DATA` | ✅ Verified field-by-field |
| Alerts (bilingual) | LIVE | Real, event-driven | Any area with USI data | "No active alerts" shown honestly | ✅ 6/6 controlled threshold/escalation/cooldown/dedup tests passed |
| Prediction identity (NEW) | LIVE | Real `prediction_id` (uuid4) + `route_hash` per request | Every prediction | — | ✅ 20/20 unique IDs, consistent hash per route |
| TomTom live feed | **NO_LIVE_FEED** (honest) | No `TOMTOM_API_KEY` in this environment | N/A | Collector code production-ready, verified by inspection | ✅ 4-state status (LIVE/STALE/NO_LIVE_FEED/ERROR) now exact |
| Full 5-tab UI redesign | DONE | — | — | — | ✅ All 6 tabs share control-center layout, verified live |
| Power / Water / Flood | PLANNED | N/A | N/A | N/A | ✅ Confirmed absent |

---

## 2. What changed this session

### Security (carried from the prior pass)
Exposed OpenWeatherMap key sanitized + scrubbed from git history via `git-filter-repo` + force-push; verified clean across local objects, working tree, and remote.

### Priority 1 — Waste routing made genuinely dynamic
- **Root cause found**: `/api/waste/routes` read a static pre-computed CSV, so any inputs (vehicle count, capacity, areas) were ignored — the same file was served regardless of what was asked.
- **Fix**: `ortools_area_route_optimizer.py` gained `solve_routes_for_api()` — a parameterized function that genuinely re-runs OR-Tools per call. `integration_bridge.py` gained a proper cache keyed on a hash of `(area_names, num_vehicles, vehicle_capacity_kg, data_version)` with a 5-minute TTL — an exact-input cache hit returns the *original* solve's real timestamp labeled `CACHED_MATCHING_INPUTS`; any different input triggers a fresh solve labeled `FRESH_SOLVE`.
- **Two real bugs found and fixed along the way**: (a) `area_names=[]` and `num_vehicles=0` were silently treated as "no filter" due to Python falsy-value checks (`if area_names:` instead of `if area_names is not None:`); (b) `extract_routes()` computed vehicle utilization against the *module-default* capacity even when a custom capacity was requested, silently doubling reported utilization for non-default capacities.
- **Tested A–G** (2/4/8 vehicles, different areas, different capacities, empty/invalid input, infeasible input) both as direct function calls and live HTTP requests — see TEST_REPORT.md.
- **Verified live in browser**: typed vehicle count → stale-closure bug found (the "Re-solve" button always sent the *first-render* empty values, ignoring anything typed) → fixed → re-verified: 6 vehicles correctly shows "NO FEASIBLE SOLUTION" in the UI, 8 vehicles correctly re-solves fresh with clean utilization percentages.

### Priority 2 — Ward identity unified
- **Root cause found**: `location_data.py`'s hand-entered `"ward"` field was an arbitrary, ungeographic number with real duplicate collisions (Silk Board and HSR Layout both `ward: 174`; Marathahalli and Outer Ring Road both `ward: 85`) — completely unrelated to the real 369-OSM-ward registry used elsewhere (`/api/wards/*`, waste's `area_osm_id`).
- **Fix**: computed a real `canonical_ward_id` for all 25 named locations via point-in-polygon (with nearest-centroid fallback) against the real ward boundaries. `location_data.py` now carries `canonical_ward_id`/`canonical_ward_name` (the one identity to use) alongside `legacy_ward_id` (the old number, preserved for backward-compat, never used in live computation). `ward_stress.py` was rewritten to iterate the real 369-ward registry instead of an arbitrary `range(1, 370)`.
- **Re-verified the "known-bad" collision**: Silk Board and HSR Layout do still share a canonical ward — but now because they are *genuinely* both inside the real "HSR Layout" ward boundary, not by coincidence.
- **Tested**: 0 ID mismatches across `/api/locations`, `/api/ward-stress`, and `/api/wards/full/schema` (25 locations × 369 wards checked); explicitly confirmed the "traffic-A + waste-B = USI-A" failure mode does not occur (USI's traffic/waste join is name/coordinate-based, never ID-based).
- **Bonus real fix enabled by this**: since ward identity is now consistent, `/api/wards/full/schema` could be extended to check each ward's *own* centroid against the real GNN directly (not just the 25 named locations) — traffic coverage across all 369 wards went from 6 wards having any signal to 369/369, honestly split as 39 real + 34 model-inferred-unvalidated + 296 simulated + 0 no-data.

### Priority 3 — Waste correctness deep audit
20 randomly-sampled areas traced end-to-end: raw CSV → `get_waste_severity()` → live `/api/usi/{area}` endpoint. **20/20 exact match**, zero hidden transformations, zero hardcoded values. Confirmed zero `random.*`/`np.random` calls anywhere in the live scoring path (`waste_estimator.py`, `temporal_predictor.py`); the one file that does use randomness (`scenario_analysis.py`) is dead code, never imported.

### Priority 4 — GNN coverage, honestly separated
Real monitored (39 wards) / model-inferred-unvalidated (34 wards) / simulated-fallback (296 wards) / no-data (0 wards) are now reported as **separate counts**, never collapsed into a single "X wards have real predictions" claim.

### Priority 5 — TomTom pipeline audited
Collector (`collect_live_traffic_history.py`) confirmed already production-ready: validates HTTP responses, timestamps every observation, appends to the historical dataset, supports `--once` for schedulers, refuses to run without a real key (never invents one). Freshness reporting (`data_status_service.py`) was tightened from 3 ambiguous states to the exact 4 required: `LIVE` / `STALE` / `NO_LIVE_FEED` / `ERROR`.

### Priority 6 — Prediction identity
`/api/predict-enhanced` now returns a unique `prediction_id` (uuid4) and a deterministic `route_hash` per request. Verified with 20 sequential requests (10 unique routes × 2): 20/20 unique `prediction_id`s, and `route_hash` was identical across repeats of the same route and distinct across different routes.

### Priority 7 — Traffic sanity test
All 8 explicitly-requested routes (Hebbal↔Silk Board, KR Puram↔Tin Factory, Whitefield↔MG Road, Electronic City↔Whitefield, Hebbal↔Outer Ring Road, Koramangala↔Whitefield, MG Road↔Marathahalli, Jayanagar↔Yeshwantpur) tested with full field capture. ETA = distance/speed×60 verified mathematically consistent for all 8 (within rounding).

### Priority 8 — USI correctness
20 real areas: `USI = traffic_weight × traffic_score + waste_weight × waste_score` (+ compounding bonus where both signals are elevated) verified to match the reported value exactly for all 20.

### Priority 9 — Alerts controlled testing
6 controlled tests against a synthetic test area (backed up and restored to leave production `alert_state.json` untouched): Green-band no-alert, first-alert-fires, same-band-suppressed, rapid-escalation-bypasses-cooldown, post-escalation-suppressed, small-change-still-suppressed. **6/6 passed.**

### Priority 10 — Full browser test
Fresh session across all 6 tabs; repeated + different-route predictions; waste calculation and dynamic routing (including the vehicle-count/capacity fields and the "NO FEASIBLE SOLUTION" honest-failure UI); USI; alert generation; browser refresh. Live network requests confirmed `200 OK` throughout — apparent console errors were stale buffered entries from earlier backend restarts, cross-checked and dismissed against live request logs each time.

---

## 3. Known limitations, disclosed rather than hidden

- **No live TomTom feed is configured** in this environment. Every "real-time" claim is either validated/extrapolated-but-static GNN inference, or static OSRM routing + weather/incident adjustment — never a live feed. `NO_LIVE_FEED` is reported honestly wherever this applies.
- **The GNN is not citywide.** 5,556 of ~393,090 OSM edges are real-model-reachable (~1.4%). Ward-level coverage is now far better disclosed (39 real / 34 inferred / 296 simulated / 0 no-data) but the *simulated* tier is still simulated, not a measurement.
- **The waste "model" is a heuristic**, not the trained satellite RandomForest that exists elsewhere in the codebase but is not wired into the live path. Labeled `WASTE_HEURISTIC_MODEL` everywhere.
- **`/api/waste/summary` now takes ~8-10s on a cache-cold first load** because it internally triggers a genuine OR-Tools solve (previously instant because it read a static file). This is the correct trade-off — a real dynamic solve costs real time. A loading indicator was added to the Waste tab for this wait (previously a disclosed gap; now fixed and verified live).
- **The full 369-ward direct-centroid GNN check takes ~10-12s** (`/api/wards/full/schema`) since it runs a real GNN lookup per ward. Acceptable for a dedicated ward-table view, not something to poll frequently.

See [REAL_DATA_STATUS.md](REAL_DATA_STATUS.md), [MODEL_CARD.md](MODEL_CARD.md), and [TEST_REPORT.md](TEST_REPORT.md) for full detail.

---

## 4. This session's pass — what changed and was verified (§23–27 of TEST_REPORT.md)

- **GNN training reproducibility re-verified**, not just checked for file existence: the real seeded training script was re-run end-to-end and its metrics matched the previously-recorded values byte-for-byte across train/spatial-val/spatial-test/temporal-test. The re-saved checkpoint was confirmed to still load and produce correct real inference through the exact production code path.
- **New USI "Search" and "Use My Location" features**, built and live-tested for the first time this session. Both reuse existing backend endpoints only (`/api/usi/{name}`, `/api/reverse-geocode`, `/api/alerts/{area}`) — no new severity thresholds or wording invented. All three real code paths verified live: valid search, invalid search (honest "coverage unavailable"), geolocation permission-denied, geolocation success with a real area match, and geolocation success with an honest "no coverage — nearest area is 833.9km away" refusal to substitute a wrong area.
- **Alerts gained a real `reason` field** on `/api/alerts/active` (previously missing), computed live via the existing `compute_usi()` — not a new computation path. SMS/alert-preview language tightened to make clear no real delivery occurs (`"SMS Preview — delivery not configured"`).
- **Traffic result card decluttered** to the exact requested field set, with all technical/internal detail (matched segments, coverage %, traffic_data_status, model string, alternative-routes table) preserved in a collapsible "Data & Model Details" section rather than removed.
- **Visual polish**: glass/blur panel backgrounds, a third ambient gradient, and severity-color glow on status pills — verified not to introduce new overflow across 1366×768, 1920×1080, and 375px mobile.
- **One real bug found and fixed this session**: the top bar did not wrap on phone-width viewports, causing genuine horizontal page overflow (`scrollWidth` 437px vs. `clientWidth` 375px, confirmed via direct DOM measurement, not a screenshot artifact). Fixed with a `max-width: 560px` media query; re-verified `scrollWidth === clientWidth` after the fix.
- **Full acceptance sweep this session**: 5 sequential Traffic predictions (0 staleness, ETA math verified), an invalid-route case, Waste loaded twice with identical output, Routing's cached-vs-fresh distinction re-confirmed, zero console errors and zero failed network requests across the entire session, `pytest` 3/3 passed, and `npm run build` compiled successfully. Full detail in TEST_REPORT.md §23–27.
- **New Route Map added to the Traffic page** (`RouteMap.jsx`, between the prediction card and the existing citywide map) — real OSRM route geometry, green/red source/destination markers, line colored by the route's real overall traffic band. Deliberately does *not* fabricate per-segment coloring: the backend's matched-segment data has no position-along-route information, so inventing which part of the line is which color would misrepresent what's actually known — disclosed via an inline caption instead.
- **Traffic prediction card redesigned** to a simplified 4-tile layout (Distance / Predicted Time / Traffic Condition / Confidence with plain-language captions) per a user-provided mockup. Every field the old 8-tile layout showed (Current ETA, Current Speed, Predicted Speed, Congestion Score, GNN Coverage) is still present — moved into "Data & Model Details", not removed.
- **Bug fixed: "Predicted Time (ETA)" showed "— min"** on some predictions despite valid distance/condition/confidence. Root cause: `/api/predict-enhanced`'s exception fallback returned travel-time fields under different key names than the ones `ResultCard.jsx` reads, and never set `predicted_eta_min` at all. Fixed by aliasing the fallback's own real, already-computed values onto the expected keys — no new calculation. Verified against 3 live routes, each showing a correct, distinct ETA. Full detail in TEST_REPORT.md §29.
