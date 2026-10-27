import React, { useState, useEffect } from 'react';
import { MapPin, Cloud, Navigation, Loader2 } from 'lucide-react';

// Geolocation error codes per the W3C spec (navigator.geolocation), used to
// give an honest, specific status message instead of one generic alert().
const GEO_ERROR_MESSAGES = {
  1: 'Location permission denied. Please allow location access in your browser and try again.',
  2: 'Your location is currently unavailable (no GPS/network signal). Please enter a location manually.',
  3: 'Getting your location timed out. Please try again or enter a location manually.',
};

const PredictionForm = ({ locations, onPredict, loading }) => {
  const [source, setSource] = useState('');
  const [destination, setDestination] = useState('');
  const [, setDatetime] = useState('');
  const [weather, setWeather] = useState('clear');
  const [userLocation, setUserLocation] = useState(null);
  // locating: null (idle) | 'requesting' | 'reverse_geocoding' | 'done' | 'error'
  const [locating, setLocating] = useState(null);
  const [locationStatus, setLocationStatus] = useState(null);

  useEffect(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    setDatetime(now.toISOString().slice(0, 16));
  }, []);

  const handlePredict = () => {
    if (!source || !destination) {
      alert('Please enter both source and destination');
      return;
    }
    if (source === destination) {
      alert('Source and destination cannot be the same');
      return;
    }
    onPredict({ source, destination, weather });
  };

  // Real "Use My Location": (1) real browser geolocation, no fabricated
  // coordinates; (2) real reverse-geocoding via the backend's
  // /api/reverse-geocode (genuine Nominatim call, same geocoder the
  // prediction pipeline itself uses); (3) honest status at every step,
  // including permission-denied / unavailable / timeout / unsupported.
  // If the resulting address doesn't match a location the prediction
  // pipeline's geocoder can resolve, this falls back to the REAL nearest
  // known location (real haversine distance, computed server-side) —
  // never a hardcoded/random landmark, and always disclosed as a fallback
  // rather than silently substituted.
  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      setLocating('error');
      setLocationStatus('Geolocation is not supported by your browser.');
      return;
    }

    setLocating('requesting');
    setLocationStatus('Getting your location…');

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setUserLocation({ lat: latitude, lon: longitude });
        setLocating('reverse_geocoding');
        setLocationStatus(`Location found (${latitude.toFixed(4)}, ${longitude.toFixed(4)}) — looking up address…`);

        try {
          const resp = await fetch(`/api/reverse-geocode?lat=${latitude}&lon=${longitude}`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();

          if (data.usable_address) {
            // Real reverse-geocoded address, shortened to "road, suburb"
            // using Nominatim's own structured components — the full
            // address (business name/house number/postcode) was verified
            // to NOT reliably round-trip through the prediction pipeline's
            // forward geocoder, this shorter form does.
            setSource(data.usable_address);
            setLocating('done');
            setLocationStatus(
              `Location found: ${data.usable_address}` +
              (data.reverse_geocoded_address ? ` (near ${data.reverse_geocoded_address})` : '')
            );
          } else if (data.nearest_known_location) {
            setSource(data.nearest_known_location);
            setLocating('done');
            setLocationStatus(
              `Could not resolve a precise address for your location — using the nearest known ` +
              `location instead: ${data.nearest_known_location} (${data.nearest_known_location_distance_km}km away).`
            );
          } else {
            setLocating('error');
            setLocationStatus('Got your coordinates, but could not resolve them to any usable location.');
          }
        } catch (e) {
          setLocating('error');
          setLocationStatus(`Got your coordinates, but the address lookup failed (${e.message}). Please enter a location manually.`);
        }
      },
      (error) => {
        setLocating('error');
        setLocationStatus(GEO_ERROR_MESSAGES[error.code] || `Unable to access your location (${error.message}).`);
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  };

  const weatherOptions = [
    { value: 'clear', label: '☀️ Clear' },
    { value: 'light_rain', label: '🌦️ Light Rain' },
    { value: 'heavy_rain', label: '🌧️ Heavy Rain' },
    { value: 'storm', label: '⛈️ Storm' },
    { value: 'fog', label: '🌫️ Fog' },
  ];

  const quickRoutes = [
    { from: 'Hebbal', to: 'Silk Board' },
    { from: 'Manyata Tech Park', to: 'Electronic City' },
    { from: 'Whitefield', to: 'MG Road' },
    { from: 'Electronic City', to: 'Whitefield' },
  ];

  const isLocating = locating === 'requesting' || locating === 'reverse_geocoding';

  return (
    <div className="cc-panel">
      <div className="cc-panel-head">
        <p className="cc-panel-title">🚦 Route Prediction</p>
        {userLocation && (
          <span className="cc-pill info">📍 {userLocation.lat.toFixed(3)}, {userLocation.lon.toFixed(3)}</span>
        )}
      </div>

      <div className="cc-route-bar">
        <div className="cc-field">
          <label><MapPin size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Source</label>
          <input
            type="text" value={source} onChange={(e) => setSource(e.target.value)}
            placeholder="e.g. Nagarbhavi" disabled={loading}
          />
        </div>
        <div className="cc-field">
          <label><Navigation size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Destination</label>
          <input
            type="text" value={destination} onChange={(e) => setDestination(e.target.value)}
            placeholder="e.g. Sarjapur Road" disabled={loading}
          />
        </div>
        <div className="cc-field">
          <label><Cloud size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Weather</label>
          <select value={weather} onChange={(e) => setWeather(e.target.value)} disabled={loading}>
            {weatherOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <button className="cc-btn-primary" onClick={handlePredict} disabled={loading || !source || !destination}>
          {loading ? 'Predicting…' : '🚀 Predict'}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
        <button
          className="cc-navlink"
          style={{ fontSize: '0.75rem', padding: '0.35rem 0.7rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          onClick={handleUseMyLocation}
          disabled={loading || isLocating}
        >
          {isLocating ? <Loader2 size={12} className="cc-spin" /> : '📍'} Use My Location
        </button>
        <span style={{ fontSize: '0.72rem', color: 'var(--cc-text-faint)', marginRight: '0.2rem' }}>Popular:</span>
        {quickRoutes.map((r, i) => (
          <button
            key={i}
            className="cc-navlink"
            style={{ fontSize: '0.75rem', padding: '0.35rem 0.7rem' }}
            onClick={() => { setSource(r.from); setDestination(r.to); }}
            disabled={loading}
          >
            {r.from} → {r.to}
          </button>
        ))}
      </div>

      {locationStatus && (
        <div
          className="cc-metric-tile"
          style={{
            marginTop: '0.65rem', fontSize: '0.78rem',
            borderLeft: `3px solid ${locating === 'error' ? 'var(--cc-red)' : locating === 'done' ? 'var(--cc-green)' : 'var(--cc-accent)'}`,
            color: 'var(--cc-text-dim)',
          }}
        >
          {locationStatus}
        </div>
      )}
    </div>
  );
};

export default PredictionForm;
