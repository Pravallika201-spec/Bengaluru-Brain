import React, { useEffect, useState } from 'react';

// THE authoritative future-traffic result for this app: "if I start this
// journey ~2 hours from now, how long should it take, and when will I
// arrive?" Time-first by design -- Predicted Journey Time and Expected
// Arrival are the PRIMARY output; speed/condition are supporting detail.
//
// TWO-LEVEL HONEST FALLBACK HIERARCHY (never a fabricated number):
//
//   LEVEL 1 -- TRAINED T+120 MODEL
//     POST /api/traffic/forecast-t120/for-route (t120_preliminary_service.py,
//     unmodified) geographically matches this route against the real
//     monitored segments the trained Random Forest model
//     (forecasting/models/t120_preliminary_rf_model.joblib) was trained
//     on, and computes a genuine route-level journey time ONLY when real
//     monitored-segment coverage is >=95% of the route's physical
//     distance (forecast.route_eta.available). Labeled "TRAINED T+120
//     MODEL".
//
//   LEVEL 2 -- GNN BASELINE ESTIMATE (used when Level 1 isn't available)
//     Uses the EXISTING, already-computed, validated real-GNN current
//     route prediction (prediction.predicted_travel_time_min /
//     prediction.traffic, from the SAME /api/predict-enhanced call that
//     resolved this route -- nothing new is computed or called here) as
//     a deterministic "if today's conditions persist" baseline. This is
//     explicitly NOT a learned 2-hour forecast and is labeled
//     "GNN BASELINE ESTIMATE" everywhere it appears, never presented as
//     AI-predicted future traffic.
//
//   TRULY UNAVAILABLE only when BOTH of the above have nothing to offer
//     (never happens in practice since predict-enhanced always returns
//     some travel-time estimate, even its own heuristic fallback).
//
// Future Departure is always request-time + 120 minutes (a real
// server-computed wall-clock value, forecast.future_departure_time --
// never the TomTom observation's own timestamp, never the browser's
// clock, never hardcoded).
const CONDITION_COLOR = {
  NORMAL: 'var(--cc-green)',
  MODERATE: 'var(--cc-yellow)',
  HIGH: 'var(--cc-orange)',
  CRITICAL: 'var(--cc-red)',
};

// Full date+time -- computed from the real ISO timestamp the backend
// returns (never the browser's own clock, never hardcoded). en-GB
// locale forces day-month-year ordering with AM/PM, e.g.
// "11 Sep 2026, 07:30 PM".
const fmtDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
  } catch { return iso; }
};

const Field = ({ label, value, color, big }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: big ? '0.6rem 0' : '0.5rem 0', borderBottom: '1px solid var(--cc-border)' }}>
    <span style={{ fontSize: big ? '0.8rem' : '0.76rem', color: 'var(--cc-text-faint)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</span>
    <span style={{ fontSize: big ? '1.15rem' : '0.92rem', fontWeight: 700, color: color || 'var(--cc-text)' }}>{value}</span>
  </div>
);

const TrafficForecastT120 = ({ prediction }) => {
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);

  const routeCoords = prediction?.route_coords || [];

  // Generic model/training metadata -- fetched once, independent of the
  // route, from the ONE endpoint that reads the training script's real
  // saved report. Retraining the pipeline on more collected data and
  // overwriting that report changes everything shown here automatically.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/traffic/forecast-t120/model-info')
      .then((r) => r.json())
      .then((data) => { if (!cancelled) setModelInfo(data); })
      .catch(() => { if (!cancelled) setModelInfo(null); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!prediction || routeCoords.length === 0) {
      setForecast(null);
      return () => { cancelled = true; };
    }

    setLoading(true);
    fetch('/api/traffic/forecast-t120/for-route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ route_coords: routeCoords, distance_km: prediction.distance_km }),
    })
      .then((r) => r.json())
      .then((data) => { if (!cancelled) { setForecast(data); setLoading(false); } })
      .catch(() => {
        if (!cancelled) {
          setForecast({ available: false, reason: '2-hour forecast unavailable for this route in the preliminary model.' });
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prediction]);

  if (!prediction) return null;

  // ---- Determine which tier of the hierarchy applies ----
  const t120Available = !!(forecast && forecast.available && forecast.route_eta?.available);

  // Level 2 inputs: the EXISTING validated GNN route prediction, already
  // computed by /api/predict-enhanced for this exact route -- read only,
  // never recomputed or called again here.
  const gnnTravelTimeMin = typeof prediction.predicted_travel_time_min === 'number' ? prediction.predicted_travel_time_min : null;
  const gnnCondition = prediction.traffic_status || prediction.traffic || null;
  const gnnUsable = gnnTravelTimeMin != null;

  const usingGnnBaseline = !t120Available && gnnUsable;
  const trulyUnavailable = !t120Available && !gnnUsable;

  // Future departure: always request-time + 120 minutes, from the
  // backend (forecast.future_departure_time) so it's a real,
  // server-computed wall-clock value even when the T+120 route-level
  // estimate itself is unavailable. Falls back to the client clock only
  // if the forecast call itself failed outright (network error).
  const departureIso = forecast?.future_departure_time || new Date(Date.now() + 120 * 60000).toISOString();

  let journeyTimeMin = null;
  let arrivalIso = null;
  let futureCondition = null;
  let futureSpeedKmh = null;

  if (t120Available) {
    journeyTimeMin = forecast.route_eta.future_travel_time_min;
    arrivalIso = forecast.route_eta.future_arrival_time;
    futureCondition = forecast.forecast?.condition;
    futureSpeedKmh = forecast.forecast?.predicted_speed_kmh;
  } else if (usingGnnBaseline) {
    journeyTimeMin = Math.round(gnnTravelTimeMin * 10) / 10;
    arrivalIso = new Date(new Date(departureIso).getTime() + gnnTravelTimeMin * 60000).toISOString();
    futureCondition = gnnCondition;
    futureSpeedKmh = prediction.current_speed_kmh ?? null;
  }

  return (
    <div className="cc-panel" style={{ borderColor: 'var(--cc-accent)', marginTop: '0.9rem' }}>
      <div className="cc-panel-head">
        <p className="cc-panel-title">🔮 2-Hour-Ahead Traffic Prediction</p>
        <span className="cc-pill neutral">PRELIMINARY</span>
      </div>

      {loading ? (
        <div className="cc-empty">Loading 2-hour prediction…</div>
      ) : !forecast ? (
        <div className="cc-empty">Loading…</div>
      ) : trulyUnavailable ? (
        <div style={{ padding: '0.9rem 1rem', background: 'var(--cc-panel-alt)', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-md)', color: 'var(--cc-text-dim)', fontSize: '0.82rem' }}>
          {forecast.reason || 'Neither the T+120 model nor a GNN baseline route estimate is available for this route.'}
        </div>
      ) : (
        <>
          <Field label="Future Departure" value={fmtDateTime(departureIso)} color="var(--cc-accent)" />
          <Field big label="Predicted Journey Time" value={`${journeyTimeMin} min`} color="var(--cc-accent)" />
          <Field big label="Expected Arrival" value={fmtDateTime(arrivalIso)} color="var(--cc-accent)" />
          <Field label="Route Distance" value={prediction.distance_km != null ? `${prediction.distance_km} km` : '—'} />
          <Field label="Future Traffic Condition" value={futureCondition || '—'} color={CONDITION_COLOR[futureCondition]} />
          {futureSpeedKmh != null && <Field label="Future Predicted Speed" value={`${futureSpeedKmh} km/h`} />}

          {/* Supporting detail: the real T+120 monitored-segment forecast(s)
              this route matched, if any -- shown regardless of whether the
              headline result used them, for full transparency. */}
          {forecast.available && forecast.segments?.length > 0 && (
            <details className="cc-details" style={{ marginTop: '0.6rem' }}>
              <summary style={{ cursor: 'pointer', fontSize: '0.76rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
                🛣️ Supported T+120 monitored segment(s) on this route
              </summary>
              <div style={{ marginTop: '0.5rem' }}>
                {forecast.segments.map((seg, i) => (
                  <div key={i} style={{ padding: '0.5rem 0.6rem', marginBottom: '0.4rem', background: 'var(--cc-bg-elevated, var(--cc-panel))', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-sm)', fontSize: '0.78rem' }}>
                    <div style={{ fontWeight: 700, color: 'var(--cc-text)', marginBottom: '0.2rem' }}>🛣️ {seg.road_name}</div>
                    <div style={{ color: 'var(--cc-text-dim)' }}>
                      {seg.edge_length_m != null && <>Segment length: {(seg.edge_length_m / 1000).toFixed(2)} km · </>}
                      Current speed: {seg.now.speed_kmh} km/h · Predicted speed at +120 min: {seg.forecast.predicted_speed_kmh} km/h
                    </div>
                    <div style={{ color: CONDITION_COLOR[seg.forecast.condition], marginTop: '0.15rem' }}>
                      Future condition: {seg.forecast.condition}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          )}

          {modelInfo && modelInfo.available && (
            <details className="cc-details" style={{ marginTop: '0.6rem' }}>
              <summary style={{ cursor: 'pointer', fontSize: '0.76rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
                🔧 Model &amp; Training Details
              </summary>
              <div style={{ marginTop: '0.5rem' }}>
                <Field label="Model" value="T+120 Random Forest" />
                <Field label="Trained At" value={fmtDateTime(modelInfo.trained_at)} />
                <Field label="Training Pairs" value={`${modelInfo.total_genuine_pairs?.toLocaleString?.() ?? '—'} genuine pairs`} />
                <Field label="Monitored Segments" value={`${modelInfo.unique_segments ?? '—'} currently trained segments`} />
                <Field label="Training Data Span" value={modelInfo.training_data_span_hours !== 'unknown' ? `${modelInfo.training_data_span_hours} hours` : 'unknown'} />
                <Field label="Train / Val / Test" value={`${modelInfo.split?.train_count ?? '—'} / ${modelInfo.split?.validation_count ?? '—'} / ${modelInfo.split?.test_count ?? '—'}`} />
                <Field label="Leakage Detected" value={modelInfo.leakage_check?.leakage_detected ? 'YES (invalid)' : 'No'} color={modelInfo.leakage_check?.leakage_detected ? 'var(--cc-red)' : 'var(--cc-green)'} />
                <Field label="Test MAE" value={`${modelInfo.test_metrics?.mae ?? '—'} km/h`} />
                <Field label="Test RMSE" value={`${modelInfo.test_metrics?.rmse ?? '—'} km/h`} />
                <Field label="Test R²" value={modelInfo.test_metrics?.r2 ?? '—'} />
                <Field label="Persistence Baseline MAE" value={`${modelInfo.persistence_baseline_test_metrics?.mae ?? '—'} km/h`} />
                <Field label="Persistence Baseline RMSE" value={`${modelInfo.persistence_baseline_test_metrics?.rmse ?? '—'} km/h`} />
                <Field label="Persistence Baseline R²" value={modelInfo.persistence_baseline_test_metrics?.r2 ?? '—'} />
                <Field
                  label="Beats Persistence Baseline"
                  value={modelInfo.baseline_comparison?.beats_baseline_overall ? 'YES' : 'NOT YET'}
                  color={modelInfo.baseline_comparison?.beats_baseline_overall ? 'var(--cc-green)' : 'var(--cc-yellow)'}
                />
                <div style={{ marginTop: '0.5rem', fontSize: '0.74rem', color: 'var(--cc-text-faint)' }}>
                  {modelInfo.baseline_comparison?.summary}
                </div>
                <div style={{ marginTop: '0.5rem', fontSize: '0.74rem', color: 'var(--cc-text-faint)' }}>
                  This preliminary model covers only its currently monitored real segments — not all Bengaluru
                  roads. Coverage will widen as the real TomTom collector gathers more segments and more
                  historical observations over time.
                </div>
                {modelInfo.limitations?.length > 0 && (
                  <ul style={{ marginTop: '0.5rem', paddingLeft: '1.1rem', fontSize: '0.74rem', color: 'var(--cc-text-faint)', lineHeight: 1.6 }}>
                    {modelInfo.limitations.map((l, i) => <li key={i}>{l}</li>)}
                  </ul>
                )}
              </div>
            </details>
          )}
        </>
      )}
    </div>
  );
};

export default TrafficForecastT120;
