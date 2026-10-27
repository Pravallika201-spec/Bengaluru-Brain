import React, { useState, useEffect } from 'react';
import { AlertTriangle, Car, Construction, TreePine, Clock } from 'lucide-react';

// Citizen-facing live incident list. Data comes from the same real
// /api/incident/list endpoint as before -- UNCHANGED. The only things
// changed here are presentation: (1) visual system migrated onto the
// shared cc- Control Center classes instead of the old legacy CSS, and
// (2) the developer/demo controls ("+ Demo Incident", "Clear All",
// "Auto ON/OFF" toggle) have been removed from this normal user-facing
// view -- they were testing aids (addDemoIncident/clearIncidents inject
// or wipe fake data via /api/incident/add and /api/incident/clear) that
// have no place on a production citizen dashboard. The functions and the
// auto-refresh behavior itself are kept -- auto-refresh now simply always
// runs (every 30s) instead of being a user-facing toggle, and the
// add/clear helper functions remain defined (unused by the UI, not
// deleted) in case a future admin/testing view needs them again.
const IncidentsPanel = ({ incidents }) => {
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [localIncidents, setLocalIncidents] = useState([]);

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(() => {
      fetchIncidents();
      setLastRefresh(new Date());
    }, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchIncidents = async () => {
    try {
      const response = await fetch('/api/incident/list');
      const data = await response.json();
      if (data.success) {
        setLocalIncidents(data.incidents);
      }
    } catch (error) {
      console.error('Failed to fetch incidents:', error);
    }
  };

  // Kept intentionally (not deleted) for a future admin/testing surface --
  // no longer wired to any button in this citizen-facing view.
  // eslint-disable-next-line no-unused-vars
  const addDemoIncident = async () => {
    try {
      const response = await fetch('/api/incident/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'accident',
          location: 'Hebbal',
          severity: 'high',
          description: 'Demo accident for testing',
          impact_min: 20
        })
      });
      const data = await response.json();
      if (data.success) {
        fetchIncidents();
      }
    } catch (error) {
      console.error('Failed to add incident:', error);
    }
  };

  // eslint-disable-next-line no-unused-vars
  const clearIncidents = async () => {
    try {
      const response = await fetch('/api/incident/clear', {
        method: 'POST'
      });
      const data = await response.json();
      if (data.success) {
        fetchIncidents();
      }
    } catch (error) {
      console.error('Failed to clear incidents:', error);
    }
  };

  const displayIncidents = localIncidents.length > 0 ? localIncidents : incidents;

  const getIncidentIcon = (type) => {
    switch (type) {
      case 'ACCIDENT':
        return <Car size={16} />;
      case 'ROAD_WORK':
        return <Construction size={16} />;
      case 'TREE_FALL':
        return <TreePine size={16} />;
      case 'VEHICLE_BREAKDOWN':
        return <AlertTriangle size={16} />;
      default:
        return <AlertTriangle size={16} />;
    }
  };

  const SEVERITY_PILL = { LOW: 'low', MEDIUM: 'medium', HIGH: 'high', CRITICAL: 'critical' };
  const SEVERITY_COLOR = {
    LOW: 'var(--cc-green)', MEDIUM: 'var(--cc-yellow)', HIGH: 'var(--cc-orange)', CRITICAL: 'var(--cc-red)',
  };

  const getTimeAgo = (timestamp) => {
    const now = new Date();
    const incidentTime = new Date(timestamp);
    const diffMs = now - incidentTime;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const sortedIncidents = [...displayIncidents].sort((a, b) => {
    const severityOrder = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, severe: 4, high: 3, moderate: 2, low: 1 };
    const aSeverity = severityOrder[a.severity] || 0;
    const bSeverity = severityOrder[b.severity] || 0;

    if (aSeverity !== bSeverity) {
      return bSeverity - aSeverity;
    }

    return new Date(b.created_at || b.reported_at) - new Date(a.created_at || a.reported_at);
  });

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title"><AlertTriangle size={13} className="cc-icon" /> Live Incident Status</p>
        <span style={{ fontSize: '0.7rem', color: 'var(--cc-text-faint)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          <Clock size={11} /> {lastRefresh.toLocaleTimeString()}
        </span>
      </div>

      {displayIncidents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '1.4rem 1rem' }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%', border: '2px solid var(--cc-green)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 0.8rem',
            color: 'var(--cc-green)', fontSize: '1.4rem',
          }}>
            ✓
          </div>
          <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--cc-text)', marginBottom: '0.3rem' }}>
            NO UNEXPECTED TRAFFIC DISRUPTIONS
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--cc-text-dim)' }}>
            Traffic conditions are currently within the expected range.
          </div>
        </div>
      ) : (
        <div>
          {sortedIncidents.map((incident) => (
            <div className="cc-alert-row" key={incident.id}>
              <div className="cc-alert-icon" style={{ background: `${SEVERITY_COLOR[incident.severity] || 'var(--cc-text-faint)'}22`, color: SEVERITY_COLOR[incident.severity] || 'var(--cc-text-dim)' }}>
                {getIncidentIcon(incident.type)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="cc-alert-title">{incident.description || incident.location}</div>
                <div className="cc-alert-meta">
                  +{incident.impact_min} min impact · {getTimeAgo(incident.created_at)}
                </div>
              </div>
              <span className={`cc-pill ${SEVERITY_PILL[incident.severity] || 'neutral'}`}>{incident.severity}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default IncidentsPanel;
