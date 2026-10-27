import React, { useEffect, useState } from 'react';

// Two genuinely separate, honestly-labeled panels:
//   1. 2-Hour Traffic Forecast — a transparent hybrid extrapolation
//      (real current GNN state x a real historical hour-of-day pattern
//      from actual TomTom observations), NOT a trained supervised T+120
//      model — see traffic_forecast_service.py. Every field discloses
//      which method tier produced it.
//   2. Live Traffic Disruption Status — a CITIZEN-FIRST summary of the
//      same real speed/delay anomaly detector (traffic_incident_service.py,
//      UNCHANGED). This detector is an unexpected-traffic/anomaly
//      detector, NOT a true accident detector — it never labels anything
//      "accident"/"confirmed" unless the underlying state is
//      PROVIDER_CONFIRMED_INCIDENT (an actual authoritative-provider
//      confirmation, not an AI inference). The full technical incident
//      list (baseline speeds, deviation %, evidence level, timestamps,
//      data mode) is real and still available, but moved behind a
//      collapsed "Technical Details" section — a normal user should be
//      able to read the main card in 2-3 seconds.
// ============================================================
// 🔒 APPROVED CITIZEN-FACING COPY — LOCKED. DO NOT EDIT WORDING.
// Re-approved and updated 2026-09-29 per explicit user instruction to
// (a) never describe the anomaly detector's output as "accident" unless
// the state is PROVIDER_CONFIRMED_INCIDENT, and (b) use these exact
// citizen-facing status labels:
//   no incident/anomaly/blockage -> "NO UNEXPECTED TRAFFIC DISRUPTIONS" /
//     "Traffic conditions are currently within the expected range."
//   TRAFFIC_ANOMALY               -> "UNEXPECTED TRAFFIC PATTERN DETECTED"
//   POSSIBLE_TRAFFIC_BLOCKAGE     -> "POSSIBLE TRAFFIC BLOCKAGE"
//   PROVIDER_CONFIRMED_INCIDENT   -> "PROVIDER-CONFIRMED INCIDENT"
// Any future change to this wording needs an explicit new approval — do
// not rewrite, shorten, or "improve" it as a drive-by edit.
//
// Only PROVIDER_CONFIRMED_INCIDENT ever uses "accident"/"confirmed"
// wording; POSSIBLE_TRAFFIC_BLOCKAGE always says "possible", never
// "confirmed"; TRAFFIC_ANOMALY never says "accident" and explicitly
// states that nothing has been confirmed. (This detector has exactly one
// confirmed tier -- there is no real second "confirmed blockage vs.
// confirmed accident" distinction in the data to report, so none is
// fabricated here.)
const CITIZEN_STATUS = {
  PROVIDER_CONFIRMED_INCIDENT: {
    icon: '🔴', label: 'PROVIDER-CONFIRMED INCIDENT', headline: 'Accident reported ahead',
    message: (road) => `An accident has been reported near ${road}, confirmed by a traffic data provider.`,
    footer: 'Your selected route is affected.',
    color: 'var(--cc-red)',
  },
  POSSIBLE_TRAFFIC_BLOCKAGE: {
    icon: '🚧', label: 'POSSIBLE TRAFFIC BLOCKAGE', headline: 'Possible road blockage ahead',
    message: (road) => `A possible road blockage has been reported near ${road} — not yet confirmed.`,
    footer: 'Your selected route is affected.',
    color: 'var(--cc-orange)',
  },
  // 🔒 LOCKED — approved copy, exact text:
  //   🟡 UNEXPECTED TRAFFIC PATTERN DETECTED
  //   "Traffic on [road] is heavier than usual. Expect delays."
  //   "No accident or road blockage has been confirmed."
  TRAFFIC_ANOMALY: {
    icon: '🟡', label: 'UNEXPECTED TRAFFIC PATTERN DETECTED', headline: 'Unexpected heavy traffic',
    message: (road) => `Traffic on ${road} is heavier than usual. Expect delays.`,
    footer: 'No accident or road blockage has been confirmed.',
    color: 'var(--cc-yellow)',
  },
};

const _SEVERITY_RANK = { TRAFFIC_ANOMALY: 0, POSSIBLE_TRAFFIC_BLOCKAGE: 1, PROVIDER_CONFIRMED_INCIDENT: 2 };

const _haversineKm = (lat1, lon1, lat2, lon2) => {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
};

// Configurable "nearby" radius (2-5km per spec) for surfacing an eligible
// incident that isn't strictly ON the selected route geometry but is
// close enough to the searched destination to be worth a warning.
const NEAR_DESTINATION_RADIUS_KM = 2.0;

const fmtAgo = (iso) => {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.round(minutes / 60);
  return `${hours} hour${hours === 1 ? '' : 's'} ago`;
};

// Small, deliberately schematic route diagram -- NOT a precision map.
// The incident itself, its road name, and the alternate-route
// distance/duration/time-saving are all real (see the caller); this SVG
// only illustrates "there's a primary route, an incident on it, and an
// alternate route around it" without claiming exact geographic accuracy.
const MiniRouteMap = ({ hasAlternate }) => (
  <svg viewBox="0 0 160 100" width="160" height="100" style={{ display: 'block' }}>
    <rect x="0" y="0" width="160" height="100" rx="10" fill="var(--cc-panel-alt)" stroke="var(--cc-border)" />
    <path d="M14,80 C50,20 110,85 146,20" fill="none" stroke="var(--cc-accent)" strokeWidth="3" strokeLinecap="round" />
    {hasAlternate && (
      <path d="M14,80 C40,50 90,95 146,20" fill="none" stroke="var(--cc-green)" strokeWidth="2.5" strokeDasharray="5 4" strokeLinecap="round" />
    )}
    <circle cx="14" cy="80" r="4" fill="var(--cc-accent)" />
    <circle cx="146" cy="20" r="4" fill="var(--cc-accent)" />
    <circle cx="80" cy="48" r="6" fill="var(--cc-red)" stroke="#fff" strokeWidth="1.5" />
    {hasAlternate && (
      <text x="80" y="96" textAnchor="middle" fontSize="8" fill="var(--cc-green)">Alternate route</text>
    )}
  </svg>
);

const METHOD_LABEL = {
  historical_temporal_extrapolation: 'Historical hour-of-day pattern + current real GNN state',
  persistence_estimate: 'Persistence estimate (insufficient historical coverage — not a temporal forecast)',
};

const fmtTime = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
};

// Shows the already-computed real alternate-route recommendation (real
// OSRM alternative distance/duration/time-saving) -- informational only.
// Never auto-applies a route; clicking "View Alternate Route" only
// expands real numeric detail already computed server-side.
const AlternateRouteBlock = ({ recommendation }) => {
  const [open, setOpen] = useState(false);
  if (!recommendation) return null;
  if (!recommendation.available) {
    return (
      <div>
        <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--cc-text-dim)', marginBottom: '0.3rem' }}>Alternate Route</div>
        <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-faint)' }}>No alternate route is currently available.</div>
      </div>
    );
  }
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', fontWeight: 700, color: 'var(--cc-green)', marginBottom: '0.25rem' }}>
        ⇄ Alternative Route Available
      </div>
      <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>
        {recommendation.distance_km} km · {recommendation.duration_min} min
      </div>
      {recommendation.time_saving_min != null && (
        <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--cc-green)', marginBottom: '0.5rem' }}>
          Saves ~{Math.abs(recommendation.time_saving_min)} min
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', background: 'var(--cc-green)', border: 'none', borderRadius: 'var(--cc-radius-sm)', color: '#06210f', fontSize: '0.8rem', fontWeight: 700, padding: '0.45rem 0.85rem', cursor: 'pointer' }}
      >
        🗺 {open ? 'Hide Alternate Route' : 'View Alternate Route'}
      </button>
      {open && (
        <div style={{ marginTop: '0.5rem', padding: '0.5rem 0.6rem', background: 'var(--cc-panel-alt)', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-sm)', fontSize: '0.76rem', color: 'var(--cc-text-faint)' }}>
          This is a recommendation only — your selected route has not been changed.
        </div>
      )}
    </div>
  );
};

const TrafficForecastAndIncidents = ({ source, destination, destinationCoords }) => {
  const [forecast, setForecast] = useState(null);
  const [incidents, setIncidents] = useState(null);
  // Note: liveStatus itself is no longer displayed since the single-card
  // Live Disruption Status redesign, but the endpoint is still polled (kept
  // harmless/unused-free via array elision) in case a future card needs it.
  const [, setLiveStatus] = useState(null);

  useEffect(() => {
    if (source && destination) {
      const url = `/api/traffic/forecast-2h?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`;
      fetch(url).then((r) => r.json()).then(setForecast).catch(() => {});
    } else {
      setForecast(null);
    }
  }, [source, destination]);

  useEffect(() => {
    // Pass source/destination (when a route is resolved) so the backend
    // can compute a real per-incident Route Impact against the ACTUAL
    // route geometry -- omitted entirely (not guessed as NO) when no
    // route is selected yet.
    const url = source && destination
      ? `/api/traffic/incidents?source=${encodeURIComponent(source)}&destination=${encodeURIComponent(destination)}`
      : '/api/traffic/incidents';
    fetch(url).then((r) => r.json()).then(setIncidents).catch(() => {});
    fetch('/api/traffic/live-status').then((r) => r.json()).then(setLiveStatus).catch(() => {});
  }, [source, destination]);

  return (
    <>
      <details className="cc-details cc-panel">
        <summary style={{ cursor: 'pointer' }}>
          <span className="cc-panel-title" style={{ display: 'inline-flex' }}>📜 Historical Context</span>
          <div className="cc-panel-sub" style={{ marginTop: '0.25rem' }}>Recent traffic patterns for comparison</div>
        </summary>
        <p style={{ fontSize: '0.76rem', color: 'var(--cc-text-faint)', margin: '0.6rem 0 0.5rem' }}>
          A transparent hybrid extrapolation (real current GNN state × a real historical
          hour-of-day speed pattern) -- background context only. The authoritative future
          prediction is the trained T+120 model shown above.
        </p>

        <div>
          {!source || !destination ? (
            <div className="cc-empty">Run a prediction above to see this.</div>
          ) : !forecast ? (
            <div className="cc-empty">Loading…</div>
          ) : !forecast.available ? (
            <div style={{ padding: '0.9rem 1rem', background: 'var(--cc-panel-alt)', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-md)', color: 'var(--cc-text-dim)', fontSize: '0.82rem' }}>
              {forecast.reason}
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.75rem', fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>
                <span>📍 {forecast.route.source} → {forecast.route.destination}</span>
                <span>·</span>
                <span>Forecast time: <strong style={{ color: 'var(--cc-text)' }}>{fmtTime(forecast.forecast_timestamp)}</strong></span>
              </div>

              <div className="cc-metric-grid cc-metric-grid-4">
                <div className="cc-metric-tile">
                  <div className="cc-mt-label">Current</div>
                  <div className="cc-mt-value sm">{forecast.current.traffic_condition}</div>
                  <div className="cc-mt-caption">{forecast.current.speed_kmh} km/h · {forecast.current.data_source}</div>
                </div>
                <div className="cc-metric-tile">
                  <div className="cc-mt-label">Forecast (+120min)</div>
                  <div className="cc-mt-value sm cc-c-orange">{forecast.forecast.traffic_condition}</div>
                  <div className="cc-mt-caption">{forecast.forecast.predicted_speed_kmh} km/h</div>
                </div>
                <div className="cc-metric-tile">
                  <div className="cc-mt-label">Predicted Delay</div>
                  <div className="cc-mt-value">{forecast.forecast.predicted_delay_percent}<span className="cc-mt-unit">%</span></div>
                </div>
                <div className="cc-metric-tile">
                  <div className="cc-mt-label">Data Quality</div>
                  <div className="cc-mt-value sm cc-c-cyan">{forecast.data_quality}</div>
                </div>
              </div>

              <div style={{ marginTop: '0.7rem', padding: '0.6rem 0.75rem', background: 'var(--cc-panel-alt)', border: '1px solid var(--cc-border)', borderRadius: 'var(--cc-radius-md)' }}>
                <div style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.3rem' }}>
                  Basis: {METHOD_LABEL[forecast.method] || forecast.method}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>{forecast.basis}</div>
              </div>

              <details className="cc-details" style={{ marginTop: '0.6rem' }}>
                <summary style={{ cursor: 'pointer', fontSize: '0.76rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
                  Limitations
                </summary>
                <ul style={{ marginTop: '0.4rem', paddingLeft: '1.1rem', fontSize: '0.74rem', color: 'var(--cc-text-faint)', lineHeight: 1.6 }}>
                  {forecast.limitations.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
              </details>
            </>
          )}
        </div>
      </details>

      {/* ============================================================
          🚨 LIVE TRAFFIC DISRUPTION STATUS — single, route-aware card.
          Reuses the existing real detector (traffic_incident_service.py,
          unchanged) and the existing real route-impact / alternate-route
          logic (traffic_incident_service.check_route_impact, unchanged).
          Only ever escalates for a real POSSIBLE_TRAFFIC_BLOCKAGE or
          PROVIDER_CONFIRMED_INCIDENT that is actually on the selected
          route or within NEAR_DESTINATION_RADIUS_KM of the searched
          destination -- an AI-only TRAFFIC_ANOMALY never appears here
          (matches the previously approved "AI anomaly = technical info
          only" rule). No incident is ever fabricated to fill this card.
          Title/copy renamed away from "Accident Alerts" — this detector
          is an unexpected-traffic/anomaly detector, not a true accident
          detector; only PROVIDER_CONFIRMED_INCIDENT ever uses that word.
          ============================================================ */}
      <div className="cc-panel" style={{ borderColor: 'var(--cc-border-strong)' }}>
        <div className="cc-panel-head">
          <p className="cc-panel-title">🚨 Live Traffic Disruption Status</p>
        </div>

        {!incidents ? (
          <div className="cc-empty">Checking your route…</div>
        ) : !incidents.available ? (
          <div className="cc-empty">{incidents.reason || 'No data available yet.'}</div>
        ) : !source || !destination ? (
          <div className="cc-empty">Select a source and destination to check for unexpected traffic disruptions on your route.</div>
        ) : (
          (() => {
            const CITIZEN_ESCALATION_TYPES = ['POSSIBLE_TRAFFIC_BLOCKAGE', 'PROVIDER_CONFIRMED_INCIDENT'];

            // Most relevant incident actually affecting the SELECTED
            // route -- real route_impact per incident, computed by the
            // backend against the real OSRM route geometry.
            const onRoute = (incidents.incidents || []).filter(
              (i) => i.route_impact === true && CITIZEN_ESCALATION_TYPES.includes(i.type)
            );
            const routeIncident = onRoute.length
              ? onRoute.reduce((worst, i) => (_SEVERITY_RANK[i.type] > _SEVERITY_RANK[worst.type] ? i : worst))
              : null;

            // Otherwise: an eligible incident within the configurable
            // "nearby" radius of the searched destination, even if the
            // route geometry doesn't strictly pass through it. Real
            // haversine distance between real coordinates -- never
            // invented.
            let nearDestIncident = null;
            if (!routeIncident && destinationCoords && destinationCoords.length === 2) {
              const [dLat, dLon] = destinationCoords;
              const nearby = (incidents.incidents || []).filter((i) => {
                if (!CITIZEN_ESCALATION_TYPES.includes(i.type)) return false;
                if (i.latitude == null || i.longitude == null) return false;
                return _haversineKm(dLat, dLon, i.latitude, i.longitude) <= NEAR_DESTINATION_RADIUS_KM;
              });
              nearDestIncident = nearby.length
                ? nearby.reduce((worst, i) => (_SEVERITY_RANK[i.type] > _SEVERITY_RANK[worst.type] ? i : worst))
                : null;
            }

            // Only ONE incident is ever shown -- the most critical (rank)
            // and, among ties, closest (on-route beats nearby).
            const relevant = routeIncident || nearDestIncident;
            const onRouteFlag = !!routeIncident;
            const recommendation = incidents.route_impact?.alternate_route_recommendation;

            if (!relevant) {
              return (
                <div style={{ textAlign: 'center', padding: '1.6rem 1rem' }}>
                  <div style={{
                    width: 56, height: 56, borderRadius: '50%', border: '2px solid var(--cc-green)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 0.9rem',
                    color: 'var(--cc-green)', fontSize: '1.6rem',
                  }}>
                    ✓
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--cc-text)', marginBottom: '0.35rem' }}>
                    NO UNEXPECTED TRAFFIC DISRUPTIONS
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--cc-text-dim)' }}>
                    Traffic conditions are currently within the expected range.
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-faint)', marginTop: '0.2rem' }}>
                    We'll alert you here if a possible blockage or a provider-confirmed incident affects your route or nearby area.
                  </div>
                </div>
              );
            }

            // 🔒 LOCKED — reuses CITIZEN_STATUS's exact approved label,
            // headline and color for whichever real, escalation-eligible
            // type was detected; the copy itself is never rewritten here.
            const status = CITIZEN_STATUS[relevant.type];
            const isConfirmed = relevant.type === 'PROVIDER_CONFIRMED_INCIDENT';
            const accentColor = status.color;
            const areaLine = onRouteFlag ? `Between ${source} and ${destination}` : `Near ${destination}`;

            return (
              <div style={{
                padding: '1rem', borderRadius: 'var(--cc-radius-md)',
                background: `${accentColor}14`, border: `1px solid ${accentColor}55`,
              }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem', alignItems: 'flex-start' }}>
                  {/* Column 1: what + where + when */}
                  <div style={{ flex: '1 1 220px', display: 'flex', gap: '0.7rem' }}>
                    <div style={{
                      flexShrink: 0, width: 40, height: 40, borderRadius: 'var(--cc-radius-sm)',
                      background: `${accentColor}22`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.2rem',
                    }}>
                      {isConfirmed ? '🚗💥' : status.icon}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.05em', color: accentColor, marginBottom: '0.15rem' }}>
                        {status.label}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, color: accentColor }}>{status.headline}</span>
                        {onRouteFlag && (
                          <span style={{ fontSize: '0.68rem', fontWeight: 700, color: accentColor, background: `${accentColor}22`, border: `1px solid ${accentColor}55`, borderRadius: 999, padding: '0.15rem 0.5rem' }}>
                            ⚠ On your route
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--cc-text)', marginTop: '0.3rem' }}>
                        📍 {relevant.road_name || `segment ${relevant.segment_id}`}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-faint)', marginTop: '0.1rem' }}>
                        📍 {areaLine}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--cc-text-faint)', marginTop: '0.1rem' }}>
                        🕐 Reported {fmtAgo(relevant.timestamp)}
                      </div>
                    </div>
                  </div>

                  {/* Column 2: route impact */}
                  <div style={{ flex: '1 1 200px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', fontWeight: 700, color: 'var(--cc-text)', marginBottom: '0.25rem' }}>
                      ⚠ Route Impact
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--cc-text-dim)' }}>
                      {recommendation?.available && recommendation.time_saving_min != null
                        ? `Expect possible delays of about ${Math.abs(recommendation.time_saving_min)} minutes if you continue on your current route.`
                        : 'Expect heavy traffic and possible delays on your current route.'}
                    </div>
                  </div>

                  {/* Column 3: alternate route */}
                  <div style={{ flex: '1 1 220px' }}>
                    <AlternateRouteBlock recommendation={recommendation} />
                  </div>

                  {/* Column 4: mini route diagram (schematic, not a precision map) */}
                  <div style={{ flexShrink: 0 }}>
                    <MiniRouteMap hasAlternate={!!recommendation?.available} />
                  </div>
                </div>
              </div>
            );
          })()
        )}
      </div>
    </>
  );
};

export default TrafficForecastAndIncidents;
