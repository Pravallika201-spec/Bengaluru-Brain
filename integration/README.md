# Integration Layer — Urban Predictive Intelligence (USI + Alerts)

Combines the **traffic** module and the **waste** module into a single
**Urban Severity Index (USI)** per named area, and drives bilingual
(Kannada + English) citizen alerts from it.

This layer imports from `traffic_module/backend` and `waste_module/waste_module`
but is kept physically separate from both, per the project's engineering
rules — neither original module is modified to make this work (aside from
the traffic-backend and waste OR-Tools bug fixes made during the Phase 1/2
audit, which were pre-existing bugs, not integration-specific changes).

## Files
- `traffic_signal.py` — traffic severity (0-100) for a named area. Prefers
  the real retrained GNN (`traffic_module/backend/real_gnn_service.py`) when
  the area falls near one of its ~750 real monitored segments; otherwise
  falls back to the simulated ward-stress model, **always labeling which
  source was used** — never silently presenting simulated data as real.
- `waste_signal.py` — waste overflow severity (0-100) for a named area, read
  directly from the waste module's real, populated
  `bengaluru_area_overflow_predictions.csv` (2,562 rows / 366 areas / 7
  prediction dates — the latest date per area is used).
- `usi_engine.py` — combines the two into one USI score + Green/Yellow/
  Orange/Red band, with a documented, configurable weighting
  (`usi_config.json`), and preserves both component scores + a human-
  readable reason so a dashboard can explain *why* an area scored as it did.
- `alerts.py` — turns a USI result into a severity-appropriate bilingual
  (English + natural Kannada, not word-for-word translation) citizen
  message, and a `send_sms_simulated()` stub that logs what *would* be sent
  — no real SMS provider is wired up (per project rules, that requires
  explicit sign-off later). The interface is written so swapping in a real
  provider (e.g. Twilio, MSG91) only means replacing that one function.
- `demo_usi_pipeline.py` — runnable end-to-end demo/verification script.

## Known coverage limits (stated up front, not discovered later)
- Traffic severity is REAL (GNN-based) only for areas near the ~750 edges
  the retrained model has ground truth for. Everywhere else it is
  SIMULATED (ward_stress.py), and the USI result always says which.
- Waste severity is real for the 366 named areas in the waste module's
  processed data; areas outside that set have no waste signal.
- Only 6 area names currently exist verbatim in BOTH modules' location
  data (Hebbal, Whitefield, Marathahalli, Indiranagar, HSR Layout,
  Shivajinagar) — these are the areas `demo_usi_pipeline.py` exercises.
  Extending coverage means adding shared area/ward identifiers to one or
  both modules' location tables — not something this integration layer can
  fabricate.
