import React from 'react';
import { Milestone, Clock, ShieldCheck, Sun, Route as RouteIcon } from 'lucide-react';

const STATUS_PILL = { low: 'low', clear: 'low', moderate: 'medium', high: 'high', critical: 'critical', severe: 'critical' };
const STATUS_COLOR = { low: 'var(--cc-green)', clear: 'var(--cc-green)', moderate: 'var(--cc-yellow)', high: 'var(--cc-orange)', critical: 'var(--cc-red)', severe: 'var(--cc-red)' };

// Plain-language restatement of the same real traffic_status the pill
// already shows — no new signal, just a friendlier caption under the
// "Traffic Condition" tile.
const STATUS_DESCRIPTION = {
  low: 'Smooth traffic, minimal delays expected.',
  clear: 'Smooth traffic, minimal delays expected.',
  moderate: 'Smooth traffic with minor delays.',
  high: 'Heavy traffic — expect noticeable delays.',
  critical: 'Severe congestion — significant delays expected.',
  severe: 'Severe congestion — significant delays expected.',
};

// Same for the real weather.impact field (LOW/MEDIUM/HIGH, from the
// backend's weather_logic.py) — a plain-language restatement, not a new
// computed value.
const WEATHER_IMPACT_DESCRIPTION = {
  low: 'Condition is ideal for travel.',
  medium: 'Condition may add minor delays.',
  high: 'Condition may cause significant delays.',
};

const ResultCard = ({ prediction }) => {
  const statusKey = (prediction.traffic_status || prediction.traffic || '').toLowerCase();
  const statusColor = STATUS_COLOR[statusKey] || 'var(--cc-yellow)';
  const statusPill = STATUS_PILL[statusKey] || 'medium';
  const statusLabel = prediction.traffic_status || prediction.traffic || '—';

  // /api/predict-enhanced always returns a real, server-computed
  // congestion_score (0-100) — derived from the real measured slowdown
  // ratio (REAL_GNN/extrapolated) or the real delay-vs-base-time ratio
  // (heuristic fallback). No client-side lookup table or random value.
  const congestionScore = typeof prediction.congestion_score === 'number' ? prediction.congestion_score : 0;

  const isRealGnn = prediction.traffic_source === 'REAL_GNN';
  const isExtrapolated = prediction.traffic_source === 'REAL_GNN_EXTRAPOLATED';
  const sourceTag = isRealGnn ? { text: 'REAL GNN (validated)', cls: 'real' }
    : isExtrapolated ? { text: 'REAL GNN (extrapolated)', cls: 'extrapolated' }
    : { text: 'HEURISTIC — no live/ML coverage here', cls: 'heuristic' };

  const fmt = (v) => (v == null ? '—' : Math.round(v));

  const predictedEta = prediction.predicted_eta_min ?? prediction.predicted_travel_time_min;
  const confidencePct = Math.round((prediction.model_confidence ?? prediction.confidence ?? 0) * 100);
  const weatherImpactKey = (prediction.weather?.impact || '').toLowerCase();

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title">
          {isRealGnn || isExtrapolated ? '🧠 AI-Assisted Traffic Prediction' : '📏 Traffic Estimate (Heuristic)'}
        </p>
        <span className={`cc-pill ${statusPill}`}>{statusLabel}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
        <span className={`cc-source-tag ${sourceTag.cls}`}>{sourceTag.text}</span>
        <span style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>
          📍 {prediction.source} → {prediction.destination}
        </span>
      </div>

      {/* Primary at-a-glance metrics: distance, ETA, condition, confidence.
          Current ETA/speed, predicted speed, raw congestion %, and GNN
          segment count are real values too — they're not gone, just moved
          into "Data & Model Details" below so the main view stays to the
          four numbers a rider actually scans first. */}
      <div className="cc-metric-grid cc-metric-grid-4">
        <div className="cc-metric-tile cc-metric-tile-icon">
          <div className="cc-mt-label"><Milestone size={13} /> Distance</div>
          <div className="cc-mt-value">{prediction.distance_km}<span className="cc-mt-unit">km</span></div>
          <div className="cc-mt-caption">Total travel distance</div>
        </div>
        <div className="cc-metric-tile cc-metric-tile-icon">
          <div className="cc-mt-label"><Clock size={13} /> Predicted Time (ETA)</div>
          <div className="cc-mt-value" style={{ color: statusColor }}>{fmt(predictedEta)}<span className="cc-mt-unit">min</span></div>
          <div className="cc-mt-caption">Estimated arrival time</div>
        </div>
        <div className="cc-metric-tile cc-metric-tile-icon">
          <div className="cc-mt-label">
            <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: statusColor }} />
            {' '}Traffic Condition
          </div>
          <div className="cc-mt-value sm" style={{ color: statusColor, textTransform: 'uppercase' }}>{statusLabel}</div>
          <div className="cc-mt-caption">{STATUS_DESCRIPTION[statusKey] || 'Current predicted congestion level.'}</div>
        </div>
        <div className="cc-metric-tile cc-metric-tile-icon">
          <div className="cc-mt-label"><ShieldCheck size={13} /> Confidence</div>
          <div className="cc-mt-value cc-c-cyan">{confidencePct}<span className="cc-mt-unit">%</span></div>
          <div className="cc-mt-caption">Model confidence</div>
        </div>
      </div>

      {/* Weather + recommendation — genuinely useful, kept visible */}
      <div className="cc-metric-grid" style={{ marginTop: '0.75rem', gridTemplateColumns: prediction.incident?.detected ? undefined : 'repeat(2, minmax(0,1fr))' }}>
        <div className="cc-metric-tile cc-metric-tile-icon">
          <div className="cc-mt-label"><Sun size={13} /> Weather</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span className="cc-mt-value sm">{prediction.weather?.condition || prediction.weather || '—'}</span>
            {prediction.weather?.temperature != null && <span style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>{prediction.weather.temperature}°C</span>}
            {prediction.weather?.impact && <span style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)' }}>Impact: <strong style={{ color: 'var(--cc-text-dim)' }}>{prediction.weather.impact}</strong></span>}
          </div>
          <div className="cc-mt-caption">{WEATHER_IMPACT_DESCRIPTION[weatherImpactKey] || 'Current conditions for this route.'}</div>
        </div>
        {prediction.incident?.detected && (
          <div className="cc-metric-tile" style={{ borderColor: 'var(--cc-orange)' }}>
            <div className="cc-mt-label">Incident</div>
            <div className="cc-mt-value sm cc-c-orange">{prediction.incident.type}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--cc-text-faint)', marginTop: '0.2rem' }}>+{prediction.incident.impact_min} min impact</div>
          </div>
        )}
        {prediction.recommended_route && (
          <div className="cc-metric-tile cc-metric-tile-icon">
            <div className="cc-mt-label"><RouteIcon size={13} /> Recommendation</div>
            <div className="cc-mt-value sm cc-c-green">{prediction.recommended_route}</div>
            <div className="cc-mt-caption">Best route based on current traffic and road conditions.</div>
          </div>
        )}
      </div>

      {/* Collapsible technical detail — full transparency preserved, just
          not forced on the main view. Native <details> — no extra state. */}
      <details className="cc-details" style={{ marginTop: '0.85rem' }}>
        <summary style={{ cursor: 'pointer', fontSize: '0.78rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
          🔧 Data &amp; Model Details
        </summary>
        <div style={{ marginTop: '0.6rem' }}>
          <div className="cc-metric-grid">
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Current ETA</div>
              <div className="cc-mt-value sm">{fmt(prediction.current_eta_min ?? prediction.current_travel_time_min)}<span className="cc-mt-unit">min</span></div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Current Speed</div>
              <div className="cc-mt-value sm">{prediction.current_speed_kmh}<span className="cc-mt-unit">km/h</span></div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Predicted Speed</div>
              <div className="cc-mt-value sm">{prediction.predicted_speed_kmh}<span className="cc-mt-unit">km/h</span></div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Congestion Score</div>
              <div className="cc-mt-value sm">{Math.round(congestionScore)}<span className="cc-mt-unit">%</span></div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">GNN Coverage</div>
              <div className="cc-mt-value sm">
                {isRealGnn || isExtrapolated
                  ? `${prediction.matched_segments ?? prediction.coverage?.road_segments_used ?? 0} segments matched`
                  : 'Not covered here'}
              </div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Free-Flow ETA</div>
              <div className="cc-mt-value sm">{fmt(prediction.free_flow_eta_min ?? prediction.base_travel_time_min)}<span className="cc-mt-unit">min</span></div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Matched Segments</div>
              <div className="cc-mt-value sm">{prediction.matched_segments ?? prediction.coverage?.road_segments_used ?? 0}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Route Coverage</div>
              <div className="cc-mt-value sm">{prediction.route_coverage?.percentage_real ?? prediction.coverage?.percentage_real ?? 0}%</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Traffic Data Status</div>
              <div className="cc-mt-value sm" style={{ fontSize: '0.7rem', lineHeight: 1.3 }}>{prediction.traffic_data_status || '—'}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Data Age</div>
              <div className="cc-mt-value sm" style={{ fontSize: '0.7rem', lineHeight: 1.3 }}>{prediction.data_age || 'no live feed'}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Prediction Time</div>
              <div className="cc-mt-value sm" style={{ fontSize: '0.7rem' }}>
                {prediction.prediction_timestamp ? new Date(prediction.prediction_timestamp).toLocaleTimeString() : '—'}
              </div>
            </div>
          </div>

          <div style={{ marginTop: '0.6rem', padding: '0.6rem 0.75rem', background: 'var(--cc-panel-alt)', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-md)', fontSize: '0.76rem', color: 'var(--cc-text-dim)' }}>
            <strong style={{ color: 'var(--cc-text)' }}>Model:</strong> {prediction.model || prediction.model_info?.model}
          </div>

          {prediction.real_gnn_signal?.covered && (
            <div style={{ marginTop: '0.6rem' }}>
              <p className="cc-panel-sub" style={{ marginBottom: '0.35rem', fontWeight: 700 }}>Matched Real Segments</p>
              <div style={{ overflowX: 'auto' }}>
                <table className="cc-table">
                  <thead><tr><th>Road</th><th>Distance from route</th><th>Predicted speed</th></tr></thead>
                  <tbody>
                    {(prediction.real_gnn_signal.matched_segments || []).map((seg, i) => (
                      <tr key={i}><td>{seg.road_name}</td><td>{seg.distance_from_route_m}m</td><td>{seg.predicted_speed_kmh} km/h</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {prediction.alternative_routes && prediction.alternative_routes.length > 0 && (
            <div style={{ marginTop: '0.6rem' }}>
              <p className="cc-panel-sub" style={{ marginBottom: '0.35rem', fontWeight: 700 }}>Alternative Routes</p>
              <div style={{ overflowX: 'auto' }}>
                <table className="cc-table">
                  <thead><tr><th>Route</th><th>Distance</th><th>Time</th><th>Traffic</th></tr></thead>
                  <tbody>
                    {prediction.alternative_routes.map((route, i) => (
                      <tr key={i}><td>{route.name}</td><td>{route.distance_km} km</td><td>{route.current_time_min} min</td><td>{route.traffic_level}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </details>
    </div>
  );
};

export default ResultCard;
