import React, { useEffect, useState } from 'react';
import TrafficForecastT120 from './TrafficForecastT120';

// This is now a SINGLE-PURPOSE panel: "if I start this journey ~2 hours
// from now, what travel time should I expect?" -- the old "Predict Now"
// / current-state option (ResultCard, /api/predict-enhanced's current
// GNN result) has been removed from the UI entirely per simplification.
// The route itself (distance, geometry, weather) still comes from the
// SAME /api/predict-enhanced call the page already makes to resolve
// Source -> Destination into a real OSRM route -- that call and its
// route-resolution role are unchanged; only its "current traffic result"
// is no longer shown here.
//
// Before the button is clicked: no forecast result is shown at all.
// After: TrafficForecastT120 (POST /api/traffic/forecast-t120/for-route,
// the real trained T+120 model) renders the one authoritative result.
const WEATHER_IMPACT_DESCRIPTION = {
  low: 'Condition is ideal for travel.',
  medium: 'Condition may add minor delays.',
  high: 'Condition may cause significant delays.',
};

const TrafficPredictionPanel = ({ prediction }) => {
  const [showForecast, setShowForecast] = useState(false);

  // A new route (new Source/Destination prediction) must not silently
  // keep showing a forecast card computed for the PREVIOUS route -- each
  // new route starts back at "no result shown until the button is
  // clicked", per the required flow.
  useEffect(() => {
    setShowForecast(false);
  }, [prediction]);

  if (!prediction) return null;

  const weatherImpactKey = (prediction.weather?.impact || '').toLowerCase();

  return (
    <div>
      <p className="cc-panel-title" style={{ marginBottom: '0.35rem' }}>🔮 2-Hour-Ahead Traffic Prediction</p>
      <p style={{ fontSize: '0.78rem', color: 'var(--cc-text-dim)', marginBottom: '0.5rem' }}>
        📍 {prediction.source} → {prediction.destination}
      </p>

      {prediction.weather && (
        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'baseline', marginBottom: '0.75rem', fontSize: '0.78rem', color: 'var(--cc-text-dim)' }}>
          <span>
            <strong style={{ color: 'var(--cc-text)' }}>Weather:</strong>{' '}
            {prediction.weather.condition || '—'}
            {prediction.weather.temperature != null && ` · ${prediction.weather.temperature}°C`}
          </span>
          {prediction.weather.impact && (
            <span style={{ color: 'var(--cc-text-faint)' }}>
              Impact: {prediction.weather.impact} — {WEATHER_IMPACT_DESCRIPTION[weatherImpactKey] || 'Current conditions for this route.'}
            </span>
          )}
        </div>
      )}

      {!showForecast && (
        <button
          type="button"
          className="cc-btn-primary"
          onClick={() => setShowForecast(true)}
          style={{ width: '100%', padding: '0.75rem 1rem' }}
        >
          🔮 Predict After 2 Hours
        </button>
      )}

      {showForecast && <TrafficForecastT120 prediction={prediction} />}
    </div>
  );
};

export default TrafficPredictionPanel;
