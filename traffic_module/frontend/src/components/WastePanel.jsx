import React, { useEffect, useState } from 'react';
import { Trash2, ExternalLink, CheckCircle2, AlertTriangle } from 'lucide-react';

// Waste tab now launches the friend's complete Waste Intelligence application
// (a separate Streamlit app: friend_waste/dashboard/enhanced_dashboard.py),
// started independently with its own environment:
//   D:\major project\friend_waste\.venv\Scripts\python.exe -m streamlit run
//   D:\major project\friend_waste\dashboard\enhanced_dashboard.py
// This panel does not re-implement any of its pages (Risk Map, Model
// Comparison, Land Use Profile, Optimized Routes, OR-Tools routing, Event
// Intelligence, Early Warning, Citizen Reports, ward-level info, satellite
// indices, prediction outputs) -- it only launches the real app in a new
// browser tab. If the Streamlit server isn't running yet, this panel still
// renders normally and just shows how to start it (the probe below never
// throws or blocks rendering).
const STREAMLIT_URL = 'http://localhost:8501';
const LAUNCH_COMMAND =
  'D:\\major project\\friend_waste\\.venv\\Scripts\\python.exe -m streamlit run ' +
  'D:\\major project\\friend_waste\\dashboard\\enhanced_dashboard.py';

const WASTE_FEATURES = [
  'Overview', 'Risk Map', 'Model Comparison', 'Land Use Profile',
  'Optimized Routes', 'OR-Tools Routing', 'Event Intelligence',
  'Early Warning', 'Citizen Reports', 'Ward-Level Information',
  'Satellite Indices (NDVI/NDBI/NDWI)', 'Waste Prediction Outputs',
];

// status: 'checking' | 'up' | 'unknown'
// 'unknown' (not 'down') is used on failure, because a failed fetch to a
// cross-origin localhost port can mean either "server not running" or just
// "browser blocked the probe" -- we never assert it's down, only that we
// couldn't confirm it's up, so the link is always still offered.
const WastePanel = () => {
  const [status, setStatus] = useState('checking');

  useEffect(() => {
    let cancelled = false;
    const timeout = setTimeout(() => {
      if (!cancelled) setStatus((s) => (s === 'checking' ? 'unknown' : s));
    }, 2500);

    fetch(STREAMLIT_URL, { mode: 'no-cors' })
      .then(() => {
        if (!cancelled) setStatus('up');
      })
      .catch(() => {
        if (!cancelled) setStatus('unknown');
      })
      .finally(() => clearTimeout(timeout));

    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, []);

  return (
    <>
      <div className="cc-hero">
        <div>
          <h2><Trash2 size={19} /> Waste Intelligence</h2>
          <p>
            The complete Waste Intelligence application — Risk Map, satellite NDVI/NDBI/NDWI,
            Event Intelligence, Citizen Reports, OR-Tools collection routing, and more — runs as
            its own Streamlit application with its own environment and opens in a new tab.
          </p>
        </div>
        <span className="cc-source-tag heuristic">EXTERNAL APPLICATION</span>
      </div>

      <div className="cc-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.9rem', fontSize: '0.8rem' }}>
          {status === 'checking' && (
            <span style={{ color: 'var(--cc-text-dim)' }}>Checking whether the Waste application is running…</span>
          )}
          {status === 'up' && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', color: 'var(--cc-c-green, #2e7d32)' }}>
              <CheckCircle2 size={14} /> Waste application detected at {STREAMLIT_URL}
            </span>
          )}
          {status === 'unknown' && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', color: 'var(--cc-text-dim)' }}>
              <AlertTriangle size={14} /> Could not confirm the Waste application is running yet — the link below will still open it if it is.
            </span>
          )}
        </div>

        <a
          href={STREAMLIT_URL}
          target="_blank"
          rel="noreferrer"
          className="cc-btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none', marginBottom: '1rem' }}
        >
          <ExternalLink size={14} /> Open Waste Intelligence Dashboard
        </a>

        <div className="cc-panel-head"><p className="cc-panel-title">Included in the Waste application</p></div>
        <div className="cc-metric-grid">
          {WASTE_FEATURES.map((feature) => (
            <div className="cc-metric-tile" key={feature}>
              <div className="cc-mt-label">{feature}</div>
            </div>
          ))}
        </div>

        {status === 'unknown' && (
          <details className="cc-details" style={{ marginTop: '0.9rem' }}>
            <summary style={{ cursor: 'pointer', fontSize: '0.76rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
              Technical Details
            </summary>
            <p style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', marginTop: '0.5rem' }}>
              If the link above doesn't open anything, the Waste application needs to be started first:
              <br />
              <code>{LAUNCH_COMMAND}</code>
            </p>
          </details>
        )}
      </div>
    </>
  );
};

export default WastePanel;
