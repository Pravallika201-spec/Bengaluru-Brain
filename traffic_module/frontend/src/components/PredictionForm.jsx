import React, { useState, useEffect } from 'react';
import { MapPin, Calendar, Cloud, Navigation } from 'lucide-react';

const PredictionForm = ({ locations, onPredict, loading }) => {
  const [source, setSource] = useState('');
  const [destination, setDestination] = useState('');
  const [datetime, setDatetime] = useState('');
  const [weather, setWeather] = useState('clear');
  const [userLocation, setUserLocation] = useState(null);
  const [useMyLocation, setUseMyLocation] = useState(false);

  // Set default datetime to current time
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

    const predictionData = {
      source,
      destination,
      weather: weather
    };

    onPredict(predictionData);
  };

  const handleUseMyLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          
          // Find nearest location (simplified)
          let nearestLocation = null;
          let minDistance = Infinity;
          
          locations.forEach(loc => {
            const distance = Math.sqrt(
              Math.pow(loc.lat - latitude, 2) + 
              Math.pow(loc.lon - longitude, 2)
            );
            if (distance < minDistance) {
              minDistance = distance;
              nearestLocation = loc.name;
            }
          });
          
          if (nearestLocation) {
            setSource(nearestLocation);
            setUseMyLocation(true);
            setUserLocation({ lat: latitude, lon: longitude });
          }
        },
        (error) => {
          console.error('Geolocation error:', error);
          alert('Unable to get your location');
        }
      );
    } else {
      alert('Geolocation is not supported by your browser');
    }
  };

  const weatherOptions = [
    { value: 'clear', label: '☀️ Clear', icon: '☀️' },
    { value: 'light_rain', label: '🌦️ Light Rain', icon: '🌦️' },
    { value: 'heavy_rain', label: '🌧️ Heavy Rain', icon: '🌧️' },
    { value: 'storm', label: '⛈️ Storm', icon: '⛈️' },
    { value: 'fog', label: '🌫️ Fog', icon: '🌫️' }
  ];

  return (
    <div className="prediction-form">
      <div className="form-header">
        <h3>🚦 Traffic Prediction</h3>
        <p>Select your route and conditions</p>
      </div>

      <div className="form-grid">
        {/* Source */}
        <div className="form-group">
          <label className="form-label">
            <MapPin size={18} />
            Source Location
          </label>
          <input
            type="text"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="form-input"
            placeholder="Any place in Bengaluru (e.g. Nagarbhavi)"
            disabled={loading}
          />
        </div>

        {/* Destination */}
        <div className="form-group">
          <label className="form-label">
            <Navigation size={18} />
            Destination
          </label>
          <input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            className="form-input"
            placeholder="Any place in Bengaluru (e.g. Sarjapur Road)"
            disabled={loading}
          />
        </div>

        
        {/* Weather */}
        <div className="form-group">
          <label className="form-label">
            <Cloud size={18} />
            Weather Conditions
          </label>
          <select
            value={weather}
            onChange={(e) => setWeather(e.target.value)}
            className="form-select"
            disabled={loading}
          >
            {weatherOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="form-actions">
        <button
          onClick={handleUseMyLocation}
          className="location-btn"
          disabled={loading}
        >
          📍 Use My Location
        </button>

        <button
          onClick={handlePredict}
          className="predict-btn"
          disabled={loading || !source || !destination}
        >
          {loading ? (
            <>
              <div className="loading"></div>
              Predicting...
            </>
          ) : (
            '🚀 PREDICT NOW'
          )}
        </button>
      </div>

      {/* Location Info */}
      {useMyLocation && userLocation && (
        <div className="location-info">
          <small>
            📍 Using your location: {userLocation.lat.toFixed(4)}, {userLocation.lon.toFixed(4)}
          </small>
        </div>
      )}

      {/* Quick Routes */}
      <div className="quick-routes">
        <h4>📍 Popular Routes</h4>
        <div className="route-chips">
          {[
            { from: 'Hebbal', to: 'Silk Board' },
            { from: 'Manyata Tech Park', to: 'Electronic City' },
            { from: 'Whitefield', to: 'MG Road' },
            { from: 'Electronic City', to: 'Whitefield' }
          ].map((route, index) => (
            <button
              key={index}
              onClick={() => {
                setSource(route.from);
                setDestination(route.to);
              }}
              className="route-chip"
              disabled={loading}
            >
              {route.from} → {route.to}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PredictionForm;
