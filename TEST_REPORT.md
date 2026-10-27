# Test Report

All tests below were actually executed against the running backend (and, where noted, a real browser session) during this engineering pass — not inferred from code review or "tests pass" alone.

## 1. Security remediation verification

| Test | Method | Result |
|---|---|---|
| Locate exposed key everywhere | `grep` across full working tree + full git history (all blobs) | Found in 1 tracked file + 4 gitignored backup copies + stale `.pyc` caches |
| Sanitize all copies | Edited all 5 source copies to read from env vars only | Confirmed via re-scan: 0 occurrences |
| History scrub | `git-filter-repo --replace-text` on an isolated mirror clone, force-pushed | Confirmed via `git ls-remote`: old commit `8928a17` unreachable, new root `a495d9e` live |
| Local object purge | `git prune` + `repack`, after finding and fixing one residual copy in the git index | Confirmed via `git cat-file -e`: object physically gone |
| Working tree safety | Checked modified-file count before/after every git operation | Stayed at 148 throughout — untouched |

## 2. Second-prediction / race-condition bug

| Test | Method | Result |
|---|---|---|
| Backend state isolation | 20 sequential HTTP requests (mixed unique + repeated routes) against the live process | 100% consistent, 0 cross-contamination |
| Frontend race condition | Rapid-fire double-submit via browser automation | Confirmed the button correctly disables during a request (no true overlapping requests possible via the UI) |
| Sequential real-usage pattern | 4 sequential real-browser predictions on different routes (Hebbal→Silk Board, Koramangala→Whitefield, MG Road→Marathahalli, Jayanagar→Yeshwantpur) | All 4 updated correctly; values matched backend exactly each time |
| Browser refresh | Refreshed the page mid-session | App reset cleanly to Overview tab, no crash, no stale state |

## 3. Response schema & math consistency

17-request test matrix: 12 unique real Bengaluru routes + 5 repeats of the first 5.

| Check | Result |
|---|---|
| Source/destination echo matches request | 17/17 (0 mismatches) |
| Repeated routes return identical results | 5/5 byte-identical (`distance_km`, `predicted_eta_min`, `congestion_score`, `traffic_source`) |
| `predicted_speed_kmh` matches `distance_km / (predicted_eta_min/60)` | 12/12 within rounding |
| All new explicit schema fields present (`free_flow_eta_min`, `congestion_score`, `model_version`, `route_coverage`, etc.) | Confirmed present and correctly typed on every response |
| `congestion_score` scale consistency (backend 0-100 vs. frontend gauge) | Found and fixed a scale mismatch in `ResultCard.jsx` (was still treating it as 0-1) |

Full route list tested: Hebbal↔Silk Board, Koramangala↔Whitefield, Indiranagar↔Electronic City, MG Road↔Marathahalli, Jayanagar↔Yeshwantpur, BTM Layout↔HSR Layout, Malleswaram↔Rajajinagar, Banashankari↔JP Nagar, Yelahanka↔Hebbal, Manyata Tech Park↔Electronic City, Sarjapur Road↔Tumkur Road, Outer Ring Road↔Marathahalli.

## 4. GNN coverage expansion

| Test | Method | Result |
|---|---|---|
| Validated-tier inference still correct | All 12 route-matrix routes | 100% returned `REAL_GNN` (validated), consistent with pre-expansion behavior |
| New extrapolated tier fires correctly | Direct test targeting a known extrapolated edge's own coordinates | `covered: True`, `source: REAL_GNN_V1_EXTRAPOLATED`, varying real speed predictions (16.4–43.3 km/h across different real edges) — confirms genuine model inference, not a stub |
| Extrapolated tier never conflated with validated | Checked `traffic_source`, `model_version`, `model_confidence` fields across both tiers | Distinct values confirmed (`REAL_GNN` vs `REAL_GNN_EXTRAPOLATED`; confidence 0.62 vs 0.25 capped) |
| No named-location route accidentally under-reports | All 12 real named-location routes | Still correctly hit the validated tier (as expected — curated locations cluster near TomTom-monitored corridors) |

## 5. Waste transparency & citizen reports

| Test | Method | Result |
|---|---|---|
| Base/bonus/final breakdown format | Queried `/api/usi/Agaram` before and after submitting real reports | Exact format confirmed: `"Base waste score: 92.16 / Citizen report contribution: +15.0 / Final score: 100.0"` |
| Bounded influence | Submitted 3 real reports via the actual `citizen_reports_store.add_report()` function (same path the dashboard uses) | Bonus capped correctly at +15 (3 × 5 = 15, at the cap) |
| Score capped at 100 | Same test, base score 92.16 + 15 bonus | Correctly capped at 100.0, not 107.16 |
| Cleanup | Reset `citizen_reports.json` to `[]` after testing | Confirmed USI reverted to baseline (92.16 / 92.2) |
| Reproducibility | Called `/api/usi/Agaram` twice with no state change | Byte-identical (92.2, Red, 92.16) both times |

## 6. OR-Tools routing

Ran the actual optimizer function (not just the cached API) with the venv's real `ortools` install:

| Scenario | Vehicles | Result |
|---|---|---|
| Auto-determined count (real data: 50 areas, 69,344.83 kg total) | 8 | Solved correctly |
| Deliberately insufficient | 1 | Correctly raised `RuntimeError` — no fake success |
| Excess vehicles | 11 | Solved correctly |
| Oversized single-area demand (15,000 kg > 10,000 kg capacity) | auto | Correctly warned, then correctly raised `RuntimeError` |

**Caveat found and documented**: `/api/waste/routes` serves a pre-computed CSV, not a live per-request solve. The solver itself is genuinely real and correctly handles infeasibility; the API layer just doesn't re-invoke it per request.

## 7. USI & Alerts

| Test | Result |
|---|---|
| USI reproducibility (same area, repeated calls) | Byte-identical |
| Real alert generation (bilingual) | Confirmed real English + Kannada text generated per area, varying by actual band/reason |
| Real dedup/cooldown | Second call to the same area within the cooldown window correctly returned `SUPPRESSED_DEDUP` |
| Honest "no active alerts" | `/api/alerts/active` returned exactly 1 genuine standing alert (Banashankari, Yellow) — not padded to look busier |
| Green band correctly excluded from alerting | Confirmed via `alerts.py::ALERT_BANDS = {"Yellow", "Orange", "Red"}` — no areas observed at Green in this dataset, but the exclusion logic is explicit, not accidental |

## 8. Ward-level exact schema

| Test | Result |
|---|---|
| All 369 wards returned, exact field names | Confirmed (`ward_id, ward_name, latitude, longitude, traffic_status, traffic_score, traffic_source, traffic_data_age, waste_score, waste_source, USI, coverage_status`) |
| Honest NO_DATA where no signal exists | 363/369 wards correctly show `traffic_status: NO_DATA`, `traffic_score: null` |
| Waste coverage | 366/369 wards have a real `waste_score` |
| Response time for full 369-ward computation | ~2.05s — acceptable for a dedicated ward-table view |

## 10. UI redesign verification (Phase 13)

| Test | Method | Result |
|---|---|---|
| All 5 tabs share the control-center layout | Rebuilt frontend, restarted dev server, navigated Traffic→Waste→USI→Alerts→Routing in a real browser after a fresh page load | Confirmed via `get_page_text` on each tab: hero header + correct data rendering on all 5 |
| Waste transparency breakdown renders in UI | Checked USI tab for a spatially-matched area | Confirmed: `"Base waste score: 56.61 / Citizen report contribution: +0.0 / Final score: 56.61"` rendered correctly |
| Citywide "Live Active Alerts" panel (new, moved from Overview-only) | Checked Alerts tab | Confirmed: showed 3 genuine standing alerts (Agaram Red, Whitefield Orange, Banashankari Yellow) from real accumulated `alert_state.json`, not fabricated |
| No console errors from the current page load | `read_console_messages` after a fresh navigate, cross-checked against `read_network_requests` | Initial read showed stale buffered errors from an earlier backend restart; live network requests all showed `200 OK` — confirmed not a current issue |
| Production build still compiles | `CI=true npx react-scripts build` after all UI changes | `Compiled successfully`, exit code 0 |

---

# Final Engineering Pass — 10 Priorities

Continuation of testing, treating the previously-reported limitations as engineering problems to fix, not just document.

## 12. Priority 1 — Dynamic waste routing (A–G test matrix)

| Test | Vehicles | Capacity | Areas | Result |
|---|---|---|---|---|
| A | 2 | default | all 50 | `NO_FEASIBLE_SOLUTION` (correctly infeasible: 69,345kg / 10,000kg needs 7+) |
| B | 4 | default | all 50 | `NO_FEASIBLE_SOLUTION` (correct) |
| C | 8 | default | all 50 | Solved, 121.9km |
| D | auto | default | 5 selected (real, pipe-separated area names) | Solved independently: 1 vehicle, 3.8km — proves inputs genuinely change output |
| E1 | 8 | 10,000kg | all 50 | Solved, 121.9km |
| E2 | 8 | 20,000kg | all 50 | Solved, 91.7km, correct utilization % (bug found & fixed — see below) |
| F1 | — | — | empty list `[]` | `INVALID_INPUT` (found and fixed a falsy-value bug: `[]` was silently treated as "no filter") |
| F2 | — | — | nonexistent area name | `INVALID_INPUT`, names the unmatched area |
| F3 | 0 | — | all | `INVALID_INPUT` (found and fixed: `0` was silently treated as "auto") |
| F4 | — | 0kg | all | `INVALID_INPUT` |
| G | 8 | 100kg | all | `NO_FEASIBLE_SOLUTION` (correct — no vehicle could ever carry any area) |

**Bugs found and fixed**: (1) `area_names=[]`/`num_vehicles=0`/`vehicle_capacity_kg=0` were silently accepted as "not provided" due to Python falsy-value checks — now explicitly validated. (2) `extract_routes()` computed utilization against the module-default capacity even when a custom capacity was solved for, silently doubling reported utilization for non-default capacities — fixed by threading the actual capacity through.

**Cache verification**: identical repeated request → `route_source: CACHED_MATCHING_INPUTS` with the *original* solve's timestamp; `force_refresh=true` or any changed input → `route_source: FRESH_SOLVE` with a new timestamp. Verified via live HTTP calls and live in the browser (UI badge showed `CACHED (158.8s ago, identical inputs)` then `FRESH SOLVE` after clicking re-solve).

**Live browser bug found and fixed**: the "Re-solve" button's vehicle-count/capacity fields used a `useCallback` with an empty dependency array, so the button always sent the values from the component's *first render* (empty strings) no matter what was typed — confirmed via the actual network request showing no `num_vehicles` param despite typing one. Fixed by removing the stale memoization; re-verified live: typing `6` → request correctly included `num_vehicles=6&force_refresh=true` → UI correctly showed "NO FEASIBLE SOLUTION"; typing `8` → correctly re-solved fresh.

## 13. Priority 2 — Ward identity unification

| Test | Result |
|---|---|
| Locate every ward/area identifier | Found two systems: real OSM `ward_id` (`ward_registry.json`, waste's `area_osm_id`) vs. arbitrary legacy ints (`location_data.py`'s old `"ward"` field, `ward_stress.py`'s `range(1,370)`) |
| Known-bad collision re-examined | Silk Board & HSR Layout (`legacy_ward_id=174` for both, by coincidence) → real point-in-polygon computation confirms they genuinely ARE both inside the real "HSR Layout" ward (`canonical_ward_id=19883285`) — same for Marathahalli/Outer Ring Road (`19884550`) |
| Cross-endpoint consistency | 0 mismatches: all 25 named locations' `canonical_ward_id` present in both `/api/ward-stress` (369 wards) and `/api/wards/full/schema` (369 wards) |
| Ward-name consistency | 0 name conflicts across all 369 wards shared between endpoints |
| Cross-contamination check (traffic-A + waste-B = USI-A) | Confirmed does NOT occur — traffic/waste scores for Marathahalli vs. Outer Ring Road (sharing a real ward) differ appropriately: waste is legitimately shared (spatial nearest-neighbor to the same real polygon, honestly labeled `spatial_nearest`), traffic varies independently per area's own real coordinates |

## 14. Priority 3 — Waste correctness (20-area trace)

Raw CSV → `get_waste_severity()` → live `/api/usi/{area}`: **20/20 areas exact match** (e.g. Thindlu: raw=90.46, backend_base=90.46, live API=90.46). Zero `random.*` calls in the live scoring path (`waste_estimator.py`, `temporal_predictor.py`); the only file using randomness (`scenario_analysis.py`) is confirmed dead code (never imported).

## 15. Priority 4 — GNN coverage, honestly separated

`/api/wards/full/schema` now checks every ward's own centroid directly against the real GNN (not just the 25 named locations): **39 REAL_GNN + 34 REAL_GNN_EXTRAPOLATED + 296 SIMULATED_WARD_STRESS + 0 NO_DATA** = 369. Reported as four separate counts in `traffic_coverage_summary`, never merged.

## 16. Priority 5 — TomTom pipeline audit

Collector code-reviewed line-by-line: validates HTTP status, timestamps every row, appends to `live_traffic_history.csv`, supports `--once` for a scheduler, exits cleanly with instructions if `TOMTOM_API_KEY` is unset (never invents one). Freshness states tightened from 3 (`LIVE`/`STALE`/`MISSING`) to the exact 4 required (`LIVE`/`STALE`/`NO_LIVE_FEED`/`ERROR`), with `ERROR` now distinct from `NO_LIVE_FEED` (corrupt data present vs. nothing collected). Not live-tested end-to-end since no real key exists in this environment — disclosed, not faked.

## 17. Priority 6 — Prediction identity

20 sequential `/api/predict-enhanced` calls (10 unique routes × 2, including exact repeats): **20/20 unique `prediction_id`s** (uuid4), and `route_hash` was identical for every repeat of the same route and distinct for every different route.

## 18. Priority 7 — Traffic sanity test (exact 8 routes)

| Route | dist_km | free-flow ETA | current speed | current ETA | pred speed | pred ETA | status | congestion | source |
|---|---|---|---|---|---|---|---|---|---|
| Hebbal → Silk Board | 20.87 | 26.7 | 46.9 | 26.7 | 32.1 | 39.0 | MODERATE | 31.6% | REAL_GNN |
| KR Puram → Tin Factory | 3.67 | 3.6 | 60.6 | 3.6 | 35.8 | 6.2 | HIGH | 40.9% | REAL_GNN |
| Whitefield → MG Road | 18.11 | 21.4 | 50.7 | 21.4 | 23.1 | 47.0 | HIGH | 54.5% | REAL_GNN |
| Electronic City → Whitefield | 21.96 | 30.2 | 43.6 | 30.2 | 26.0 | 50.7 | HIGH | 40.4% | REAL_GNN |
| Hebbal → Outer Ring Road | 23.33 | 28.6 | 49.0 | 28.6 | 33.3 | 42.0 | MODERATE | 32.0% | REAL_GNN |
| Koramangala → Whitefield | 17.35 | 19.0 | 54.8 | 19.0 | 24.8 | 42.0 | HIGH | 54.7% | REAL_GNN |
| MG Road → Marathahalli | 13.34 | 17.9 | 44.6 | 17.9 | 23.4 | 34.2 | HIGH | 47.6% | REAL_GNN |
| Jayanagar → Yeshwantpur | 12.91 | 15.0 | 51.7 | 15.0 | 21.6 | 35.9 | SEVERE | 58.2% | REAL_GNN |

Math check (`ETA = distance/speed × 60`, tolerance 0.15 min for rounding): **0 issues across all 8 routes.**

## 19. Priority 8 — USI correctness (20 areas)

`USI = traffic_weight × traffic_score + waste_weight × waste_score` (+10 compounding bonus where both ≥ the HIGH threshold, capped at 100): **20/20 areas matched the reported USI exactly** (e.g. Koramangala: 65.0×0.5 + 60.9×0.5 = 62.95 → +10 compounding bonus → 73.0, exactly matching the reported value).

## 20. Priority 9 — Alerts controlled testing

Using a synthetic test area (production `alert_state.json` backed up before, confirmed byte-identical after):

| Test | Expected | Result |
|---|---|---|
| Green band | Never alerts | ✅ `None` returned |
| First alert at a new band | Fires | ✅ `SIMULATED_NOT_SENT` |
| Immediate repeat, same band | Suppressed | ✅ `SUPPRESSED_DEDUP` |
| Rapid escalation (+20 USI, band change) | Bypasses cooldown, marked `ESCALATION` | ✅ Fired, `alert_type: ESCALATION` |
| Immediate repeat after escalation | Suppressed again | ✅ `SUPPRESSED_DEDUP` |
| Small change (+2, same band) | Still suppressed (not an escalation) | ✅ `SUPPRESSED_DEDUP` |

**6/6 passed.** Production `alert_state.json` confirmed unchanged (byte-diff against pre-test backup).

## 21. Priority 10 — Full browser test (post-fix)

Fresh dev server, full tab sweep after all Priority 1–9 backend changes: Overview → Traffic (predict Hebbal→Silk Board, repeat identical, then Koramangala→Whitefield — correct update each time, no contamination) → Waste (confirmed ~8-10s load from the now-real OR-Tools solve, no loading indicator — disclosed as a minor UX gap) → USI (confirmed new `REAL (GNN, validated)` label) → Alerts (confirmed live active-alerts list and bilingual dedup) → Routing (confirmed dynamic re-solve UI, found and fixed the stale-closure bug live, confirmed `NO FEASIBLE SOLUTION` and `FRESH SOLVE` render correctly) → browser refresh (clean reset to Overview, live network requests all `200 OK`, apparent console errors cross-checked and confirmed stale/buffered from earlier restarts, not current).

## 22. What was NOT (re)tested this pass

- Full automated pytest suite (not re-run this session; the manual/live tests above are more thorough for the specific bugs being investigated but don't replace CI-style regression coverage).
- Load/performance testing under concurrent multi-user traffic.
- Mobile/responsive browser testing.
- Live TomTom collector end-to-end (no real API key available in this environment — code-reviewed and confirmed production-ready instead).

---

# Production-Readiness Pass — GNN reproducibility, USI location features, decluttering, visual polish

## 23. GNN training pipeline — genuine reproducibility verification

Re-ran the real seeded training script (`traffic_module/models/train_gnn_real_v1.py`, `SEED=42`) end-to-end rather than just checking the checkpoint file exists.

| Metric | Previously recorded (`traffic_model_real_v1_metrics.json`) | This session's fresh re-run | Match |
|---|---|---|---|
| train MAE/RMSE/R² (n=1229) | 3.9116 / 5.9681 / 0.6950 | 3.9116 / 5.9681 / 0.6950 | ✅ byte-identical |
| spatial val (n=107) | 6.2367 / 8.3979 / 0.6367 | 6.2367 / 8.3979 / 0.6367 | ✅ byte-identical |
| spatial test (n=125) | 5.9246 / 7.6847 / 0.6224 | 5.9246 / 7.6847 / 0.6224 | ✅ byte-identical |
| temporal test (n=185) | 3.0188 / 4.6394 / 0.7407 | 3.0188 / 4.6394 / 0.7407 | ✅ byte-identical |

Checkpoint was backed up before re-training as a safety measure. Feature-engineering and split code (lines 80–179) re-read to confirm no target leakage. After re-training, confirmed the checkpoint still loads through the exact production code path (`real_gnn_service.py::_get_context()`): 749 labeled + 4,807 extrapolated edges, real non-negative inference (30.6 km/h, Hebbal–Silk Board corridor) — not just "file exists."

## 24. New features — USI Search & "Use My Location" (live browser, first-time test)

| Test | Method | Result |
|---|---|---|
| Search valid area | Typed "Whitefield", clicked Search | Real fused USI (50.9, Yellow) rendered, correct 50/50 weighting breakdown, honest SIMULATED/HEURISTIC sub-labels |
| Search invalid area | Typed "Nonexistentplace999" | Honest `USI coverage unavailable for "..."` message, no fabricated result, previous result preserved rather than blanked |
| Use My Location — permission denied | Real browser geolocation (no permission granted in this environment) | Correct `Location permission denied…` message via the real `GEO_ERROR_MESSAGES` map |
| Use My Location — success | Mocked coordinates near Whitefield via `navigator.geolocation` override | Reverse-geocoded, matched to Whitefield (0.089km away) via the real `/api/reverse-geocode` + 5km radius check, fetched `/api/alerts/Whitefield`, rendered a real "Citizen Alert For Your Location" block labeled **"PREVIEW ONLY — NOT REAL SMS DELIVERY"** |
| Use My Location — no coverage | Mocked coordinates in Mumbai (far away) | Correctly refused to substitute a wrong area: `"nearest covered area (Yelahanka) is 833.897km away, beyond the 5km match radius"` — real haversine distance, not fabricated |

This also had a real, verifiable side effect: the USI-triggered alert for Whitefield appeared moments later on the Alerts tab's Live Active Alerts list with a matching timestamp, confirming the feature is wired to the real alert-state backend, not a client-side mock.

## 25. Alerts — new `reason` field & relabeling

| Test | Result |
|---|---|
| `/api/alerts/active` reason field | Backend now computes it live via `compute_usi()` per area (previously missing from `alert_state.json`); confirmed real, varied per-area text in the browser, e.g. `"Medium traffic congestion and medium waste overflow risk and waste data joined from the nearest real area (madiwala, 0.718km away)"` |
| SMS honesty relabel | `"Simulated SMS"` → `"SMS Preview — delivery not configured"`; `"Selected Area Preview"` → `"Citizen Alert Preview"` — confirmed rendered correctly, no remaining "simulated SMS" language implying real delivery |
| Cooldown/dedup still correct after changes | The Whitefield alert generated in test 24 correctly showed `Suppressed (cooldown): deduplicated: same band within cooldown window` on a second trigger within the window |

## 26. Traffic page decluttering (ResultCard rewrite)

Main view now shows exactly the requested field set (Distance, Current/Predicted ETA, Current/Predicted Speed, Congestion, Confidence, GNN Coverage, Weather, Incident, Recommendation); everything else (Free-Flow ETA, Matched Segments, Route Coverage %, Traffic Data Status, Data Age, Prediction Time, raw Model string, Matched Real Segments table, Alternative Routes table) moved into a collapsible "🔧 Data & Model Details" `<details>` section — verified present and functional in the browser, not just removed.

## 27. Full acceptance test matrix (this session, live browser + live backend)

| Area | Test | Result |
|---|---|---|
| Traffic | 5 sequential predictions, distinct routes (2 presets + 2 presets + 1 free-text) | All 5 fully updated (distance/speed/ETA/congestion/status/map markers), 0 staleness, 0 cross-contamination |
| Traffic | ETA math (`distance/speed × 60`) | Checked all 5: max deviation < 0.2 min (rounding only) |
| Traffic | Invalid/uncoverable route | Honest error, no fake result, stale UI state correctly cleared |
| USI | Search + Use My Location (3 paths) | See §24 |
| Alerts | Reason field + relabeling | See §25 |
| Waste | Loaded twice (tab switch + full page reload) | Identical values both times (366 areas, 3,639t, same top-10 list) — confirms non-random, deterministic heuristic |
| Routing | Cached vs. fresh distinction | First load: `CACHED (295.4s ago)`; after Re-Solve: `FRESH SOLVE`, took a real 8.04s, same optimal 120.9km/8-vehicle result (deterministic solver, unchanged inputs) |
| Responsive | 1366×768 | All 6 tabs checked — clean, no overflow/overlap |
| Responsive | 1920×1080 | Checked — content stays within a max-width container, no wasted-space regression |
| Responsive | 375px (mobile) | **Found a real bug**: `.cc-topbar` (brand + time/weather/LIVE chips) didn't wrap, causing `document.documentElement.scrollWidth` (437px) to exceed `clientWidth` (375px) — a genuine horizontal-overflow bug, confirmed via DOM measurement, not just a screenshot artifact. **Fixed** by adding a `@media (max-width: 560px)` rule letting the topbar wrap and shrinking chip padding. Re-verified: `scrollWidth === clientWidth` (375 = 375) after the fix, and the Traffic ResultCard's metric grid renders as a clean 2-column layout with no overlap on mobile. |
| Console | Errors across the entire session (all tabs, all tests above) | **Zero** — `read_console_messages(onlyErrors=true)` empty throughout |
| Network | All requests across the entire session | **Zero failures** — every request (including the CSS hot-reload after the mobile fix) returned `200 OK` |
| Backend | `pytest tests/ -v` | 3/3 passed (`test_enhanced_prediction.py`) |
| Frontend | `npm run build` | `Compiled successfully`, 215.92 kB main JS / 15.31 kB CSS gzipped |

## 28. What was NOT (re)tested this session

- Full automated pytest suite beyond the 3 existing tests in `test_enhanced_prediction.py` (no additional test files were added this session).
- Load/performance/concurrency testing.
- Live TomTom collector end-to-end (still no `TOMTOM_API_KEY` in this environment — remains honestly disclosed as `NO_LIVE_FEED`, not worked around).
- The Streamlit waste dashboard (`enhanced_dashboard.py`) — out of scope, requires a separate process.

---

# Bug Fix — Traffic page "Predicted Time (ETA)" showing "— min"

## 29. Root cause and fix

`/api/predict-enhanced` wraps its main prediction logic in a single `try/except`. When anything inside that path throws, the `except` block falls back to the older `predict_traffic()` helper (also used by the deprecated `/predict-route` endpoint). That helper computes a real, correct distance/traffic/confidence — which is why those three fields displayed correctly — but returns its travel-time fields under different names (`predicted_travel_time`, `current_travel_time`, `base_travel_time`, no `_min` suffix) and never sets `predicted_eta_min`/`current_eta_min` at all. `ResultCard.jsx` only reads the `_eta_min` names, so it rendered "— min" whenever this fallback fired.

**Confirmed trigger, reproduced directly**: calling `predict_traffic('Silk Board', 'Marathahalli')` in isolation hits an internal (separately pre-existing, unrelated) `traffic_predictor_v2` checkpoint state_dict mismatch — `models/traffic_model_v2.pth` doesn't match the `TrafficGNNv2` architecture `predict_route_v2()` expects. That inner failure is already caught inside `predict_traffic()` itself (it safely falls back to an ORS-based heuristic and returns `traffic: 'CRITICAL'` for this route) — but confirms the fallback path is real and reachable, matching the user-reported CRITICAL-band screenshot exactly.

**Fix** ([app.py](traffic_module/backend/app.py), except-block only, ~8 lines): alias the fallback's own already-computed values onto the field names the UI reads —
```python
result.setdefault("predicted_eta_min", result.get("predicted_travel_time"))
result.setdefault("current_eta_min", result.get("current_travel_time"))
result.setdefault("free_flow_eta_min", result.get("base_travel_time"))
```
No new calculation, no fabricated number — the same real heuristic result, exposed under the correct key.

**Verified**:
| Test | Result |
|---|---|
| Isolated fallback test (`predict_traffic` + fix applied manually) | `predicted_eta_min: 38` (was absent before the fix) |
| Live route 1: Silk Board → Marathahalli | 27 min, MODERATE |
| Live route 2: Hebbal → Silk Board | 37 min, MODERATE |
| Live route 3: Electronic City → Whitefield | 47 min, HIGH |
| Route Map after fix | Still renders correctly (2 markers, tiles load) |
| Console errors | 0 current (stale "Proxy error" entries were from a backend-restart window, confirmed via live network log) |
| pytest | 3/3 passed |
| `npm run build` | Compiled successfully |

**Explicitly not touched**: the `traffic_predictor_v2` / `traffic_model_v2.pth` checkpoint mismatch that triggers this fallback in the first place. That's a separate, legacy model (superseded by `real_gnn_service.py` / `traffic_model_real_v1.pth`, the model this project's GNN work is actually built on) — the user's instructions for this fix explicitly excluded touching the GNN model, so it was left as-is; it already fails safely without crashing anything.

---

# 2-Hour Forecasting + Real-Time Incident Detection

## 30. Data inspection, CSV repair, and the honest forecast-readiness verdict

Full detail in `traffic_module/backend/forecasting/README.md`. Summary:

- `bengaluru_traffic_history.csv` (24h real ward-rotation collection, Sep 8–9): 946 raw rows → 930 valid, 3 repaired (ERROR rows with a stray exception-text field beyond the header — nulled unmeasured fields, not invented), 13 rejected (unexplained `OK`-row field-count shift, no safe realignment possible — discarded, not guessed).
- Built real T→T+120min pairing with a 15-minute tolerance window, matching only genuine future observations of the same OSM edge (never a random future row, never future information in the input features — unit-tested).
- **Result: 0 valid pairs.** Median per-edge revisit interval is ~353.6 minutes — the 369-ward/batch-8 rotation design (from an earlier session's citywide-coverage task) revisits each edge roughly once per ~5.9h rotation, not every ~2h. No model was trained; `/api/traffic/forecast-2h` honestly reports `UNAVAILABLE` with these real numbers rather than fabricating a forecast or reusing `future_mins = predicted_duration_mins`.

## 31. Real-time anomaly detection

New `traffic_incident_service.py`: NORMAL / TRAFFIC_ANOMALY / POSSIBLE_INCIDENT / PROVIDER_CONFIRMED_INCIDENT hierarchy, configurable thresholds, tested against both synthetic fixtures (11 unit tests) and the real 930-row dataset live via `/api/traffic/incidents`: 133/369 segments flagged (mostly delay-percentage anomalies and one segment with a real TomTom `road_closure=True` flag verified present in the raw data). `PROVIDER_CONFIRMED_INCIDENT` is coded and tested but never reachable in production — this project's TomTom integration has no incidents-feed endpoint, disclosed in every API response (`provider_incident_feed_configured: false`).

## 32. Verification

| Test | Result |
|---|---|
| Existing `pytest tests/` (3 tests) | Still 3/3 passed, unchanged |
| New `test_traffic_forecasting_and_incidents.py` (18 tests) | 18/18 passed |
| `/api/traffic/forecast-2h` | 200, honest UNAVAILABLE + real data-quality numbers |
| `/api/traffic/incidents` | 200, 133 real anomalies, correct evidence/segment IDs |
| `/api/traffic/live-status` | 200, correctly reports `tomtom_configured: false`, real last-observation age |
| Existing endpoints (`predict-enhanced`, `usi/areas`, `alerts/active`, `waste/summary`, `incident/list`, `ward-stress`, `weather`, `traffic/data-status`) | All still 200 OK, unaffected |
| `npm run build` | Compiled successfully |

**Not verified**: live browser click-through of the new UI panels — the frontend dev proxy targets port 8000, which was occupied by an unrelated, already-running application not part of this project; killing it was out of scope. Verified instead via direct API calls (confirmed correct JSON shape matching what the new `TrafficForecastAndIncidents.jsx` component renders) and a successful production build.

**Not implemented this pass** (disclosed, not silently skipped): map-overlay incident markers (Part G) and routing-system incident integration (Part H) — the existing map and OR-Tools routing are completely untouched, not partially/riskily modified.

---

# Route-Level 2-Hour Forecast — Hybrid Extrapolation (given no time to collect more data)

## 33. Method chosen, and why

With zero T+120 supervised pairs available (§30) and no time to collect
another multi-day dataset, the strongest legitimate approach found by
inspecting the existing project was a **transparent hybrid
extrapolation**: real current route state (existing `real_gnn_service.py`,
completely unmodified — spatial component) × a real historical
hour-of-day speed_ratio ratio derived from the actual 930 valid TomTom
observations (temporal component). Explicitly rejected: the app.py-only
heuristic tables (`get_it_park_impact`, `get_event_status`,
`get_bengaluru_speed`'s `SPEED_TABLE`, `get_congestion_multiplier`) —
inspected and confirmed to be hand-picked constants (e.g. a flat `1.25`
evening-peak multiplier) never used by the real `/api/predict-enhanced`
path and not derived from any measurement, so including them would have
weakened rather than strengthened the forecast's defensibility.

New: `traffic_forecast_service.py::get_route_forecast_2h()`,
`forecasting/historical_pattern.py::get_temporal_ratio()`.

## 34. Live verification

| Test | Result |
|---|---|
| `GET /api/traffic/forecast-2h` (no route) | 200, honest "source and destination required" — no default route guessed |
| `GET /api/traffic/forecast-2h?source=Hebbal&destination=Silk+Board` | 200, `method: "historical_temporal_extrapolation"`, `data_quality: "HIGH DATA SUPPORT"` (REAL_GNN current state, n=48 and n=96 real samples at the two relevant hours), basis string names the exact real numbers used |
| Bug found & fixed live | `routing_service.get_route()` raises (not returns falsy) for an ungeocodable place — was crashing the forecast call uncaught; now caught, returns honest `available: false` |
| New tests (7 more, on top of the 21 already in §32) | All pass — 120-minute horizon math, method-label discipline (never "supervised"/"trained model"), invalid-route handling, historical-pattern availability for both a well-sampled and an empty hour |
| Full suite | **28/28 passed** |
| Existing endpoints re-verified after the rewire | `predict-enhanced`, `usi/areas`, `alerts/active`, `waste/summary`, `waste/routes`, `traffic/incidents`, `traffic/live-status`, `ward-stress` — all still 200 |
| `npm run build` | Compiled successfully |

## 35. What can be said in a project review, verbatim

> "The Traffic module produces a 2-hour-ahead forecast for a selected
> route by combining the project's real, validated GNN's current traffic
> state with a real historical hour-of-day traffic pattern derived from
> actual collected TomTom observations. This is a transparent hybrid
> extrapolation, not a trained end-to-end spatiotemporal GNN — the
> project's own collected data does not yet contain enough repeated
> same-segment observations 120 minutes apart to train and validate that
> kind of model, and no such training or accuracy claim is made. The
> existing GNN's own validated metrics (spatial R²≈0.62, temporal
> R²≈0.74) describe its current-state speed prediction, not this
> forecast — the two are never blended into one number."

Do not say a spatiotemporal GNN predicts 2 hours ahead, and do not state
any accuracy/error metric for the +120-minute forecast itself.
