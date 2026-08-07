import React, { useState, useEffect } from 'react';
import { AlertTriangle, Car, Construction, TreePine, Clock, RefreshCw } from 'lucide-react';

const IncidentsPanel = ({ incidents }) => {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        setLastRefresh(new Date());
      }, 30000); // Refresh every 30 seconds
      
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const getIncidentIcon = (type) => {
    switch (type) {
      case 'ACCIDENT':
        return <Car size={20} />;
      case 'ROAD_WORK':
        return <Construction size={20} />;
      case 'TREE_FALL':
        return <TreePine size={20} />;
      case 'VEHICLE_BREAKDOWN':
        return <AlertTriangle size={20} />;
      default:
        return <AlertTriangle size={20} />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'LOW':
        return 'status-green';
      case 'MEDIUM':
        return 'status-yellow';
      case 'HIGH':
        return 'status-orange';
      case 'CRITICAL':
        return 'status-red';
      default:
        return 'status-yellow';
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'LOW':
        return '🟢';
      case 'MEDIUM':
        return '🟡';
      case 'HIGH':
        return '🟠';
      case 'CRITICAL':
        return '🔴';
      default:
        return '⚪';
    }
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

  const sortedIncidents = [...incidents].sort((a, b) => {
    // Sort by severity first, then by time
    const severityOrder = { 'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
    const aSeverity = severityOrder[a.severity] || 0;
    const bSeverity = severityOrder[b.severity] || 0;
    
    if (aSeverity !== bSeverity) {
      return bSeverity - aSeverity;
    }
    
    return new Date(b.reported_at) - new Date(a.reported_at);
  });

  return (
    <div className="incidents-panel">
      <div className="incidents-header">
        <div className="header-title">
          <AlertTriangle size={20} />
          <h3>🚨 Live Incidents</h3>
        </div>
        
        <div className="incidents-controls">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`refresh-toggle ${autoRefresh ? 'active' : ''}`}
          >
            <RefreshCw size={16} />
            Auto {autoRefresh ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      <div className="incidents-list">
        {sortedIncidents.length === 0 ? (
          <div className="no-incidents">
            <div className="no-incidents-icon">✅</div>
            <p>No active incidents</p>
            <small>Clear traffic conditions</small>
          </div>
        ) : (
          sortedIncidents.map((incident) => (
            <div key={incident.id} className={`incident-card ${getSeverityColor(incident.severity)}`}>
              <div className="incident-header">
                <div className="incident-type">
                  {getIncidentIcon(incident.type)}
                  <span>{incident.type}</span>
                </div>
                <div className="incident-severity">
                  {getSeverityIcon(incident.severity)}
                  <span>{incident.severity}</span>
                </div>
              </div>
              
              <div className="incident-details">
                <div className="incident-location">
                  📍 {incident.location}
                </div>
                <div className="incident-meta">
                  <span className="incident-ward">Ward {incident.ward}</span>
                  <span className="incident-time">
                    <Clock size={12} />
                    {getTimeAgo(incident.reported_at)}
                  </span>
                </div>
              </div>
              
              <div className="incident-coords">
                <small>
                  {incident.lat.toFixed(4)}, {incident.lon.toFixed(4)}
                </small>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Incidents Summary */}
      {incidents.length > 0 && (
        <div className="incidents-summary">
          <div className="summary-stats">
            <div className="stat-item">
              <div className="stat-label">Active</div>
              <div className="stat-value">{incidents.length}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Critical</div>
              <div className="stat-value traffic-critical">
                {incidents.filter(i => i.severity === 'CRITICAL').length}
              </div>
            </div>
            <div className="stat-item">
              <div className="stat-label">High</div>
              <div className="stat-value traffic-high">
                {incidents.filter(i => i.severity === 'HIGH').length}
              </div>
            </div>
          </div>
          
          <div className="last-refresh">
            <small>
              <Clock size={12} />
              Last: {lastRefresh.toLocaleTimeString()}
            </small>
          </div>
        </div>
      )}
    </div>
  );
};

export default IncidentsPanel;
