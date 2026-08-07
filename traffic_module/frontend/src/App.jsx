import React, { useState, useEffect } from 'react';
import PredictionForm from './components/PredictionForm';
import ResultCard from './components/ResultCard';
import WardMap from './components/WardMap';
import WardStressGrid from './components/WardStressGrid';
import IncidentsPanel from './components/IncidentsPanel';
import ITShiftTimer from './components/ITShiftTimer';
import PeakHoursChart from './components/PeakHoursChart';
import SMSPreview from './components/SMSPreview';
import ModuleStatusBar from './components/ModuleStatusBar';
import './App.css';
import './components.css';

function App() {
  const [prediction, setPrediction] = useState(null);
  const [locations, setLocations] = useState([]);
  const [wardStress, setWardStress] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [weather, setWeather] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [loading, setLoading] = useState(false);

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
      const response = await fetch('/api/ward-stress');
      const data = await response.json();
      setWardStress(data);
    } catch (error) {
      console.error('Failed to fetch ward stress:', error);
    }
  };

  const fetchIncidents = async () => {
    try {
      const response = await fetch('/api/incidents');
      const data = await response.json();
      setIncidents(data);
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
    setLoading(true);
    try {
      const response = await fetch('/api/predict', {
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
      setPrediction(data);
    } catch (error) {
      console.error('Prediction error:', error);
      // Show error message
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <div className="header-title">
            <h1>🧠 BENGALURU BRAIN</h1>
            <h2>NAMMA FLOW — Traffic Intelligence</h2>
          </div>
          
          <div className="header-info">
            <div className="live-clock">
              {currentTime.toLocaleTimeString()}
            </div>
            
            {weather && (
              <div className="weather-info">
                <span className="weather-icon">
                  {weather.condition === 'clear' ? '☀️' : 
                   weather.condition === 'clouds' ? '☁️' : 
                   weather.condition.includes('rain') ? '🌧️' : '🌫️'}
                </span>
                <span className="weather-temp">{weather.temperature}°C</span>
              </div>
            )}
            
            <div className="live-indicator">
              <div className="live-dot"></div>
              <span>LIVE</span>
            </div>
          </div>
        </div>
      </header>

      <div className="main-content">
        {/* Prediction Form */}
        <div className="prediction-section">
          <PredictionForm 
            locations={locations} 
            onPredict={handlePredict}
            loading={loading}
          />
        </div>

        {/* Results */}
        {prediction && (
          <div className="results-section">
            <ResultCard prediction={prediction} />
          </div>
        )}

        {/* Map and Grid Layout */}
        <div className="dashboard-grid">
          {/* Ward Map */}
          <div className="map-section">
            <WardMap 
              locations={locations}
              wardStress={wardStress}
              prediction={prediction}
            />
          </div>

          {/* Ward Stress Grid */}
          <div className="stress-grid-section">
            <WardStressGrid wardStress={wardStress} />
          </div>
        </div>

        {/* Bottom Panels */}
        <div className="bottom-panels">
          {/* Incidents Panel */}
          <div className="incidents-section">
            <IncidentsPanel incidents={incidents} />
          </div>

          {/* IT Shift Timer */}
          <div className="shift-timer-section">
            <ITShiftTimer />
          </div>
        </div>

        {/* Charts and SMS */}
        <div className="charts-section">
          {/* Peak Hours Chart */}
          <div className="chart-section">
            <PeakHoursChart />
          </div>

          {/* SMS Preview */}
          {prediction && prediction.current_status === 'CRITICAL' && (
            <div className="sms-section">
              <SMSPreview prediction={prediction} />
            </div>
          )}
        </div>
      </div>

      {/* Module Status Bar */}
      <ModuleStatusBar />
    </div>
  );
}

export default App;
