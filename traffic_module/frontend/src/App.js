import React, { useState, useEffect } from "react";
import "./App.css";

import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap
} from "react-leaflet";

import L from "leaflet";

import "leaflet/dist/leaflet.css";

// Fix default marker icon issue

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: require("leaflet/dist/images/marker-icon-2x.png"),
  iconUrl: require("leaflet/dist/images/marker-icon.png"),
  shadowUrl: require("leaflet/dist/images/marker-shadow.png"),
});

// Auto-fit map bounds

function RouteBounds({ routeCoords, sourceCoords, destCoords }) {

  const map = useMap();

  useEffect(() => {

    if (routeCoords && routeCoords.length > 0) {

      const bounds = L.latLngBounds(routeCoords);

      map.fitBounds(bounds, {
        padding: [50, 50],
        maxZoom: 15,
        animate: true,
        duration: 0.5
      });

    } else if (sourceCoords && destCoords) {

      const bounds = L.latLngBounds([
        sourceCoords,
        destCoords
      ]);

      map.fitBounds(bounds, {
        padding: [50, 50],
        maxZoom: 14,
        animate: true,
        duration: 0.5
      });
    }

  }, [routeCoords, sourceCoords, destCoords, map]);

  return null;
}

function App() {

  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");

  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);

  const bengaluruCenter = [12.9716, 77.5946];

  // Predict traffic

  const predictTraffic = async () => {

    if (!source || !destination) {

      alert("Enter source and destination");

      return;
    }

    setLoading(true);

    try {

      const response = await fetch(
        "http://127.0.0.1:8000/predict-route",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            source,
            destination
          })
        }
      );

      const data = await response.json();

      console.log(data);

      setResult(data);

    } catch (error) {

      console.log(error);

      alert("Backend connection failed");
    }

    setLoading(false);
  };

  // Traffic colors

  const getTrafficColor = (traffic) => {

    switch (traffic) {

      case "CRITICAL":
        return "#FF3131";

      case "HIGH":
        return "#FF6B35";

      case "MODERATE":
        return "#FFD700";

      case "LOW":
        return "#00FF00";

      default:
        return "#00D4FF";
    }
  };

  // Coordinates

  const sourceCoords =
    result?.source_coords || bengaluruCenter;

  const destCoords =
    result?.destination_coords || bengaluruCenter;

  const routeCoords =
    result?.route_coords || [];

  return (

    <div className="app-container">

      {/* HEADER */}

      <div className="header">

        <h1 className="title">
          Bengaluru Brain 🚦
        </h1>

      </div>

      {/* INPUT CARD */}

      <div className="input-card">

        <div className="input-group">

          <label>
            📍 Source Location
          </label>

          <input
            type="text"
            placeholder="e.g., Hebbal"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />

        </div>

        <div className="input-group">

          <label>
            🎯 Destination Location
          </label>

          <input
            type="text"
            placeholder="e.g., Marathahalli"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          />

        </div>

        <button
          onClick={predictTraffic}
          className="predict-button"
          disabled={loading}
        >

          {loading
            ? "🔄 Predicting..."
            : "🚀 Predict Traffic"}

        </button>

      </div>

      {/* LOADING */}

      {loading && (

        <div className="loading-overlay">

          <div className="spinner"></div>

          <p>
            Analyzing traffic patterns...
          </p>

        </div>

      )}

      {/* RESULTS */}

      {result && (

        <div className="results-container">

          {/* PREDICTION CARD */}

          <div className="prediction-card">

            <div className="route-header">

              <h2>
                {source} → {destination}
              </h2>

              <div
                className={`traffic-badge ${(result?.traffic || "").toLowerCase()}`}
              >

                {result?.traffic || "LOW"}

              </div>

            </div>

            {/* METRICS */}

            <div className="metrics-grid">

              <div className="metric-item">
                <div className="metric-label">Travel Time</div>
                <div className="metric-value">
                  {Math.round(result.travel_time)} mins
                </div>
              </div>

              <div className="metric-item">
                <div className="metric-label">Base Time</div>
                <div className="metric-value">
                  {Math.round(result.base_duration_mins)} mins
                </div>
              </div>

              <div className="metric-item">
                <div className="metric-label">Delay</div>
                <div className="metric-value delay">
                  +{Math.round(result.delay)} mins
                </div>
              </div>

              <div className="metric-item">
                <div className="metric-label">Distance</div>
                <div className="metric-value">
                  {result.distance_km.toFixed(1)} km
                </div>
              </div>

            </div>

            <div className="metrics-grid">

              <div className="metric-item">
                <div className="metric-label">Avg Speed</div>
                <div className="metric-value">
                  {result.avg_speed.toFixed(1)} km/h
                </div>
              </div>

              <div className="metric-item">
                <div className="metric-label">Route Type</div>
                <div className="metric-value">
                  {result.route_type.toUpperCase()}
                </div>
              </div>

            </div>

            {/* DAY INFO */}

            <div className="day-info-section">

              <div className="day-info-item">

                <span className="day-info-label">
                  📅 Day:
                </span>

                <span className="day-info-value">
                  {result?.day_name || "Unknown"} ({result?.day_type || "Unknown"})
                </span>

              </div>

              <div className="day-info-item">

                <span className="day-info-label">
                  🛣 Route:
                </span>

                <span className="day-info-value">
                  {result?.route_type?.toUpperCase() || "NORMAL"}
                </span>

              </div>

              <div className="day-info-item">

                <span className="day-info-label">
                  🚗 Speed:
                </span>

                <span className="day-info-value">
                  {result?.current_speed_kmh || 0} km/h
                </span>

              </div>

            </div>

            {/* FACTORS */}

            <div className="factors-section">

              <h3>
                📊 Contributing Factors
              </h3>

              <div className="factors-list">

                {result?.factors &&
                result.factors.length > 0 ? (

                  result.factors.map((factor, index) => (

                    <span
                      key={index}
                      className="factor-tag"
                    >
                      {factor}
                    </span>

                  ))

                ) : (

                  <span className="no-factors">
                    Normal traffic conditions
                  </span>

                )}

              </div>

            </div>

            {/* CONTEXT */}

            <div className="context-section">

              <div className="context-item">

                <span className="context-label">
                  🌦️ Weather:
                </span>

                <span className="context-value">
                  {result?.weather || "clear"}
                </span>

              </div>

              <div className="context-item">

                <span className="context-label">
                  🎭 Event:
                </span>

                <span className="context-value">
                  {result?.event || "No Event"}
                </span>

              </div>

              <div className="context-item">

                <span className="context-label">
                  🎯 Confidence:
                </span>

                <span className="context-value">
                  {Math.round((result?.confidence || 0) * 100)}%
                </span>

              </div>

            </div>

            {/* STATUS */}

            <div className="status-section">

              <div className="status-message">
                {result?.status || "No status"}
              </div>

            </div>

          </div>

          {/* MAP */}

          <div className="map-card">

            <MapContainer
              center={bengaluruCenter}
              zoom={10}
              style={{
                height: "500px",
                width: "100%",
                borderRadius: "16px"
              }}
            >

              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; OpenStreetMap contributors'
              />

              <RouteBounds
                routeCoords={routeCoords}
                sourceCoords={sourceCoords}
                destCoords={destCoords}
              />

              {/* SOURCE */}

              <Marker position={sourceCoords}>

                <Popup>

                  <div className="marker-popup">

                    <strong>
                      🚩 Source
                    </strong>

                    <br />

                    {source}

                  </div>

                </Popup>

              </Marker>

              {/* DESTINATION */}

              <Marker position={destCoords}>

                <Popup>

                  <div className="marker-popup">

                    <strong>
                      🏁 Destination
                    </strong>

                    <br />

                    {destination}

                  </div>

                </Popup>

              </Marker>

              {/* ROUTE */}

              {routeCoords &&
              routeCoords.length > 0 && (

                <Polyline
                  positions={routeCoords}
                  pathOptions={{
                    color: getTrafficColor(result?.traffic || "LOW"),
                    weight: 6,
                    opacity: 0.8,
                    lineCap: "round",
                    lineJoin: "round"
                  }}
                />

              )}

            </MapContainer>

          </div>

        </div>
      )}

    </div>
  );
}

export default App;