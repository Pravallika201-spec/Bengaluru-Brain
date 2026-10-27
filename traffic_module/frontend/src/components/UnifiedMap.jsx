import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import { divIcon } from 'leaflet';
import 'leaflet/dist/leaflet.css';

// One Bengaluru map shared by the USI and Routing views. Markers are the
// REAL curated locations from the traffic module (never fabricated
// coordinates); marker color reflects each area's real USI band once
// loaded. Kept intentionally small (currently 6 markers) rather than
// clustering machinery that would be overkill at this scale — clustering
// is worth adding once coverage grows past a few dozen areas.
const BAND_COLOR = { Green: '#00FF00', Yellow: '#FFD700', Orange: '#FF6B35', Red: '#FF3131', Unknown: '#475569' };

const UnifiedMap = ({ areas, selectedArea, onSelectArea, usiByArea = {}, extraMarkers = [], height = 420 }) => {
  const [fetchedUsi, setFetchedUsi] = useState({});

  useEffect(() => {
    let cancelled = false;
    (areas || []).forEach((area) => {
      fetch(`/api/usi/${encodeURIComponent(area.name)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!cancelled && data && data.available) {
            setFetchedUsi((prev) => ({ ...prev, [area.name]: data }));
          }
        })
        .catch(() => {});
    });
    return () => { cancelled = true; };
  }, [areas]);

  const bandFor = (name) => {
    const data = usiByArea[name] || fetchedUsi[name];
    return data ? data.band : 'Unknown';
  };
  const usiFor = (name) => {
    const data = usiByArea[name] || fetchedUsi[name];
    return data ? data.usi : null;
  };

  const icon = (color, isSelected) => divIcon({
    className: 'custom-marker',
    html: `<div style="
        background:${color}; width:${isSelected ? 26 : 20}px; height:${isSelected ? 26 : 20}px;
        border-radius:50%; border:2px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,0.4);
      "></div>`,
    iconSize: [isSelected ? 26 : 20, isSelected ? 26 : 20],
    iconAnchor: [isSelected ? 13 : 10, isSelected ? 13 : 10],
  });

  return (
    <div className="map-container cc-map-frame">
      <MapContainer center={[12.9716, 77.5946]} zoom={11} style={{ height, width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {(areas || []).map((area) => {
          const band = bandFor(area.name);
          const usi = usiFor(area.name);
          const isSelected = selectedArea === area.name;
          return (
            <Marker
              key={area.name}
              position={[area.lat, area.lon]}
              icon={icon(BAND_COLOR[band] || BAND_COLOR.Unknown, isSelected)}
              eventHandlers={{ click: () => onSelectArea && onSelectArea(area.name) }}
            >
              <Popup>
                <div>
                  <strong>{area.name}</strong> (Ward {area.ward})<br />
                  USI: {usi ?? 'loading…'} — {band}
                </div>
              </Popup>
            </Marker>
          );
        })}
        {extraMarkers.map((m, idx) => (
          <Marker
            key={`extra-${idx}`}
            position={[m.lat, m.lon]}
            icon={icon(m.color || '#00D4FF', false)}
          >
            <Popup>{m.label}</Popup>
          </Marker>
        ))}
      </MapContainer>
      {(areas || []).length > 0 && (
        <div className="map-legend" style={{ marginTop: '0.75rem' }}>
          {Object.entries(BAND_COLOR).map(([band, color]) => (
            <div className="legend-item" key={band}>
              <div className="legend-color" style={{ background: color }}></div>
              <span>{band}</span>
            </div>
          ))}
        </div>
      )}
      {(areas || []).length === 0 && extraMarkers.length > 0 && (
        <div style={{ fontSize: '0.8rem', color: '#94A3B8', marginTop: '0.5rem' }}>
          Marker colors above indicate which vehicle's route each stop belongs to.
        </div>
      )}
    </div>
  );
};

export default UnifiedMap;
