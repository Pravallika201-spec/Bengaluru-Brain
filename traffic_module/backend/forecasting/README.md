# Traffic Forecasting & Anomaly Detection

This document covers the two NEW capabilities added to the Traffic module:
a genuine T+120-minute forecasting pipeline, and real-time speed/delay
anomaly detection. It does not replace or duplicate the existing GNN
traffic prediction (`real_gnn_service.py` / `/api/predict-enhanced`),
which is unchanged.

## 1. How the 2-hour forecast works (when data supports it)

`forecasting/forecast_dataset_builder.py` builds `T -> T+120min` training
pairs from **two genuine observations of the same real OSM edge**:

1. `csv_validator.py` reads `bengaluru_traffic_history.csv`, discarding or
   repairing malformed rows (see §3).
2. For every valid observation at time `T` of edge `E`, look for another
   valid observation of the **same edge `E`** whose timestamp falls within
   `TOLERANCE_MINUTES` (currently 15) of `T + 120min`.
3. If found, that pair becomes one training example: input = the real
   features at `T` (current speed, free-flow speed, speed ratio, delay %,
   travel times, confidence, hour, day-of-week, weekend flag — all known
   at time `T`, nothing from the future); target = the real
   `current_speed_kmh` / `speed_ratio` / `delay_percent` at the matched
   future timestamp.
4. If no observation falls inside the tolerance window, **no pair is
   created for that (edge, T)** — never the nearest available row, never
   an interpolated value.

`GET /api/traffic/forecast-2h` calls `get_forecast_status()`, which only
ever returns a real prediction if enough such pairs exist AND a model has
actually been trained on them. Neither is true today (see §2) — the
endpoint returns an honest `"available": false"` with the real
data-quality numbers instead.

**What this replaces**: the old `predict_traffic()` fallback set
`future_mins = predicted_duration_mins` — a literal copy of the current
prediction relabeled as a "forecast". That line still exists in the
legacy fallback path (untouched, out of scope for this change) but the
new `/api/traffic/forecast-2h` endpoint never uses it and never presents
a copied value as a forecast.

## 2. Actual data coverage (measured, not assumed)

As of the data currently in `bengaluru_traffic_history.csv`
(see `data/forecast/csv_validation_report.json` and
`data/forecast/data_readiness_report.json` for the machine-readable
version of these same numbers):

| Metric | Value |
|---|---|
| Total raw rows | 946 |
| Valid rows (as collected) | 930 |
| Repaired rows | 3 |
| Rejected rows | 13 |
| Unique real OSM edges observed | 369 |
| Time span | 2026-09-08 17:56 → 2026-09-09 17:49 (~24h) |
| Unique timestamps | 120 |
| **Median per-edge revisit interval** | **~353.6 minutes** |
| **Min per-edge revisit interval** | **336.9 minutes** |
| **T+120min pairs found (15-min tolerance)** | **0** |

**Verdict: INSUFFICIENT.** Zero T+120 pairs exist and no model has been
trained. This is not a bug in the pairing logic — it's a direct
consequence of the collector's citywide-coverage design
(`collect_bengaluru_traffic_production.py`): 369 wards are polled in
batches of 8 (47 batches), so each individual edge is revisited roughly
once per full rotation (~5.9 hours), not every ~2 hours. **Broad
citywide coverage and a 2-hour forecast horizon are in direct tension
under a fixed TomTom request quota** — you cannot have both 369 distinct
edges AND a <2-hour per-edge revisit interval without a much larger
quota. This tension is disclosed here rather than resolved by silently
picking one; see "What it would take" below.

## 3. Why rows were malformed, and how they were handled

Root-caused by actually inspecting the file (not assumed): the
collector's `get_traffic()` exception handler returns
`{"status", "http_status", "error"}` on a network failure — `"error"` is
not one of the CSV's 23 header columns, so a small number of `ERROR` rows
had a stray extra field.

- **3 rows repaired**: `status=ERROR` rows where columns 0–11 (real
  metadata + status + http_status) are still trustworthy; every
  traffic-measurement column from `frc` onward was set to `null` — not
  invented, since an ERROR row genuinely has no successful TomTom
  response to report.
- **13 rows rejected**: `status=OK` rows with an unexplained field-count
  shift where no safe, unambiguous column realignment could be
  determined. Per the "never invent/never misattribute a value" rule,
  these are discarded with a logged reason rather than guessed.

The original raw file is never modified or deleted — `csv_validator.py`
writes a separate clean copy to `data/forecast/bengaluru_traffic_history_clean.csv`.

## 4. Time-aware train/validation/test split

Not implemented — there is no trained model to split data for (see §2).
When enough real pairs exist, the intended split is: older timestamps →
train, later → validation, latest → temporal test (same convention
already used by `traffic_module/models/train_gnn_real_v1.py` for the
existing GNN), reported with MAE/RMSE/R² and sample counts per split —
never a single blended "accuracy" number.

## 5. How live TomTom data is obtained

Via the existing `collect_bengaluru_traffic_production.py` (ward-rotation
based) and `tomtom_traffic_service.py` (`get_point_traffic()`, used by
the incident detector's live-lookup path). `TOMTOM_API_KEY` (or
`TRAFFIC_API_KEY`) is read from the environment only — never hardcoded,
never logged, never returned by any endpoint. No endpoint added in this
change triggers a new TomTom API call; they all read what has already
been collected to `bengaluru_traffic_history.csv`. Live polling remains
a manual/explicit action (`python collect_bengaluru_traffic_production.py
--once`, or its own loop) — the backend never starts it automatically.

## 6–8. How anomalies are detected, and why "anomaly" ≠ "accident"

See `traffic_incident_service.py`'s module docstring and
`GET /api/traffic/incidents`. Classification hierarchy:

```
NORMAL
  -> TRAFFIC_ANOMALY        (a single anomaly-level speed drop/delay/closure flag)
  -> POSSIBLE_INCIDENT      (severe AND persistent across recent readings,
                              and/or corroborated by a nearby segment)
  -> PROVIDER_CONFIRMED_INCIDENT
                             (only if a real incident-feed confirms it)
```

A single bad reading never escalates past `TRAFFIC_ANOMALY` on its own —
it must be either severe **and** persistent across `min_persistent_observations`
(default 2) consecutive readings, or corroborated by
`min_corroborating_neighbors` (default 1) nearby anomalous segments, to
reach `POSSIBLE_INCIDENT`. The word "accident" never appears in the
classification vocabulary (enforced by
`tests/test_traffic_forecasting_and_incidents.py::test_never_classifies_as_accident_string`).

`PROVIDER_CONFIRMED_INCIDENT` requires an explicit `provider_confirmed=True`
passed in by the caller — this project's TomTom integration
(`tomtom_traffic_service.py`) has **no incidents-feed endpoint wired up**,
so nothing in the current system ever sets that flag. The tier exists in
the code (and is unit-tested) so the classification hierarchy is
complete, but it is honestly dormant — `GET /api/traffic/incidents`
reports `"provider_incident_feed_configured": false` in every response.

## 9. What happens when TomTom is unavailable

`GET /api/traffic/live-status` reports `tomtom_configured: false` (key
presence only, never the value) without making any request. The incident
detector and forecast-readiness check both fall back to whatever is
already in `bengaluru_traffic_history.csv` — historical, not live — and
say so explicitly (`live-status`'s `note` field, and the age of the last
observation).

## 10. Actual model metrics

None — no temporal forecasting model has been trained (see §2). The
existing spatial GNN's real metrics (unchanged by this work) remain in
`traffic_module/models/traffic_model_real_v1_metrics.json`:
spatial-test MAE≈5.925/RMSE≈7.685/R²≈0.622 (n=125), temporal-test
MAE≈3.019/RMSE≈4.639/R²≈0.741 (n=185).

## 11. Actual data coverage

See §2's table — this is the complete, current, measured picture. No
number here is estimated or rounded up for effect.

## 12. Known limitations

- **Zero T+120 forecast pairs exist today.** The forecast endpoint is a
  real, working pipeline with nothing to serve yet — not a stub, but
  also not a working forecast.
- **Citywide coverage vs. forecast horizon is a real architectural
  tension**, not a bug: the same collector cannot cheaply give you both
  369-ward breadth and a sub-2-hour per-edge revisit interval on a fixed
  TomTom quota. Resolving this requires either (a) a second,
  small-segment collector polling a handful of high-priority corridors
  every 5 minutes specifically for forecasting (separate from the
  ward-coverage collector), or (b) a materially larger TomTom quota.
  Neither was implemented here — flagging the tradeoff was judged more
  useful than picking one silently.
- **No incident-provider feed exists** in this project's TomTom
  integration — `PROVIDER_CONFIRMED_INCIDENT` is real code, unit-tested,
  and permanently unreachable in production until/unless one is added.
- **The anomaly detector's "expected speed" baseline** is either a
  recent same-segment historical average (when ≥2 prior observations
  exist) or the segment's own TomTom free-flow speed otherwise — both
  real values, but the free-flow fallback is a coarser notion of
  "expected" than a true recent baseline.
- **UI additions are intentionally minimal** (a forecast-status panel and
  an incident list on the existing Traffic tab) — map-overlay markers
  (Part G) and route/routing integration (Part H) were not implemented
  in this pass; the existing map, routing, and OR-Tools system are
  completely untouched.

## What it would take to close the forecast gap

A dedicated small-segment (e.g., 8–20 high-priority corridors) collector
loop polling every 5 minutes, run continuously for several days, would
produce a per-edge revisit interval well under the 120-minute target —
at which point `forecast_dataset_builder.py` (already built, already
tested) would start producing real pairs, and a genuinely trainable
first model becomes possible. No code changes would be needed in the
pairing/validation pipeline itself.

---

## 13. UPDATE — the actual 2-hour forecast now served (`traffic_forecast_service.py`)

Given a time constraint on collecting more data, the project needed a
forecast NOW rather than after another multi-day collection run. Rather
than wait indefinitely for §12's fix, a **transparent hybrid
extrapolation** was built and is what `GET /api/traffic/forecast-2h`
(now requiring `source`+`destination` query params — a route-level
forecast) actually serves:

```
real current route state (real_gnn_service.py, unmodified)
        x
real historical hour-of-day speed_ratio ratio
  (forecast_hour's avg / current_hour's avg, from actual TomTom
   observations — forecasting/historical_pattern.py)
        =
+120-minute projected speed/condition/delay
```

**This is NOT a trained supervised T+120 model** — it is explicitly
labeled `method: "historical_temporal_extrapolation"` (or
`"persistence_estimate"` when the forecast hour has <10 real historical
samples, in which case the current state is honestly carried forward
unchanged rather than temporally adjusted). Both current-state and
temporal-ratio inputs are real, measured values; nothing is interpolated
or invented. The spatial component (which edges matter, their current
real speed) comes entirely from the existing real GNN; the temporal
component is citywide-aggregated (all 369 monitored real edges pooled
per hour), not per-segment — disclosed in every response's
`limitations` list, since per-segment history remains too sparse
(median ~2.5 observations/edge) for a per-segment hourly pattern.

Data quality is reported as one of three qualitative, evidence-derived
labels — **never a random or fabricated number**:
`HIGH DATA SUPPORT` (REAL_GNN current state + ≥30 real samples at both
the current and forecast hour), `MODERATE DATA SUPPORT` (REAL_GNN or
extrapolated-GNN current state, thinner historical sample), `LIMITED
DATA SUPPORT` (heuristic current state, or no historical adjustment
could be applied at all).

See `traffic_forecast_service.py`'s module docstring for the full
method description, and `tests/test_traffic_forecasting_and_incidents.py`
for the route-forecast test coverage (120-minute horizon math, honest
handling of an unresolvable route, method-label discipline, no
"supervised"/"trained model" claims).

### What can honestly be said about this in a project review

- "The Traffic module produces a 2-hour-ahead forecast for a selected
  route by combining the project's real, validated GNN's current traffic
  state with a real historical hour-of-day traffic pattern derived from
  actual collected TomTom observations."
- "This is a transparent hybrid extrapolation, not a trained end-to-end
  spatiotemporal GNN — the project's own collected data does not yet
  contain enough repeated same-segment observations 120 minutes apart to
  train and validate that kind of model, and no such training or
  accuracy claim is made."
- "The existing GNN's own validated metrics (spatial R²≈0.62, temporal
  R²≈0.74) describe its CURRENT-state speed prediction, not this
  forecast — the two are never blended into one number."
- **Do not say**: "a spatiotemporal GNN predicts traffic 2 hours ahead"
  or state any accuracy/error metric for the +120-minute forecast itself
  — none has been measured, because no T+120 ground truth exists yet to
  measure it against.
