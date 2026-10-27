import React, { useState, useEffect, useRef } from 'react';
import PredictionForm from './components/PredictionForm';
import RouteMap from './components/RouteMap';
import TrafficForecastAndIncidents from './components/TrafficForecastAndIncidents';
import TrafficPredictionPanel from './components/TrafficPredictionPanel';
import WardTrafficStressMonitor from './components/WardTrafficStressMonitor';
import IncidentsPanel from './components/IncidentsPanel';
import ITShiftTimer from './components/ITShiftTimer';
import PeakHoursChart from './components/PeakHoursChart';
import SMSPreview from './components/SMSPreview';
import ModuleStatusBar from './components/ModuleStatusBar';
import OverviewPanel from './components/OverviewPanel';
import WastePanel from './components/WastePanel';
import UsiPanel from './components/UsiPanel';
import AlertsPanel from './components/AlertsPanel';
import './App.css';
import './components.css';
import './dashboard.css';
import './theme.css';

const TABS = [
  { id: 'overview', label: 'Overview', icon: '🏠' },
  { id: 'traffic', label: 'Traffic', icon: '🚦' },
  { id: 'waste', label: 'Waste', icon: '🗑️' },
  { id: 'usi', label: 'USI', icon: '📊' },
  { id: 'alerts', label: 'Alerts', icon: '🔔' },
];

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedUsiArea, setSelectedUsiArea] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [locations, setLocations] = useState([]);
  const [wardStress, setWardStress] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [weather, setWeather] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [loading, setLoading] = useState(false);
  const [predictError, setPredictError] = useState(null);
  // Guards against a real, verified race condition: if an OLDER prediction
  // request's network response resolves AFTER a NEWER one (plausible —
  // different routes hit OSRM/GNN/weather with different real latency),
  // the older response must NOT be allowed to overwrite the already-shown
  // newer result. Each call gets a monotonically increasing id; only the
  // response matching the CURRENT latest id is ever applied.
  const requestIdRef = useRef(0);

  // Fetch initial data
  useEffect(() => {
    fetchLocations();
    fetchWardStress();
    fetchIncidents();
    fetchWeather();

    // Update time every second
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Refresh data periodically
  useEffect(() => {
    const interval = setInterval(() => {
      fetchWardStress();
      fetchIncidents();
      fetchWeather();
    }, 60000); // Refresh every minute

    return () => clearInterval(interval);
  }, []);

  const fetchLocations = async () => {
    try {
      const response = await fetch('/api/locations');
      const data = await response.json();
      setLocations(data);
    } catch (error) {
      console.error('Failed to fetch locations:', error);
    }
  };

  const fetchWardStress = async () => {
    try {
      // NOTE: /api/ward-stress is SIMULATED data (see backend/ward_stress.py) —
      // there is no live sensor feed behind these numbers yet.
      const response = await fetch('/api/ward-stress');
      const data = await response.json();
      setWardStress(data.wards || []);
    } catch (error) {
      console.error('Failed to fetch ward stress:', error);
    }
  };

  const fetchIncidents = async () => {
    try {
      const response = await fetch('/api/incident/list');
      const data = await response.json();
      setIncidents(data.success ? data.incidents : []);
    } catch (error) {
      console.error('Failed to fetch incidents:', error);
    }
  };

  const fetchWeather = async () => {
    try {
      const response = await fetch('/api/weather');
      const data = await response.json();
      setWeather(data.weather);
    } catch (error) {
      console.error('Failed to fetch weather:', error);
    }
  };

  const handlePredict = async (predictionData) => {
    const thisRequestId = ++requestIdRef.current;
    setLoading(true);
    setPredictError(null);
    // Clear the previous result immediately rather than leaving a stale
    // route's numbers on screen while the new request is in flight — the
    // exact "does not update correctly" symptom is indistinguishable from
    // "still showing the old route" if we don't do this.
    setPrediction(null);
    try {
      // Use enhanced endpoint for real-time traffic intelligence
      const response = await fetch('/api/predict-enhanced', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(predictionData),
      });

      if (!response.ok) {
        throw new Error('Prediction failed');
      }

      const data = await response.json();

      // Ignore this response if a newer request has since been fired —
      // prevents an out-of-order (slower) older response from clobbering
      // an already-displayed newer result.
      if (thisRequestId !== requestIdRef.current) return;

      // The backend's exception path (e.g. the source/destination text
      // couldn't be geocoded at all — a real "location not found", not a
      // bug) falls back to a degraded response with no source/destination
      // fields at all and status "Unable to predict". Found via testing an
      // address the forward geocoder genuinely can't resolve: this shape
      // previously slipped past the mismatch check below because a MISSING
      // data.source was treated as "trivially matches" rather than a
      // failure signal — fixed by checking for this shape explicitly.
      const looksLikeGeocodeFailure = data.status === 'Unable to predict'
        || (data.distance_km === 0 && !data.source && !data.destination);
      if (looksLikeGeocodeFailure) {
        setPredictError(
          `Could not find a route for "${predictionData.source}" → "${predictionData.destination}" — one of these locations could not be geocoded. Try a more specific or different location name.`
        );
        return;
      }

      // Defense in depth: the backend was verified this session to never
      // mix up routes across requests, but assert it anyway rather than
      // silently trusting it — if it ever did, showing a mismatched result
      // would be worse than showing an explicit error.
      const sourceMatches = !data.source || data.source.toLowerCase() === predictionData.source.toLowerCase();
      const destMatches = !data.destination || data.destination.toLowerCase() === predictionData.destination.toLowerCase();
      if (!sourceMatches || !destMatches) {
        setPredictError(
          `Backend returned a result for "${data.source} → ${data.destination}" but "${predictionData.source} → ${predictionData.destination}" was requested — discarding rather than showing a mismatched route.`
        );
        return;
      }

      setPrediction(data);
    } catch (error) {
      if (thisRequestId !== requestIdRef.current) return;
      console.error('Prediction error:', error);
      setPredictError(error.message || 'Prediction failed — please try again.');
    } finally {
      if (thisRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  return (
    <div className="app">
      {/* Top bar + navigation are wrapped in one sticky group so the nav
          always sits directly below the header regardless of the header's
          actual rendered height (fixes a real bug: the header can wrap to
          two lines on narrower widths, and the nav previously used a
          hardcoded `top: 54px` sticky offset that no longer matched,
          causing the taller header to visually cover the nav once
          scrolled — found via live browser testing). */}
      <div className="cc-header-group">
      <header className="cc-topbar">
        <div className="cc-brand">
          <div className="cc-brand-icon">🧠</div>
          <div className="cc-brand-text">
            <h1>BENGALURU BRAIN</h1>
            <p>Namma Flow — Civic Intelligence Platform</p>
          </div>
        </div>

        <div className="cc-topbar-right">
          {/* FINAL VISUAL THEME FIX: header badge requested in the theme
              brief -- static label, no new data/endpoint/logic. */}
          <span className="cc-pill info cc-ward-badge">369 WARDS</span>

          <div className="cc-chip"><strong>{currentTime.toLocaleTimeString()}</strong></div>

          {weather && (
            <div className="cc-chip">
              <span>
                {weather.condition === 'clear' ? '☀️' :
                 weather.condition === 'clouds' ? '☁️' :
                 weather.condition.includes('rain') ? '🌧️' : '🌫️'}
              </span>
              <strong>{weather.temperature}°C</strong>
            </div>
          )}

          <div className="cc-chip live">
            <span className="cc-dot"></span>
            <span>LIVE</span>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="cc-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`cc-navlink ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
      </div>

      <div className="cc-page">
        {activeTab === 'overview' && <OverviewPanel />}

        {activeTab === 'traffic' && (
          <>
            <div className="cc-hero">
              <div>
                <h2>🚦 Traffic Intelligence</h2>
                <p>
                  Real-world route prediction using GNN + OSRM — powered by real, TomTom-labeled road
                  segments where coverage exists, otherwise a clearly-labeled static estimate.
                </p>
              </div>
            </div>

            {/* ================================================================
                GROUP A — PREDICT A ROUTE
                source/destination -> current condition -> 2-hour forecast ->
                route map. Underlying calls/props are UNCHANGED: PredictionForm
                still calls handlePredict -> /api/predict-enhanced; the result
                still flows into TrafficPredictionPanel (T+120 forecast) and
                RouteMap exactly as before. Only the surrounding grouping/
                visual hierarchy changed.
                ================================================================ */}
            <div className="cc-section-heading"><span>Predict a Route</span></div>

            <PredictionForm
              locations={locations}
              onPredict={handlePredict}
              loading={loading}
            />

            {predictError && (
              <div className="cc-panel" style={{ borderColor: 'var(--cc-red)', color: '#ff8a8a' }}>
                ⚠️ {predictError}
              </div>
            )}

            {loading && (
              <div className="cc-panel cc-empty">
                Predicting… (this route's real routing/GNN lookup is in progress)
              </div>
            )}

            {/* FIXED order within Group A — do not reorder, and do not make
                either conditional on anything beyond what's already here. */}
            {!loading && prediction && <TrafficPredictionPanel prediction={prediction} />}

            {!loading && prediction && <RouteMap prediction={prediction} />}

            {/* ================================================================
                GROUP B — CITY TRAFFIC CONDITIONS
                Replaces the old citywide point-map (WardMap, always zoomed to
                a near-empty world view) with a Ward Traffic Stress Monitor
                driven by the SAME wardStress data (same /api/ward-stress
                fetch above) -- no new endpoint, no new/random values. WardMap
                and the old card-grid WardStressGrid are no longer rendered on
                this page (components preserved, unused, see backup folder);
                the real Traffic prediction route map above is untouched.
                ================================================================ */}
            <div className="cc-section-heading"><span>City Traffic Conditions</span></div>

            <WardTrafficStressMonitor wardStress={wardStress} />

            {/* ================================================================
                GROUP C — INCIDENTS & PATTERNS
                Same components, same data/endpoints as before, grouped and
                re-themed together. IncidentsPanel's demo-only controls
                (+ Demo Incident / Clear All / Auto ON toggle) have been
                removed from this citizen-facing view; see IncidentsPanel.jsx.
                ================================================================ */}
            <div className="cc-section-heading"><span>Incidents &amp; Patterns</span></div>

            <TrafficForecastAndIncidents
              source={prediction?.source}
              destination={prediction?.destination}
              destinationCoords={prediction?.destination_coords}
            />

            <div className="cc-2col">
              <IncidentsPanel incidents={incidents} />
              <ITShiftTimer />
            </div>

            <div className="cc-2col">
              <PeakHoursChart />
              {prediction && (prediction.traffic === 'SEVERE' || prediction.traffic === 'HIGH') && (
                <SMSPreview prediction={prediction} />
              )}
            </div>
          </>
        )}

        {activeTab === 'waste' && <WastePanel />}

        {activeTab === 'usi' && (
          <UsiPanel selectedArea={selectedUsiArea} onSelectArea={setSelectedUsiArea} />
        )}

        {activeTab === 'alerts' && (
          <AlertsPanel selectedArea={selectedUsiArea} onSelectArea={setSelectedUsiArea} />
        )}

      </div>

      {/* Module Status Bar */}
      <ModuleStatusBar />
    </div>
  );
}

export default App;
