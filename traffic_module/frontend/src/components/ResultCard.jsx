import React from 'react';
import { 
  AlertTriangle, 
  Clock, 
  Route, 
  TrendingUp, 
  Wind, 
  Calendar,
  MapPin,
  AlertCircle
} from 'lucide-react';

const ResultCard = ({ prediction }) => {
  const getStatusColor = (status) => {
    switch (status.toLowerCase()) {
      case 'clear':
        return 'traffic-low';
      case 'low':
        return 'traffic-low';
      case 'moderate':
        return 'traffic-medium';
      case 'high':
        return 'traffic-high';
      case 'critical':
        return 'traffic-critical';
      default:
        return 'traffic-medium';
    }
  };

  const getStatusBadge = (status) => {
    switch (status.toLowerCase()) {
      case 'clear':
        return 'status-green';
      case 'low':
        return 'status-green';
      case 'moderate':
        return 'status-yellow';
      case 'high':
        return 'status-orange';
      case 'critical':
        return 'status-red';
      default:
        return 'status-yellow';
    }
  };

  const formatTime = (minutes) => {
    if (minutes < 60) {
      return `${minutes} min`;
    }
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}min`;
  };

  const getCongestionPercentage = (score) => {
    return Math.round(score * 100);
  };

  return (
    <div className="result-card">
      <div className="result-header">
        <h3>🎯 AI-Assisted Traffic Prediction</h3>
        <div className={`status-badge ${getStatusBadge(prediction.traffic)}`}>
          {prediction.traffic}
        </div>
      </div>

      {/* Route Information */}
      <div className="route-display">
        <div className="route-header">
          <MapPin size={20} />
          <span>📍 {prediction.source} → {prediction.destination}</span>
        </div>
        <div className="route-details">
          <div className="route-distance">📏 Distance: {prediction.distance_km} km</div>
          <div className="route-time">� Prediction Time: {prediction.prediction_time}</div>
          <div className="route-day">📅 {prediction.day_type}</div>
        </div>
      </div>

      {/* Travel Time Analysis */}
      <div className="travel-time-section">
        <h4>⏱️ Travel Time Analysis</h4>
        <div className="time-comparison">
          <div className="time-item">
            <div className="time-label">Estimated Travel Time:</div>
            <div className={`time-value ${getStatusColor(prediction.traffic)}`}>
              {prediction.travel_time} mins
            </div>
          </div>
          <div className="time-item">
            <div className="time-label">Predicted Delay:</div>
            <div className={`delay-value ${getStatusColor(prediction.traffic)}`}>
              +{prediction.delay} mins
            </div>
          </div>
          <div className="time-item">
            <div className="time-label">Traffic Status:</div>
            <div className={`traffic-status ${getStatusColor(prediction.traffic)}`}>
              {prediction.traffic}
            </div>
          </div>
        </div>
      </div>

      {/* AI Congestion Score */}
      <div className="congestion-gauge">
        <h4>🧠 AI Congestion Score</h4>
        <div className="gauge-container">
          <div className="gauge-circle">
            <div 
              className="gauge-fill"
              style={{
                background: `conic-gradient(
                  ${prediction.congestion_score > 0.8 ? '#FF3131' : 
                    prediction.congestion_score > 0.6 ? '#FF6B35' : 
                    prediction.congestion_score > 0.4 ? '#FFD700' : 
                    prediction.congestion_score > 0.2 ? '#00FF00' : '#00FF00'} 
                  0deg ${Math.round(prediction.congestion_score * 100) * 3.6}deg,
                  #1E293B ${Math.round(prediction.congestion_score * 100) * 3.6}deg 360deg
                )`
              }}
            >
              <div className="gauge-center">
                <div className={`congestion-score ${getStatusColor(prediction.traffic)}`}>
                  {Math.round(prediction.congestion_score * 100)}%
                </div>
                <div className="congestion-label">AI Score</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Contributing Factors */}
      <div className="factors-section">
        <h4>� Contributing Factors</h4>
        <div className="factor-badges">
          {prediction.factors && prediction.factors.length > 0 ? (
            prediction.factors.map((factor, index) => (
              <div key={index} className="factor-badge">
                <div className="factor-icon">
                  {factor.includes('IT') ? '🏢' : 
                   factor.includes('weather') || factor.includes('rain') ? '🌦️' :
                   factor.includes('office') || factor.includes('rush') ? '🚗' :
                   factor.includes('weekend') ? '📅' : '📊'}
                </div>
                <div className="factor-text">{factor}</div>
              </div>
            ))
          ) : (
            <div className="no-factors">Normal traffic conditions</div>
          )}
        </div>
      </div>

      {/* Weather Impact */}
      <div className="weather-section">
        <h4>🌦️ Weather Conditions</h4>
        <div className="weather-info">
          <div className="weather-type">{prediction.weather}</div>
          <div className="weather-impact">
            {prediction.weather === 'clear' ? '✅ Clear visibility' :
             prediction.weather === 'light_rain' ? '🌦️ Light rain impact' :
             prediction.weather === 'heavy_rain' ? '🌧️ Heavy rain impact' :
             prediction.weather === 'storm' ? '⛈️ Storm impact' :
             prediction.weather === 'fog' ? '🌫️ Fog impact' : '🌤️ Weather conditions'}
          </div>
        </div>
      </div>

      {/* AI Confidence */}
      <div className="confidence-section">
        <h4>🎯 AI Confidence</h4>
        <div className="confidence-meter">
          <div className="confidence-bar">
            <div 
              className="confidence-fill"
              style={{ width: `${prediction.confidence * 100}%` }}
            ></div>
          </div>
          <div className="confidence-text">
            {Math.round(prediction.confidence * 100)}% confidence
          </div>
        </div>
      </div>

      {/* Status Summary */}
      <div className="status-summary">
        <div className="status-icon">
          <AlertCircle size={24} />
        </div>
        <div className="status-content">
          <div className="status-title">Prediction Summary</div>
          <div className="status-message">{prediction.status}</div>
        </div>
      </div>
    </div>
  );
};

export default ResultCard;
