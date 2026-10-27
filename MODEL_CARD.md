# Model Card — Bengaluru Brain Traffic GNN (`traffic_model_real_v1`)

## Dataset

- **760 real TomTom-observed OSM edges**, single spatial snapshot (2026-08-27).
- **13 real TomTom-monitored road segments**, polled repeatedly over ~3 days (2026-08-26 onward) — the temporal-generalization portion of the training data.
- Combined into a labeled set of **749 edges** with usable ground truth (some snapshot rows were dropped for missing node coordinates or graph-connectivity issues — see `traffic_module/models/prepare_real_traffic_dataset.py`).
- Trained subgraph: **4,304 real OSM nodes, 5,819 real OSM edges** (Bengaluru road network, all real — no synthetic nodes/edges).

## Features

- **Node features** (3): `degree`, `avg_incident_maxspeed_kph`, `avg_incident_length_m` — all computed from real OSM edge attributes of the subgraph.
- **Scalar (edge-level) features** (14): `edge_length_m`, `base_speed_kph`, `hour_sin`, `hour_cos`, `is_weekend`, plus a 9-category one-hot Functional Road Class (`frc_FRC0`…`frc_UNKNOWN`).
- All features are real, either directly from OSM tags or standard time-of-day encodings — none are fabricated placeholders.

## Target

Predicted road speed (km/h) for a given edge at a given hour/weekend context.

## Architecture

3-layer `GCNConv` graph encoder (hidden sizes 64 → 32 → 16) producing per-node embeddings, followed by an edge-level MLP that takes the concatenated embeddings of an edge's two endpoints plus the 14 scalar features and predicts a single speed value. Implemented in PyTorch Geometric (`real_gnn_service.py::TrafficGNNReal`).

## Training

See `traffic_module/models/train_gnn_real_v1.py`. Two held-out test splits were used:
- **Spatial holdout**: edges geographically excluded from training, testing generalization to unseen road segments.
- **Temporal holdout**: later time-of-day observations on the same monitored segments, testing generalization across time.

## Metrics (from the checkpoint itself, not re-derived)

| Split | MAE (km/h) | RMSE (km/h) | R² | n |
|---|---|---|---|---|
| Spatial test | 5.92 | 7.68 | 0.622 | 125 |
| Temporal test | 3.02 | 4.64 | 0.741 | 185 |

These are the only accuracy claims this model makes. They apply to the **749 labeled edges' test splits only.**

## Coverage — the honest limitation, and this session's expansion

- The model has **real ground-truth validation for 749 of ~393,090 edges** in the full Bengaluru OSM graph (~0.19%). This was true before this session and remains true — no amount of architecture change manufactures ground truth that doesn't exist.
- **New this session**: the model's own 5,819-edge trained subgraph contains 4,807 real edges beyond the 749 labeled ones. Because the GNN computes node embeddings via message-passing over the *whole* subgraph (not just labeled edges), it can genuinely run the same trained forward pass on these additional real edges. This is real inference — the same weights, the same architecture, real OSM length/maxspeed as input — but **these specific edges were never scored against ground truth**, so the R²/MAE/RMSE above do **not** apply to them.
  - Reported separately as `REAL_GNN_V1_EXTRAPOLATED`, confidence capped at 0.25 (vs. up to 0.9 for the validated tier), with an explicit "not individually validated" note in every API response that uses it.
  - This raises route-matchable real-model coverage from 749 to 5,556 edges (~1.4% of the citywide graph) — a genuine ~7.4x increase using zero new external data, not a coverage number achieved by relaxing what counts as "real."
- **What would be required to go further**: real ground-truth speed observations (TomTom or equivalent) for edges outside the current 5,819-edge subgraph. No such data exists in this environment. Fabricating labels or claiming citywide coverage without them would violate the project's own honesty requirement — so this is explicitly reported as a limitation rather than worked around.

## Coverage reporting — separated, not merged (Priority 4 audit)

Ward-level traffic coverage is now checked directly against each of the 369 real wards' own centroid coordinates (previously only the 25 named locations curated in `location_data.py` were checked, silently under-reporting wards that genuinely have real monitored edges within their boundary). The result is reported as four **separate** counts, never collapsed into one headline number:

| Tier | Count | Meaning |
|---|---|---|
| `REAL_GNN` | 39 wards | A real TomTom-labeled edge is within 200m of the ward centroid — validated, covered by the R²/MAE/RMSE metrics above |
| `REAL_GNN_EXTRAPOLATED` | 34 wards | A real (unlabeled) subgraph edge is within 200m — genuine inference, no test-set validation |
| `SIMULATED_WARD_STRESS` | 296 wards | No real edge nearby; falls back to that ward's own simulated stress score |
| `NO_DATA` | 0 wards | (Kept as an honest fallback; currently empty because tier 3 now covers all real wards) |

This does **not** mean "369 wards have real traffic predictions" — only 73 (39+34) do. The other 296 are simulated, clearly labeled as such.

## Limitations

- Not a citywide traffic model. Most routes in Bengaluru will not have any GNN signal (validated or extrapolated) and will honestly fall back to static routing + weather/incident heuristics.
- No live retraining or online learning — this is a static, offline-trained checkpoint. "Real-time" claims in this system refer to *live inference on a static model*, never to the model itself being refreshed from a live feed (no such feed is configured in this environment).
- FRC (Functional Road Class) for the 4,807 extrapolated edges is set to `UNKNOWN` rather than guessed from the OSM `highway` tag, since no verified OSM-highway→FRC crosswalk was available to match how the original labeled data was classified — an approximate guess here was judged worse than an honest "unknown."
- Route-level predictions (in `/api/predict-enhanced`) scale the *whole route's* travel time using the ratio between the matched segment(s)' predicted speed and the router's free-flow estimate. This is a documented corridor-level approximation, not true segment-by-segment integration across the entire route geometry.
