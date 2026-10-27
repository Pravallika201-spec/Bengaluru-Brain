import React from 'react';
import { Bell } from 'lucide-react';
import CurrentAreaLocator from './UsiLocationAlerts';
import AreaAlerts from './AreaAlerts';

// Main "Alerts" navigation tab -- deliberately compact and
// location-focused. The ONLY content here is the one combined
// Traffic+Waste status/alert card (AreaAlerts) for the SAME shared
// `selectedArea` state the USI page uses (passed down from App.js,
// same prop App.js already hands UsiPanel), plus the same
// CurrentAreaLocator used everywhere else, so there is exactly one
// location system and one selected-area source of truth -- never a
// second independent one for this tab. Searching or selecting a new
// area on the USI page updates this tab automatically, since both
// read the same selectedArea/onSelectArea from App.js.
//
// This page intentionally does NOT fetch or display /api/alerts/active
// (the city-wide "every area currently alerting" list) or the separate
// road-level traffic-incident list -- a citizen should see the status of
// THEIR area, not a technical city-wide feed. Nothing backend-side is
// removed (those endpoints and the data behind them are untouched); this
// page simply no longer renders them.
const AlertsPanel = ({ selectedArea, onSelectArea }) => {
  return (
    <>
      <div className="cc-hero">
        <div>
          <h2><Bell size={19} /> Alerts Near You</h2>
          <p>One combined Traffic + Waste status for your current or selected area, generated from real USI data -- never fabricated to fill the dashboard.</p>
        </div>
      </div>

      {/* If nothing is selected yet (e.g. the person opened Alerts first,
          without visiting USI), automatically attempt current-location
          detection right away -- autoRequestOnMount actively calls the
          same requestLocation() a click would, rather than only checking
          for already-granted permission, since this page's whole design
          is "use my location automatically". Same shared component and
          same selectedArea/onSelectArea as the USI page -- never a second
          location system. Never fires once an area is already selected
          (via USI/search), and this panel disappears the moment one is --
          the current selected area always wins over passive detection. */}
      {!selectedArea && (
        <CurrentAreaLocator selectedArea={selectedArea} onSelectArea={onSelectArea} autoRequestOnMount />
      )}

      {selectedArea && (
        <p style={{ fontSize: '0.82rem', color: 'var(--cc-text-dim)', margin: '0 0 0.8rem' }}>
          📍 Current area: <strong style={{ color: 'var(--cc-text)' }}>{selectedArea}</strong>
        </p>
      )}

      <AreaAlerts selectedArea={selectedArea} headingWord="Alert" />
    </>
  );
};

export default AlertsPanel;
