import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import { divIcon } from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Dedicated Source → Destination route map for the Traffic page (separate
// from the existing citywide "Bengaluru Traffic Map" below it, which plots
// all 25 known locations + ward stress). This one exists only to show the
// actual predicted route clearly: real OSRM route geometry, real source/
// destination markers, colored by the route's real overall traffic band.
//
// Honesty note: the backend's `real_gnn_signal.matched_segments` (up to 5
// nearby monitored road segments) carries real per-segment speeds, but NOT
// their position along the route polyline — the backend matches them by
// proximity only, sorted by distance, not by path order. Coloring
// individual pieces of the line by those segments would silently invent a
// spatial correspondence the data doesn't actually contain. So this map
// colors the whole path with the route's real overall predicted band
// (the same value shown in the prediction card above), which IS accurate
// to what is known — see "Data & Model Details" for the real matched
// segments themselves.

const BAND_COLOR = {
  low: '#22c55e',
  moderate: '#eab308',
  high: '#f97316',
  severe: '#ef4444',
};

function FitToRoute({ coords }) {
  const map = useMap();
  React.useEffect(() => {
    if (coords && coords.length > 1) {
      map.fitBounds(coords, { padding: [32, 32] });
    }
  }, [map, coords]);
  return null;
}

const pinIcon = (color, label) => divIcon({
  className: 'route-map-pin',
  html: `
    <div style="
      background: ${color};
      width: 26px; height: 26px;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      border: 2px solid #ffffff;
      box-shadow: 0 2px 6px rgba(0,0,0,0.45);
      display: flex; align-items: center; justify-content: center;
    ">
      <span style="transform: rotate(45deg); color: #0b1120; font-weight: 800; font-size: 11px;">${label}</span>
    </div>
  `,
  iconSize: [26, 26],
  iconAnchor: [13, 26],
  popupAnchor: [0, -26],
});

const RouteMap = ({ prediction }) => {
  const routeCoords = prediction?.route_coords || [];
  const sourceCoords = prediction?.source_coords;
  const destCoords = prediction?.destination_coords;

  if (!routeCoords.length || !sourceCoords || !destCoords) return null;

  const band = (prediction.traffic || '').toLowerCase();
  const routeColor = BAND_COLOR[band] || '#00D4FF';

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title">🗺️ Route Map (Source → Destination)</p>
        <div style={{ display: 'flex', gap: '0.9rem', fontSize: '0.72rem', color: 'var(--cc-text-dim)' }}>
          <span><span style={{ color: BAND_COLOR.low }}>●</span> Low</span>
          <span><span style={{ color: BAND_COLOR.moderate }}>●</span> Medium</span>
          <span><span style={{ color: BAND_COLOR.high }}>●</span> High</span>
          <span><span style={{ color: BAND_COLOR.severe }}>●</span> Critical</span>
        </div>
      </div>

      <div className="cc-map-frame" style={{ marginTop: '0.6rem' }}>
        <MapContainer
          center={sourceCoords}
          zoom={12}
          style={{ height: '360px', width: '100%', borderRadius: '8px' }}
        >
          {/* Same free, no-key OSM tile source already used by the existing
              "Bengaluru Traffic Map" (WardMap.jsx) below — the CartoDB dark
              basemap tried here first now requires registration and was
              silently serving "API KEY REQUIRED" placeholder tiles instead
              of failing outright (found via an actual visual screenshot,
              not just a DOM/network check — the placeholder is itself a
              valid-looking 256x256 image, which is why automated checks
              missed it). */}
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <FitToRoute coords={routeCoords} />

          <Polyline
            key={`route-${prediction.source}-${prediction.destination}-${prediction.distance_km}`}
            positions={routeCoords}
            color={routeColor}
            weight={5}
            opacity={0.9}
          />

          <Marker position={sourceCoords} icon={pinIcon('#22c55e', 'S')}>
            <Popup>
              <strong>Source</strong><br />{prediction.source}
            </Popup>
          </Marker>
          <Marker position={destCoords} icon={pinIcon('#ef4444', 'D')}>
            <Popup>
              <strong>Destination</strong><br />{prediction.destination}
            </Popup>
          </Marker>
        </MapContainer>
      </div>

      <p style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: 'var(--cc-text-faint)' }}>
        Path is the real OSRM route geometry for this prediction. Line color reflects the route's overall
        predicted traffic band ({prediction.traffic || '—'}) — the same value in the card above. Real
        per-segment GNN readings (where matched) are listed under "Data &amp; Model Details", but the
        backend doesn't report their exact position along this path, so they aren't used to paint individual
        pieces of the line.
      </p>
    </div>
  );
};

export default RouteMap;
