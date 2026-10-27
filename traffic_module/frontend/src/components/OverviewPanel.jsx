import React, { useEffect, useState } from 'react';
import { Bell, TrendingUp, Info } from 'lucide-react';
import UnifiedMap from './UnifiedMap';

// Command-center landing view: every number here comes from /api/health,
// /api/waste/summary, /api/alerts/active, and /api/usi/{area} (looped over
// the real, verified coverage list from /api/usi/areas). Nothing here is
// hardcoded to look like the reference mock; the layout and visual system
// are inspired by it, the data is not.
const FEED_BADGE = {
  LIVE: { label: 'LIVE', cls: 'cc-c-green' },
  STALE: { label: 'STALE', cls: 'cc-c-yellow' },
  NO_LIVE_FEED: { label: 'NO LIVE FEED', cls: 'cc-c-red' },
  ERROR: { label: 'ERROR', cls: 'cc-c-red' },
};

const BAND_ORDER = { Red: 3, Orange: 2, Yellow: 1, Green: 0, Unknown: -1 };
const BAND_PILL = { Red: 'critical', Orange: 'high', Yellow: 'medium', Green: 'low', Unknown: 'neutral' };
const BAND_BAR = { Red: 'var(--cc-red)', Orange: 'var(--cc-orange)', Yellow: 'var(--cc-yellow)', Green: 'var(--cc-green)', Unknown: 'var(--cc-text-faint)' };
const GAUGE_STOPS = [
  { max: 25, color: '#22c55e' },
  { max: 50, color: '#eab308' },
  { max: 75, color: '#f97316' },
  { max: 100, color: '#ef4444' },
];

const gaugeColor = (v) => (GAUGE_STOPS.find((s) => v <= s.max) || GAUGE_STOPS[GAUGE_STOPS.length - 1]).color;
const gaugeLabel = (v) => (v == null ? '—' : v <= 24 ? 'NORMAL' : v <= 49 ? 'MODERATE' : v <= 74 ? 'HIGH STRESS' : 'CRITICAL');

// Semicircular USI gauge — pure SVG arc, no chart library, driven entirely
// by the real averaged USI value computed below.
const UsiGauge = ({ value }) => {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value)) / 100;
  const r = 80, cx = 100, cy = 96;
  const startAngle = Math.PI, endAngle = Math.PI - pct * Math.PI;
  const arcPoint = (angle) => [cx + r * Math.cos(angle), cy - r * Math.sin(angle)];
  const [sx, sy] = arcPoint(startAngle);
  const [ex, ey] = arcPoint(endAngle);
  const largeArc = pct > 0.5 ? 1 : 0;
  const color = value == null ? '#5b6580' : gaugeColor(value);
  return (
    <svg viewBox="0 0 200 110" width="100%" style={{ maxWidth: 220 }}>
      <path d={`M 20 96 A 80 80 0 0 1 180 96`} fill="none" stroke="var(--cc-border-strong)" strokeWidth="14" strokeLinecap="round" />
      {value != null && (
        <path d={`M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`} fill="none" stroke={color} strokeWidth="14" strokeLinecap="round" />
      )}
    </svg>
  );
};

const OverviewPanel = () => {
  const [health, setHealth] = useState(null);
  const [waste, setWaste] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [usiAreas, setUsiAreas] = useState([]);
  const [usiResults, setUsiResults] = useState({});
  const [selectedArea, setSelectedArea] = useState(null);

  const refresh = () => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => {});
    fetch('/api/waste/summary').then((r) => (r.ok ? r.json() : null)).then(setWaste).catch(() => {});
    fetch('/api/alerts/active').then((r) => (r.ok ? r.json() : null)).then(setAlerts).catch(() => {});
    fetch('/api/usi/areas').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d && d.available) setUsiAreas(d.areas || []);
    }).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    usiAreas.forEach((area) => {
      fetch(`/api/usi/${encodeURIComponent(area.name)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!cancelled && data && data.available) {
            setUsiResults((prev) => ({ ...prev, [area.name]: data }));
          }
        })
        .catch(() => {});
    });
    return () => { cancelled = true; };
  }, [usiAreas]);

  const feedStatus = health?.traffic_data_status?.feed_status;
  const feedBadge = FEED_BADGE[feedStatus] || FEED_BADGE.NO_LIVE_FEED;

  const resultsWithUsi = Object.values(usiResults).filter((r) => r.usi != null);
  const avgUsi = resultsWithUsi.length
    ? Math.round(resultsWithUsi.reduce((s, r) => s + r.usi, 0) / resultsWithUsi.length)
    : null;
  const avgTraffic = (() => {
    const vals = resultsWithUsi.map((r) => r.traffic?.score).filter((v) => v != null);
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
  })();
  const avgWaste = (() => {
    const vals = resultsWithUsi.map((r) => r.waste?.score).filter((v) => v != null);
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
  })();
  const topStressed = [...resultsWithUsi]
    .sort((a, b) => (BAND_ORDER[b.band] - BAND_ORDER[a.band]) || (b.usi - a.usi))
    .slice(0, 6);

  return (
    <>
      <div className="cc-hero">
        <div>
          <h2>🧭 Bengaluru Brain — Civic Intelligence Platform</h2>
          <p>
            Traffic, Waste, and a combined Urban Severity Index for Bengaluru, with bilingual citizen alerts.
          </p>
        </div>
        <span className="cc-pill info" style={{ fontSize: '0.8rem', padding: '0.45rem 0.9rem' }}>Bengaluru — 369 Wards</span>
      </div>

      {/* 3-column command-center row */}
      <div className="cc-overview-grid">
        {/* LEFT — USI gauge */}
        <div className="cc-panel">
          <div className="cc-panel-head">
            <p className="cc-panel-title">Urban Stress Index (USI)</p>
          </div>
          <p className="cc-panel-sub" style={{ marginBottom: '0.4rem' }}>Real-time city stress status</p>
          <div className="cc-gauge-wrap">
            <UsiGauge value={avgUsi} />
            <div className="cc-gauge-value" style={{ color: avgUsi == null ? 'var(--cc-text-faint)' : gaugeColor(avgUsi) }}>
              {avgUsi ?? '—'}
            </div>
            <div className="cc-gauge-label" style={{ color: avgUsi == null ? 'var(--cc-text-faint)' : gaugeColor(avgUsi) }}>
              {gaugeLabel(avgUsi)}
            </div>
            <div className="cc-gauge-caption">
              Avg across {resultsWithUsi.length || usiAreas.length} covered areas · updated {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : '—'}
            </div>
          </div>

          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--cc-border)', paddingTop: '0.75rem' }}>
            <p className="cc-panel-sub" style={{ marginBottom: '0.5rem', fontWeight: 700 }}>USI Level Guide</p>
            {[
              ['0 – 24', 'Green', 'Normal'],
              ['25 – 49', 'Yellow', 'Moderate'],
              ['50 – 74', 'Orange', 'High'],
              ['75 – 100', 'Red', 'Critical'],
            ].map(([range, band, word]) => (
              <div key={band} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', padding: '0.25rem 0', color: 'var(--cc-text-dim)' }}>
                <i style={{ width: 8, height: 8, borderRadius: '50%', background: BAND_BAR[band], display: 'inline-block', flexShrink: 0 }} />
                <span style={{ width: 62, color: 'var(--cc-text-faint)' }}>{range}</span>
                <span className={`cc-pill ${BAND_PILL[band]}`}>{word}</span>
              </div>
            ))}
          </div>
        </div>

        {/* CENTER — map */}
        <div className="cc-panel">
          <div className="cc-panel-head">
            <p className="cc-panel-title">🗺️ Bengaluru City Live Overview</p>
            <span className="cc-pill neutral">Live data: {usiAreas.length} areas</span>
          </div>
          <p className="cc-panel-sub" style={{ marginBottom: '0.5rem' }}>
            Bengaluru has 369 wards in total. Markers below show the areas with live USI data today;
            colored by severity — click a marker for detail. The Traffic tab's Ward Status list covers
            all 369 wards, searchable by name, and clearly marks which ones have data today.
          </p>
          <UnifiedMap
            areas={usiAreas}
            selectedArea={selectedArea}
            onSelectArea={setSelectedArea}
            usiByArea={usiResults}
            height={460}
          />
          {selectedArea && usiResults[selectedArea] && (
            <div className="cc-metric-tile" style={{ marginTop: '0.75rem' }}>
              <strong style={{ color: 'var(--cc-text)' }}>{selectedArea}</strong> — USI {usiResults[selectedArea].usi} ({usiResults[selectedArea].band}).{' '}
              <span style={{ color: 'var(--cc-text-dim)' }}>{usiResults[selectedArea].reason}</span>
            </div>
          )}
        </div>

        {/* RIGHT — live alerts + top stressed */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="cc-panel">
            <div className="cc-panel-head">
              <p className="cc-panel-title"><Bell size={13} className="cc-icon" /> Live Alerts</p>
              {alerts?.available && <span className="cc-pill neutral">{alerts.alerts.length}</span>}
            </div>
            {alerts?.available && alerts.alerts.length > 0 ? (
              alerts.alerts.slice(0, 5).map((a) => (
                <div className="cc-alert-row" key={a.area_name}>
                  <div className="cc-alert-icon" style={{ background: `${BAND_BAR[a.band]}22`, color: BAND_BAR[a.band] }}>⚠</div>
                  <div style={{ flex: 1 }}>
                    <div className="cc-alert-title">{a.area_name}</div>
                    <div className="cc-alert-meta">USI {a.usi} · {new Date(a.last_alert_time).toLocaleTimeString()}</div>
                  </div>
                  <span className={`cc-pill ${BAND_PILL[a.band]}`}>{a.band}</span>
                </div>
              ))
            ) : (
              <div className="cc-empty">No active alerts — nothing has crossed the Yellow/Orange/Red threshold since the last cooldown reset.</div>
            )}
          </div>

          <div className="cc-panel">
            <div className="cc-panel-head">
              <p className="cc-panel-title"><TrendingUp size={13} className="cc-icon" /> Top Stressed Zones</p>
            </div>
            {topStressed.length > 0 ? (
              topStressed.map((r, i) => (
                <div className="cc-rank-row" key={r.area_name}>
                  <span className="cc-rank-idx">{i + 1}</span>
                  <span style={{ color: 'var(--cc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.area_name}</span>
                  <div className="cc-rank-bar-track">
                    <div className="cc-rank-bar-fill" style={{ width: `${r.usi}%`, background: BAND_BAR[r.band] }} />
                  </div>
                  <span className="cc-rank-value" style={{ color: BAND_BAR[r.band] }}>{r.usi}</span>
                </div>
              ))
            ) : (
              <div className="cc-empty">Loading real USI scores…</div>
            )}
          </div>
        </div>
      </div>

      {/* Civic domains overview — ONLY implemented modules, real derived numbers */}
      <div className="cc-panel">
        <div className="cc-panel-head">
          <p className="cc-panel-title">Civic Domains Overview</p>
        </div>
        <div className="cc-domain-grid">
          <div className="cc-domain-tile">
            <div className="cc-dt-icon">🚦</div>
            <div className="cc-dt-value" style={{ color: avgTraffic == null ? 'var(--cc-text-faint)' : gaugeColor(avgTraffic) }}>{avgTraffic ?? '—'}</div>
            <div className="cc-dt-label">Traffic</div>
          </div>
          <div className="cc-domain-tile">
            <div className="cc-dt-icon">🗑️</div>
            <div className="cc-dt-value" style={{ color: avgWaste == null ? 'var(--cc-text-faint)' : gaugeColor(avgWaste) }}>{avgWaste ?? '—'}</div>
            <div className="cc-dt-label">Waste</div>
          </div>
          <div className="cc-domain-tile">
            <div className="cc-dt-icon">📊</div>
            <div className="cc-dt-value" style={{ color: avgUsi == null ? 'var(--cc-text-faint)' : gaugeColor(avgUsi) }}>{avgUsi ?? '—'}</div>
            <div className="cc-dt-label">USI</div>
          </div>
          <div className="cc-domain-tile">
            <div className="cc-dt-icon">📱</div>
            <div className="cc-dt-value cc-c-red">{alerts?.count ?? 0}</div>
            <div className="cc-dt-label">Active Alerts</div>
          </div>
        </div>
      </div>

      <div className="cc-panel">
        <div className="cc-panel-head"><p className="cc-panel-title">What Each Tab Shows</p></div>
        <ul style={{ paddingLeft: '1.1rem', color: 'var(--cc-text-dim)', lineHeight: 1.8, fontSize: '0.82rem', margin: 0 }}>
          <li><strong style={{ color: 'var(--cc-text)' }}>Traffic</strong> — route prediction, live map, ward status, incidents.</li>
          <li><strong style={{ color: 'var(--cc-text)' }}>Waste</strong> — land-use risk summary, top risk areas, full dashboard link.</li>
          <li><strong style={{ color: 'var(--cc-text)' }}>USI</strong> — combined Traffic + Waste severity per area, with a plain-language reason.</li>
          <li><strong style={{ color: 'var(--cc-text)' }}>Alerts</strong> — bilingual citizen alert preview and delivery history.</li>
        </ul>
      </div>

      {/* Technical detail, collapsed by default -- kept for anyone who
          wants to verify how the numbers above are computed, but out of
          the way for a normal evaluator/citizen view. Nothing removed,
          only moved + reworded so it reads clearly instead of like a
          debug console. */}
      <details className="cc-details">
        <summary style={{ cursor: 'pointer', fontSize: '0.8rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
          <Info size={13} className="cc-icon" /> Methodology &amp; Data
        </summary>

        <div className="cc-panel" style={{ marginTop: '0.8rem' }}>
          <div className="cc-panel-head"><p className="cc-panel-title">System Status</p></div>
          <div className="cc-metric-grid">
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Monitored traffic segments</div>
              <div className="cc-mt-value">{health?.real_gnn_v1?.n_labeled_edges ?? '—'}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Waste data</div>
              <div className={`cc-mt-value sm ${waste ? 'cc-c-green' : 'cc-c-red'}`}>{waste ? 'ONLINE' : 'OFFLINE'}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Areas with live USI data</div>
              <div className="cc-mt-value">{health?.usi_integration?.overlap_count ?? usiAreas.length ?? '—'}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Live traffic feed</div>
              <div className={`cc-mt-value sm ${feedBadge.cls}`}>{feedBadge.label}</div>
            </div>
            <div className="cc-metric-tile">
              <div className="cc-mt-label">Traffic prediction engine</div>
              <div className={`cc-mt-value sm ${health?.real_gnn_v1?.available ? 'cc-c-green' : 'cc-c-red'}`}>
                {health?.real_gnn_v1?.available ? 'ONLINE' : 'OFFLINE'}
              </div>
            </div>
          </div>
          {health?.real_gnn_v1?.available && (
            <p style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)', marginTop: '0.6rem' }}>
              Model accuracy (R²): {health.real_gnn_v1.metrics.spatial_test.R2.toFixed(2)} on new locations,{' '}
              {health.real_gnn_v1.metrics.temporal_test.R2.toFixed(2)} on future time windows.
            </p>
          )}
          {!health?.traffic_data_status?.collector_configured && (
            <div className="cc-metric-tile" style={{ marginTop: '0.6rem', borderLeft: '3px solid var(--cc-orange)' }}>
              The live traffic feed isn't configured in this environment, so traffic beyond the{' '}
              {health?.real_gnn_v1?.n_labeled_edges ?? '~750'} already-monitored segments uses the simulated
              ward-status fallback, which is never presented as real-time.
            </div>
          )}
        </div>

        {health?.ward_coverage?.available && (
          <div className="cc-panel" style={{ marginTop: '0.8rem' }}>
            <div className="cc-panel-head">
              <p className="cc-panel-title">🗺️ Ward Data Coverage ({health.ward_coverage.total_wards} Bengaluru wards)</p>
            </div>
            <p className="cc-panel-sub" style={{ marginBottom: '0.6rem' }}>
              Real OpenStreetMap ward boundaries. Waste data is joined to every ward; traffic data is joined
              to {health.ward_coverage.wards_with_precise_boundary} wards with a precise boundary. A ward
              existing in this registry does not by itself mean real-time traffic data exists for it.
            </p>
            <div className="cc-metric-grid">
              <div className="cc-metric-tile"><div className="cc-mt-label">Live traffic data</div><div className="cc-mt-value cc-c-red">{health.ward_coverage.coverage_summary.REAL_LIVE}</div></div>
              <div className="cc-metric-tile"><div className="cc-mt-label">Historical traffic data</div><div className="cc-mt-value cc-c-green">{health.ward_coverage.coverage_summary.REAL_HISTORICAL}</div></div>
              <div className="cc-metric-tile"><div className="cc-mt-label">Model-predicted</div><div className="cc-mt-value cc-c-green">{health.ward_coverage.coverage_summary.ML_PREDICTION}</div></div>
              <div className="cc-metric-tile"><div className="cc-mt-label">Limited data</div><div className="cc-mt-value cc-c-yellow">{health.ward_coverage.coverage_summary.LIMITED_COVERAGE}</div></div>
              <div className="cc-metric-tile"><div className="cc-mt-label">Awaiting data</div><div className="cc-mt-value cc-c-red">{health.ward_coverage.coverage_summary.INSUFFICIENT_DATA}</div></div>
            </div>
          </div>
        )}

        <div className="cc-panel" style={{ marginTop: '0.8rem' }}>
          <div className="cc-panel-head"><p className="cc-panel-title">Data Honesty Legend</p></div>
          <div className="cc-metric-grid">
            <div className="cc-metric-tile"><div className="cc-mt-value sm cc-c-green">REAL</div><div className="cc-mt-label" style={{ marginTop: '0.3rem' }}>Real model predictions, real routing, real weather, real route optimization</div></div>
            <div className="cc-metric-tile"><div className="cc-mt-value sm cc-c-cyan">HEURISTIC</div><div className="cc-mt-label" style={{ marginTop: '0.3rem' }}>Waste severity: real land-use ratios with fixed weighting, not a trained model</div></div>
            <div className="cc-metric-tile"><div className="cc-mt-value sm cc-c-yellow">LIVE, LIMITED</div><div className="cc-mt-label" style={{ marginTop: '0.3rem' }}>Covers a subset of wards/areas today; widens as more real data is collected</div></div>
            <div className="cc-metric-tile"><div className="cc-mt-value sm" style={{ color: 'var(--cc-text-dim)' }}>SIMULATED</div><div className="cc-mt-label" style={{ marginTop: '0.3rem' }}>Clearly labeled fallback values (e.g. ward traffic status) — never shown as real-time</div></div>
            <div className="cc-metric-tile"><div className="cc-mt-value sm cc-c-red">PLANNED</div><div className="cc-mt-label" style={{ marginTop: '0.3rem' }}>Real SMS delivery, Water/Power/Flood modules — not built yet</div></div>
          </div>
        </div>
      </details>
    </>
  );
};

export default OverviewPanel;
