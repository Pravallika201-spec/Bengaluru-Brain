import React, { useState, useEffect } from 'react';
import { Filter, Grid, TrendingUp } from 'lucide-react';

const WardStressGrid = ({ wardStress }) => {
  const [filter, setFilter] = useState('all');
  const [filteredWards, setFilteredWards] = useState(wardStress);

  useEffect(() => {
    filterWards();
  }, [filter, wardStress]);

  const filterWards = () => {
    let filtered = [...wardStress];
    
    switch (filter) {
      case 'red':
        filtered = filtered.filter(ward => ward.status === 'CRITICAL');
        break;
      case 'orange':
        filtered = filtered.filter(ward => ward.status === 'HIGH');
        break;
      case 'yellow':
        filtered = filtered.filter(ward => ward.status === 'MEDIUM');
        break;
      case 'green':
        filtered = filtered.filter(ward => ward.status === 'LOW');
        break;
      case 'it-zones':
        filtered = filtered.filter(ward => ward.is_it_zone);
        break;
      default:
        // Show all
        break;
    }
    
    // Sort by traffic score (highest first)
    filtered.sort((a, b) => b.traffic_score - a.traffic_score);
    
    setFilteredWards(filtered);
  };

  const getStatusColor = (status) => {
    switch (status) {
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

  const getStatusIcon = (status) => {
    switch (status) {
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

  const getScoreColor = (score) => {
    if (score >= 90) return 'traffic-critical';
    if (score >= 70) return 'traffic-high';
    if (score >= 40) return 'traffic-medium';
    return 'traffic-low';
  };

  return (
    <div className="ward-stress-grid">
      <div className="grid-header">
        <div className="header-title">
          <Grid size={20} />
          <h3>🏛️ Ward Stress Monitor</h3>
        </div>
        
        <div className="filter-controls">
          <div className="filter-buttons">
            <button
              onClick={() => setFilter('all')}
              className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
            >
              All ({wardStress.length})
            </button>
            <button
              onClick={() => setFilter('red')}
              className={`filter-btn ${filter === 'red' ? 'active' : ''}`}
            >
              🔴 Red ({wardStress.filter(w => w.status === 'CRITICAL').length})
            </button>
            <button
              onClick={() => setFilter('orange')}
              className={`filter-btn ${filter === 'orange' ? 'active' : ''}`}
            >
              🟠 Orange ({wardStress.filter(w => w.status === 'HIGH').length})
            </button>
            <button
              onClick={() => setFilter('it-zones')}
              className={`filter-btn ${filter === 'it-zones' ? 'active' : ''}`}
            >
              🏢 IT Zones ({wardStress.filter(w => w.is_it_zone).length})
            </button>
          </div>
        </div>
      </div>

      <div className="wards-grid">
        {filteredWards.slice(0, 30).map((ward) => (
          <div key={ward.ward_id} className={`ward-card ${getStatusColor(ward.status)}`}>
            <div className="ward-header">
              <div className="ward-info">
                <div className="ward-name">
                  {ward.ward_name || `Ward ${ward.ward_id}`}
                </div>
                <div className="ward-id">#{ward.ward_id}</div>
              </div>
              <div className="ward-status">
                {getStatusIcon(ward.status)}
              </div>
            </div>
            
            <div className="ward-metrics">
              <div className={`traffic-score ${getScoreColor(ward.traffic_score)}`}>
                {ward.traffic_score}
              </div>
              <div className="score-label">Traffic Score</div>
            </div>
            
            {ward.is_it_zone && (
              <div className="it-zone-badge">
                🏢 IT Zone
              </div>
            )}
            
            {ward.is_major_corridor && (
              <div className="corridor-badge">
                🛣️ Major Corridor
              </div>
            )}
          </div>
        ))}
      </div>

      {filteredWards.length === 0 && (
        <div className="no-results">
          <Filter size={48} />
          <p>No wards found for the selected filter</p>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid-summary">
        <div className="summary-item">
          <div className="summary-label">Total Wards</div>
          <div className="summary-value">{filteredWards.length}</div>
        </div>
        <div className="summary-item">
          <div className="summary-label">Critical</div>
          <div className="summary-value traffic-critical">
            {filteredWards.filter(w => w.status === 'CRITICAL').length}
          </div>
        </div>
        <div className="summary-item">
          <div className="summary-label">High</div>
          <div className="summary-value traffic-high">
            {filteredWards.filter(w => w.status === 'HIGH').length}
          </div>
        </div>
        <div className="summary-item">
          <div className="summary-label">Avg Score</div>
          <div className="summary-value">
            {filteredWards.length > 0 
              ? Math.round(filteredWards.reduce((sum, w) => sum + w.traffic_score, 0) / filteredWards.length)
              : 0
            }
          </div>
        </div>
      </div>
    </div>
  );
};

export default WardStressGrid;
