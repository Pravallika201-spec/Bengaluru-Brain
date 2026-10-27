import React, { useEffect, useState } from 'react';

// Slim system footer — the old boxy "module grid" card was moved onto the
// Overview page itself (Civic Domains Overview tiles) to match the
// reference layout's compact single-row footer. This still pulls real
// data (last backend refresh) rather than a decorative static string.
const ModuleStatusBar = () => {
  const [lastUpdate, setLastUpdate] = useState(new Date());

  useEffect(() => {
    fetch('/api/health').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d?.timestamp) setLastUpdate(new Date(d.timestamp));
    }).catch(() => {});
  }, []);

  return (
    <footer className="cc-footer">
      <span>🕐 Updated: {lastUpdate.toLocaleTimeString()}</span>
      <span>Bengaluru Brain — Civic Intelligence Platform</span>
      <span>Bengaluru — 369 Wards</span>
    </footer>
  );
};

export default ModuleStatusBar;
