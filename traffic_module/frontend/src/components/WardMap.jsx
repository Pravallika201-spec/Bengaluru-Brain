import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import { Icon, divIcon } from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix Leaflet default icon issue
delete Icon.Default.prototype._getIconUrl;
Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const WardMap = ({ locations, wardStress, prediction }) => {
  const [mapCenter] = useState([12.9716, 77.5946]); // Bengaluru center
  const [mapZoom] = useState(11);
  const routePolylineRef = useRef(null);

  // Get ward stress color
  const getWardColor = (wardId) => {
    const ward = wardStress.find(w => w.ward_id === wardId);
    if (!ward) return '#475569';
    
    switch (ward.status) {
      case 'LOW':
        return '#00FF00';
      case 'MEDIUM':
        return '#FFD700';
      case 'HIGH':
        return '#FF6B35';
      case 'CRITICAL':
        return '#FF3131';
      default:
        return '#475569';
    }
  };

  // Create custom icon for location markers
  const createLocationIcon = (location, stress) => {
    const color = getWardColor(location.ward);
    
    return divIcon({
      className: 'custom-marker',
      html: `
        <div style="
          background: ${color};
          width: 20px;
          height: 20px;
          border-radius: 50%;
          border: 2px solid #ffffff;
          box-shadow: 0 2px 4px rgba(0,0,0,0.3);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          font-weight: bold;
          color: white;
        ">
          ${location.it_zone ? '🏢' : '📍'}
        </div>
      `,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
  };

  
  // Get route color based on traffic status
  const getRouteColor = () => {
    if (!prediction) return '#00D4FF';
    
    switch (prediction.status.toLowerCase()) {
      case 'clear':
      case 'low':
        return '#00FF00';
      case 'moderate':
        return '#FFD700';
      case 'high':
        return '#FF6B35';
      case 'critical':
        return '#FF3131';
      default:
        return '#00D4FF';
    }
  };

  // Get route coordinates for prediction
  const getRouteCoordinates = () => {
    if (!prediction || !prediction.path_coords) return [];
    
    return prediction.path_coords.map(coord => [coord.lat, coord.lon]);
  };

  // Get source and destination markers
  const getSourceDestinationMarkers = () => {
    if (!prediction) return [];
    
    const markers = [];
    
    if (prediction.src_coords) {
      markers.push({
        position: [prediction.src_coords.lat, prediction.src_coords.lon],
        type: 'source',
        name: prediction.source
      });
    }
    
    if (prediction.dst_coords) {
      markers.push({
        position: [prediction.dst_coords.lat, prediction.dst_coords.lon],
        type: 'destination',
        name: prediction.destination
      });
    }
    
    return markers;
  };

  return (
    <div className="ward-map">
      <div className="map-header">
        <h3>🗺️ Bengaluru Traffic Map</h3>
        <div className="map-legend">
          <div className="legend-item">
            <div className="legend-color" style={{ background: '#00FF00' }}></div>
            <span>Low</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ background: '#FFD700' }}></div>
            <span>Medium</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ background: '#FF6B35' }}></div>
            <span>High</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ background: '#FF3131' }}></div>
            <span>Critical</span>
          </div>
        </div>
      </div>
      
      <div className="map-container">
        <MapContainer
          center={mapCenter}
          zoom={mapZoom}
          style={{ height: '400px', width: '100%', borderRadius: '8px' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {/* Source and destination markers */}
          {getSourceDestinationMarkers().map((marker, index) => (
            <Marker
              key={`${marker.type}-${index}`}
              position={marker.position}
              icon={divIcon({
                className: 'custom-marker',
                html: `
                  <div style="
                    background: ${marker.type === 'source' ? '#00FF00' : '#FF3131'};
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    border: 2px solid #ffffff;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 10px;
                    font-weight: bold;
                    color: white;
                  ">
                    ${marker.type === 'source' ? 'S' : 'D'}
                  </div>
                `,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
              })}
            >
              <Popup>
                <div className="popup-content">
                  <h4>{marker.name}</h4>
                  <p>Type: {marker.type === 'source' ? 'Source' : 'Destination'}</p>
                </div>
              </Popup>
            </Marker>
          ))}
          
          {/* Route polyline */}
          {prediction && getRouteCoordinates().length > 0 && (
            <Polyline
              positions={getRouteCoordinates()}
              color={getRouteColor()}
              weight={4}
              opacity={0.8}
              dashArray="10, 5"
            />
          )}
        </MapContainer>
      </div>
      
      {/* Map Info */}
      <div className="map-info">
        <div className="info-item">
          <span className="info-label">📍 Locations:</span>
          <span className="info-value">{locations.length}</span>
        </div>
        <div className="info-item">
          <span className="info-label">🏢 IT Zones:</span>
          <span className="info-value">{locations.filter(loc => loc.it_zone).length}</span>
        </div>
        {prediction && (
          <div className="info-item">
            <span className="info-label">🚦 Route Status:</span>
            <span className={`info-value ${getStatusColor(prediction.current_status)}`}>
              {prediction.current_status}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

// Helper function to get status color
const getStatusColor = (status) => {
  switch (status.toLowerCase()) {
    case 'low':
      return 'traffic-low';
    case 'medium':
      return 'traffic-medium';
    case 'high':
      return 'traffic-high';
    case 'critical':
      return 'traffic-critical';
    default:
      return 'traffic-medium';
  }
};

export default WardMap;
