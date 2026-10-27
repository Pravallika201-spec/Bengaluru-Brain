import React, { useMemo, useState } from 'react';
import { Search, LayoutGrid } from 'lucide-react';

// Compact replacement for the old citywide WardMap + WardStressGrid pair.
// Renders the SAME wardStress array App.js already fetches from the SAME
// /api/ward-stress endpoint (see App.js fetchWardStress()) -- no new
// fetch, no new fields, no randomized/generated values added here. This
// component only changes HOW the existing data is displayed (a filterable/
// searchable table instead of a citywide point-map + a wall of 30 cards).
//
// Data-honesty note (unchanged from the previous WardStressGrid.jsx):
// ward identity (id, name, IT-zone flag, major-corridor flag) is real --
// the same 369 real BBMP/OSM wards used everywhere else in this app. The
// traffic_score itself is a simulated/heuristic value (see backend/
// ward_stress.py), NOT a GNN model output, so this is deliberately titled
// "Ward Traffic Stress Monitor" rather than anything implying it is a
// live GNN prediction for all 369 wards.

const STATUS_ORDER = { CRITICAL: 3, HIGH: 2, MEDIUM: 1, LOW: 0 };
const STATUS_LABEL = { CRITICAL: 'Critical', HIGH: 'High', MEDIUM: 'Moderate', LOW: 'Low' };
const STATUS_COLOR = {
  CRITICAL: 'var(--cc-red)',
  HIGH: 'var(--cc-orange)',
  MEDIUM: 'var(--cc-yellow)',
  LOW: 'var(--cc-green)',
};
const STATUS_PILL = { CRITICAL: 'critical', HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'CRITICAL', label: 'Critical' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Moderate' },
  { id: 'LOW', label: 'Low' },
];

const WardTrafficStressMonitor = ({ wardStress = [] }) => {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const counts = useMemo(() => ({
    CRITICAL: wardStress.filter((w) => w.status === 'CRITICAL').length,
    HIGH: wardStress.filter((w) => w.status === 'HIGH').length,
    MEDIUM: wardStress.filter((w) => w.status === 'MEDIUM').length,
    LOW: wardStress.filter((w) => w.status === 'LOW').length,
  }), [wardStress]);

  const filtered = useMemo(() => {
    let rows = wardStress;
    if (filter !== 'all') rows = rows.filter((w) => w.status === filter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((w) =>
        (w.ward_name || '').toLowerCase().includes(q) || String(w.ward_id).includes(q)
      );
    }
    // Highest-stress wards first -- same ordering the previous grid used.
    return [...rows].sort((a, b) => (STATUS_ORDER[b.status] - STATUS_ORDER[a.status]) || (b.traffic_score - a.traffic_score));
  }, [wardStress, filter, search]);

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title"><LayoutGrid size={13} className="cc-icon" /> Ward Traffic Stress Monitor</p>
        <span className="cc-source-tag simulated">SIMULATED</span>
      </div>
      <p className="cc-panel-sub" style={{ marginBottom: '0.7rem' }}>
        Traffic stress across Bengaluru's 369 wards.
      </p>

      <div className="cc-ward-legend">
        <span><i style={{ background: STATUS_COLOR.LOW }} /> Low</span>
        <span><i style={{ background: STATUS_COLOR.MEDIUM }} /> Moderate</span>
        <span><i style={{ background: STATUS_COLOR.HIGH }} /> High</span>
        <span><i style={{ background: STATUS_COLOR.CRITICAL }} /> Critical</span>
      </div>

      <div className="cc-metric-grid cc-metric-grid-4" style={{ margin: '0.8rem 0' }}>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Critical</div>
          <div className="cc-mt-value cc-c-red">{counts.CRITICAL}</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">High</div>
          <div className="cc-mt-value cc-c-orange">{counts.HIGH}</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Moderate</div>
          <div className="cc-mt-value cc-c-yellow">{counts.MEDIUM}</div>
        </div>
        <div className="cc-metric-tile">
          <div className="cc-mt-label">Low</div>
          <div className="cc-mt-value cc-c-green">{counts.LOW}</div>
        </div>
      </div>

      <div className="cc-ward-toolbar">
        <div className="cc-field cc-ward-search">
          <label><Search size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Search Ward</label>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. Whitefield or 142"
          />
        </div>
        <div className="cc-ward-filters">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              className={`cc-navlink ${filter === f.id ? 'active' : ''}`}
              style={{ fontSize: '0.76rem', padding: '0.4rem 0.75rem' }}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
              {f.id !== 'all' && <span style={{ marginLeft: 5, opacity: 0.75 }}>({counts[f.id]})</span>}
            </button>
          ))}
        </div>
      </div>

      <p className="cc-panel-sub" style={{ margin: '0.6rem 0 0.4rem' }}>
        {filtered.length} of {wardStress.length || 369} wards shown
      </p>

      <div className="cc-ward-table-wrap">
        <table className="cc-table cc-ward-table">
          <thead>
            <tr>
              <th>Ward</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Stress</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((w) => (
              <tr key={w.ward_id}>
                <td>
                  <span style={{ color: 'var(--cc-text)' }}>{w.ward_name || `Ward ${w.ward_id}`}</span>
                  <span style={{ color: 'var(--cc-text-faint)', marginLeft: 6, fontSize: '0.72rem' }}>#{w.ward_id}</span>
                  {w.is_it_zone && <span title="IT Zone" style={{ marginLeft: 6 }}>🏢</span>}
                  {w.is_major_corridor && <span title="Major Corridor" style={{ marginLeft: 4 }}>🛣️</span>}
                </td>
                <td>
                  <span className={`cc-pill ${STATUS_PILL[w.status] || 'neutral'}`}>
                    {STATUS_LABEL[w.status] || w.status}
                  </span>
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--cc-font-display)', fontWeight: 700, color: STATUS_COLOR[w.status] || 'var(--cc-text-dim)' }}>
                  {w.traffic_score}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="cc-empty">No wards match this search/filter.</div>
        )}
      </div>

      <details className="cc-details" style={{ marginTop: '0.8rem' }}>
        <summary style={{ cursor: 'pointer', fontSize: '0.76rem', color: 'var(--cc-accent)', fontWeight: 700 }}>
          Methodology &amp; data basis
        </summary>
        <p style={{ marginTop: '0.5rem', fontSize: '0.76rem', color: 'var(--cc-text-faint)', lineHeight: 1.6 }}>
          Ward identity (name, id, boundary, IT-zone and major-corridor flags) is real — the same 369 real
          BBMP/OSM wards used everywhere else in this app. The stress score itself is a simulated/heuristic
          value (see backend/ward_stress.py), not a live feed and not an output of the GNN traffic model —
          it is not presented as a GNN prediction anywhere in this app.
        </p>
      </details>
    </div>
  );
};

export default WardTrafficStressMonitor;
