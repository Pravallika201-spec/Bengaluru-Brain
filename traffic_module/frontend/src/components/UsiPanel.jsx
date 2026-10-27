import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Activity, MapPin, Search } from 'lucide-react';
import UnifiedMap from './UnifiedMap';
import CurrentAreaLocator from './UsiLocationAlerts';
import AreaAlerts from './AreaAlerts';

const BAND_PILL = { Red: 'critical', Orange: 'high', Yellow: 'medium', Green: 'low', Unknown: 'neutral' };
const BAND_COLOR = { Red: 'var(--cc-red)', Orange: 'var(--cc-orange)', Yellow: 'var(--cc-yellow)', Green: 'var(--cc-green)', Unknown: 'var(--cc-text-faint)' };
// Plain-language label for the real server-computed band -- no new
// thresholds introduced, purely a display mapping of the existing value.
const BAND_WORD = { Red: 'CRITICAL', Orange: 'HIGH', Yellow: 'MODERATE', Green: 'LOW', Unknown: '—' };

// Urban Severity Index panel — the central Traffic+Waste fusion view.
// Every number shown here traces back to a real signal or an explicitly
// labeled simulated fallback; nothing is invented client-side. Band
// thresholds and alert wording are never re-derived here — both come
// straight from the existing backend (/api/usi/{area}, /api/alerts/{area}),
// which already implement the project's one real severity system
// (integration/usi_config.json: Green<=40, Yellow<=60, Orange<=80, Red>80).
//
// WARD COVERAGE: there is deliberately only ONE search control here --
// "Search Location" -- which resolves against the 24 curated named
// locations first, then the full real 369-ward registry (integration/geo/
// ward_registry.json, fetched once via /api/wards/list for matching only;
// no separate selector UI is rendered for it, per the latest UX cleanup).
// Whichever name resolves, the SAME /api/usi/{area} endpoint is called for
// it -- there is no second, richer endpoint for non-curated wards -- so
// this panel and the combined Alert card below it (which calls
// /api/alerts/{area} -> the same compute_usi()) can never disagree about
// a given area's Traffic/Waste numbers.
// A search/select never fabricates a score: when a resolved area has no
// real-or-simulated signal for a domain, that domain's tile honestly says
// so instead of inventing one (see the UNKNOWN-level checks below).
const UsiPanel = ({ selectedArea, onSelectArea }) => {
  const [coverage, setCoverage] = useState(null);
  const [areas, setAreas] = useState([]);
  const [usi, setUsi] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [searchText, setSearchText] = useState('');
  const [searchStatus, setSearchStatus] = useState(null);

  // The full real 369-ward registry (integration/geo/ward_registry.json via
  // /api/wards/list) -- static metadata only (names, ids, coordinates),
  // fast to fetch, no per-ward computation. Lets Search Location also match
  // a ward outside the 24 curated names (by name or by its real ward_id),
  // and gives the map a real centroid pin for whichever ward is selected.
  const [allWards, setAllWards] = useState([]);

  // Stable-identity set of curated names so selectedWardMarker (and any
  // other memo below) can always read the latest list without needing
  // fetchUsi/handleSearch to be recreated on every areas update.
  const curatedNamesRef = useRef(new Set());

  useEffect(() => {
    fetch('/api/usi/areas')
      .then((r) => r.json())
      .then((data) => {
        setCoverage(data.coverage);
        const loadedAreas = data.areas || [];
        setAreas(loadedAreas);
        curatedNamesRef.current = new Set(loadedAreas.map((a) => a.name.toLowerCase()));
        if (!selectedArea && loadedAreas.length > 0) {
          onSelectArea(loadedAreas[0].name);
        }
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // All 369 real wards -- static registry, not per-ward computed data, so
  // this is fast and safe to fetch in full on mount (the same pattern
  // CitizenAlertRegistration.jsx already uses for its own ward picker).
  // Used only for search matching and the map marker -- never rendered as
  // a list or selector of its own.
  useEffect(() => {
    fetch('/api/wards/list')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.available) {
          setAllWards(data.wards || []);
        }
      })
      .catch(() => {});
  }, []);

  // Fetches real USI for whatever area name was resolved -- the SAME
  // /api/usi/{area} endpoint for every area, curated or not, so this
  // panel's numbers and the Alert card's numbers always come from the
  // identical backend computation for a given area.
  const fetchUsi = useCallback((area) => {
    if (!area) return;
    setLoading(true);
    setError(null);
    fetch(`/api/usi/${encodeURIComponent(area)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setUsi)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchUsi(selectedArea);
  }, [selectedArea, fetchUsi]);

  // The ONE search control for location. Matches against the 24 curated
  // locations first (unchanged), then the full real 369-ward registry by
  // exact name, then -- if the query is purely numeric -- by a ward's real
  // ward_id. No fuzzy/partial matching and no selector list: an unmatched
  // query just explains itself honestly instead of showing a giant list.
  const handleSearch = () => {
    const q = searchText.trim();
    if (!q) return;
    const qLower = q.toLowerCase();
    setSearchStatus('searching');

    const curatedMatch = areas.find((a) => a.name.toLowerCase() === qLower);
    if (curatedMatch) {
      setSearchStatus(null);
      onSelectArea(curatedMatch.name);
      return;
    }

    const wardMatch = allWards.find((w) => (w.ward_name || '').toLowerCase() === qLower);
    if (wardMatch) {
      setSearchStatus(null);
      onSelectArea(wardMatch.ward_name);
      return;
    }

    if (/^\d+$/.test(q)) {
      const idMatch = allWards.find((w) => String(w.ward_id) === q);
      if (idMatch) {
        setSearchStatus(null);
        onSelectArea(idMatch.ward_name);
        return;
      }
    }

    setSearchStatus(`'${q}' is not a recognized Bengaluru area. Try a ward name (e.g. "Whitefield", "Doddabommasandra") or a ward ID.`);
  };

  // Real centroid marker for a selected ward outside the 24 curated
  // locations (which already get their own pin from `areas`/UnifiedMap) --
  // a real coordinate from the ward registry, never invented, shown even
  // when that ward has no USI score yet.
  const selectedWardMarker = useMemo(() => {
    if (!selectedArea) return null;
    if (curatedNamesRef.current.has(selectedArea.toLowerCase())) return null;
    const ward = allWards.find((w) => (w.ward_name || '').toLowerCase() === selectedArea.toLowerCase());
    if (!ward || ward.centroid_lat == null || ward.centroid_lon == null) return null;
    return [{
      lat: ward.centroid_lat,
      lon: ward.centroid_lon,
      label: `${ward.ward_name} (Ward #${ward.ward_id})${usi && usi.available ? ` — USI ${usi.usi ?? '—'}` : ' — data not available yet'}`,
      color: usi && usi.available ? BAND_COLOR[usi.band || 'Unknown'] : '#94A3B8',
    }];
  }, [selectedArea, allWards, usi]);

  const sourceTagClass = (source) => {
    if (source === 'REAL_GNN') return 'real';
    if (source === 'REAL_GNN_EXTRAPOLATED') return 'extrapolated';
    if (source === 'WASTE_HEURISTIC_MODEL') return 'heuristic';
    if (source === 'SIMULATED_WARD_STRESS') return 'simulated';
    return 'simulated';
  };

  const sourceTagLabel = (source) => {
    switch (source) {
      case 'REAL_GNN': return 'REAL (validated)';
      case 'REAL_GNN_EXTRAPOLATED': return 'REAL (extrapolated)';
      case 'WASTE_HEURISTIC_MODEL': return 'HEURISTIC';
      case 'SIMULATED_WARD_STRESS': return 'SIMULATED';
      case 'NO_DATA': return 'NO DATA';
      default: return source || 'UNKNOWN';
    }
  };

  const band = usi?.band || 'Unknown';

  return (
    <>
      <div className="cc-hero">
        <div>
          <h2><Activity size={19} /> Urban Severity Index</h2>
          <p>Traffic and waste signals combined into a single 0–100 severity score for each area.</p>
        </div>
      </div>

      <div className="cc-panel">
        <div className="cc-panel-head"><p className="cc-panel-title">🔎 Search Location</p></div>
        <div className="cc-route-bar" style={{ gridTemplateColumns: '1fr auto' }}>
          <div className="cc-field">
            <label><Search size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Search Bengaluru location</label>
            <input
              type="text" value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="e.g. Whitefield"
            />
          </div>
          <button className="cc-btn-primary" onClick={handleSearch}>🔍 Search</button>
        </div>
        {searchStatus && (
          <div className="cc-metric-tile" style={{ marginTop: '0.6rem', borderLeft: '3px solid var(--cc-orange)', fontSize: '0.78rem' }}>{searchStatus}</div>
        )}
      </div>

      <CurrentAreaLocator selectedArea={selectedArea} onSelectArea={onSelectArea} />

      {/* The familiar quick-location chips -- the exact same 24 curated
          locations (`areas`, from /api/usi/areas) and the exact same
          cc-navlink chip markup the project used before, just moved back
          onto the page. Clicking one calls the SAME onSelectArea the
          search box and CurrentAreaLocator already use, so USI/Traffic/
          Waste/Map/Alert/Alerts-tab all update together exactly as a
          search would -- this is a second entry point into the one
          selectedUsiArea state, never a second state of its own. */}
      {areas.length > 0 && (
        <div className="cc-panel">
          <div className="cc-panel-head"><p className="cc-panel-title">📍 Quick Locations</p></div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {areas.map((a) => (
              <button
                key={a.name}
                className={`cc-navlink ${selectedArea === a.name ? 'active' : ''}`}
                style={{ fontSize: '0.76rem', padding: '0.35rem 0.65rem' }}
                onClick={() => onSelectArea(a.name)}
              >
                {a.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="cc-2col">
        <div className="cc-panel">
          {loading && <div className="cc-empty">Loading USI…</div>}
          {error && <div className="cc-empty">Could not load USI: {error}</div>}

          {usi && usi.available && (
            <>
              <div className="cc-usi-hero">
                <div className="cc-usi-hero-score">
                  <div style={{ fontFamily: 'var(--cc-font-display)', fontSize: '3.2rem', fontWeight: 700, color: BAND_COLOR[band], lineHeight: 1 }}>
                    {usi.usi ?? '—'}
                  </div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, letterSpacing: '0.08em', color: BAND_COLOR[band], marginTop: '0.3rem' }}>
                    {BAND_WORD[band] || band}
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.55rem', flexWrap: 'wrap' }}>
                    <span className={`cc-pill ${BAND_PILL[band]}`}>{band}</span>
                    {usi.partial_data && <span className="cc-pill neutral">PARTIAL DATA</span>}
                    {usi.compounding_bonus_applied && <span className="cc-pill orange">COMPOUNDING BONUS</span>}
                  </div>
                </div>
              </div>

              <p style={{ fontSize: '0.78rem', color: 'var(--cc-text-faint)', marginBottom: '0.9rem' }}>
                Updated {new Date(usi.timestamp).toLocaleTimeString()}
              </p>

              <div className="cc-metric-tile" style={{ marginBottom: '0.9rem' }}>
                <div className="cc-mt-label">Current Urban Condition</div>
                <p style={{ color: 'var(--cc-text)', fontSize: '0.85rem', marginTop: '0.35rem', lineHeight: 1.5 }}>{usi.reason}</p>
              </div>

              <div className="cc-metric-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="cc-metric-tile">
                  <div className="cc-panel-head" style={{ marginBottom: '0.4rem' }}>
                    <span className="cc-mt-label" style={{ margin: 0 }}>Traffic Contribution</span>
                    {usi.traffic.level !== 'UNKNOWN' && (
                      <span className={`cc-source-tag ${sourceTagClass(usi.traffic.source)}`}>{sourceTagLabel(usi.traffic.source)}</span>
                    )}
                  </div>
                  {usi.traffic.level === 'UNKNOWN' ? (
                    <p style={{ color: 'var(--cc-text-dim)', fontSize: '0.82rem', marginTop: '0.35rem' }}>
                      Traffic data not available yet for this area.
                    </p>
                  ) : (
                    <>
                      <div className="cc-mt-value">{usi.traffic.score ?? '—'} <span className="cc-mt-unit">({usi.traffic.level})</span></div>
                      <p style={{ fontSize: '0.76rem', color: 'var(--cc-text-dim)', marginTop: '0.35rem' }}>{usi.traffic.detail}</p>
                    </>
                  )}
                </div>
                <div className="cc-metric-tile">
                  <div className="cc-panel-head" style={{ marginBottom: '0.4rem' }}>
                    <span className="cc-mt-label" style={{ margin: 0 }}>Waste Contribution</span>
                    {usi.waste.level !== 'UNKNOWN' && (
                      <span className={`cc-source-tag ${sourceTagClass(usi.waste.source)}`}>{sourceTagLabel(usi.waste.source)}</span>
                    )}
                  </div>
                  {usi.waste.level === 'UNKNOWN' ? (
                    <p style={{ color: 'var(--cc-text-dim)', fontSize: '0.82rem', marginTop: '0.35rem' }}>
                      Waste data not available yet for this area.
                    </p>
                  ) : (
                    <>
                      <div className="cc-mt-value">{usi.waste.score ?? '—'} <span className="cc-mt-unit">({usi.waste.level})</span></div>
                      <p style={{ fontSize: '0.76rem', color: 'var(--cc-text-dim)', marginTop: '0.35rem' }}>{usi.waste.detail}</p>
                      {usi.waste.score_breakdown_text && (
                        <div style={{ fontSize: '0.76rem', color: 'var(--cc-cyan)', marginTop: '0.5rem', background: 'rgba(34,211,238,0.08)', border: '1px solid rgba(34,211,238,0.25)', borderRadius: 6, padding: '0.4rem 0.6rem' }}>
                          {usi.waste.score_breakdown_text}
                        </div>
                      )}
                      {usi.waste.geo_match_type === 'spatial_nearest' && (
                        <p style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', marginTop: '0.35rem' }}>
                          Waste joined from nearest real area, {usi.waste.geo_match_distance_km}km away.
                        </p>
                      )}
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="cc-panel">
          <div className="cc-panel-head"><p className="cc-panel-title">🗺️ USI Map</p></div>
          <UnifiedMap
            areas={areas}
            selectedArea={selectedArea}
            onSelectArea={onSelectArea}
            usiByArea={usi && usi.available ? { [usi.area_name]: usi } : {}}
            extraMarkers={selectedWardMarker || []}
          />
        </div>
      </div>

      {/* Combined Traffic+Waste alert/status for the currently selected
          area, shown directly on the USI page itself -- reuses the exact
          same card the Alerts tab uses (same component, same
          /api/alerts/{area} call), just with page-appropriate heading
          wording. Whatever area is searched/selected/detected above
          immediately shows its own alert here too, so a citizen never has
          to re-search in the Alerts tab. */}
      <AreaAlerts selectedArea={selectedArea} headingWord="Alert" />
    </>
  );
};

export default UsiPanel;
