import React, { useState, useEffect } from "react";
import "./App.css";

import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap,
} from "react-leaflet";

import L from "leaflet";
import "leaflet/dist/leaflet.css";


// ============================================================
// LEAFLET MARKER FIX
// ============================================================

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: require(
    "leaflet/dist/images/marker-icon-2x.png"
  ),
  iconUrl: require(
    "leaflet/dist/images/marker-icon.png"
  ),
  shadowUrl: require(
    "leaflet/dist/images/marker-shadow.png"
  ),
});


// ============================================================
// MAP AUTO FIT
// ============================================================

function RouteBounds({
  routeCoords,
  sourceCoords,
  destCoords,
}) {
  const map = useMap();

  useEffect(() => {
    try {
      if (
        routeCoords &&
        routeCoords.length > 1
      ) {
        const bounds =
          L.latLngBounds(routeCoords);

        map.fitBounds(bounds, {
          padding: [50, 50],
          maxZoom: 15,
          animate: true,
        });
      } else if (
        sourceCoords &&
        destCoords
      ) {
        const bounds =
          L.latLngBounds([
            sourceCoords,
            destCoords,
          ]);

        map.fitBounds(bounds, {
          padding: [50, 50],
          maxZoom: 14,
          animate: true,
        });
      }
    } catch (error) {
      console.error(
        "Map bounds error:",
        error
      );
    }
  }, [
    routeCoords,
    sourceCoords,
    destCoords,
    map,
  ]);

  return null;
}


// ============================================================
// MAIN APPLICATION
// ============================================================

function App() {

  const [source, setSource] =
    useState("");

  const [destination, setDestination] =
    useState("");

  const [result, setResult] =
    useState(null);

  const [error, setError] =
    useState("");

  const [loading, setLoading] =
    useState(false);


  // ==========================================================
  // BENGALURU CENTER
  // ==========================================================

  const bengaluruCenter = [
    12.9716,
    77.5946,
  ];


  // ==========================================================
  // PREDICT TRAFFIC
  // ==========================================================

  const predictTraffic = async () => {

    if (
      !source.trim() ||
      !destination.trim()
    ) {
      setError(
        "Please enter both source and destination."
      );

      setResult(null);

      return;
    }

    setLoading(true);

    setError("");

    setResult(null);

    try {

      const response = await fetch(
        "http://127.0.0.1:8000/predict-route",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            source:
              source.trim(),

            destination:
              destination.trim(),
          }),
        }
      );


      // ------------------------------------------------------
      // Read response safely
      // ------------------------------------------------------

      const data =
        await response.json();


      console.log(
        "Backend response:",
        data
      );


      // ------------------------------------------------------
      // Handle backend errors
      // ------------------------------------------------------

      if (!response.ok) {

        const message =
          data?.detail ||
          "Backend returned an error.";

        throw new Error(
          message
        );
      }


      // ------------------------------------------------------
      // Validate essential fields
      // ------------------------------------------------------

      if (
        typeof data.distance_km !==
        "number"
      ) {
        throw new Error(
          "Backend response is missing distance_km."
        );
      }
      if (typeof data.travel_time !== "number") {
  throw new Error(
    "Backend response is missing travel time."
  );
}
      setResult(data);

    } catch (err) {

      console.error(
        "Prediction error:",
        err
      );

      setError(
        err.message ||
        "Unable to connect to the backend."
      );
      setResult(null);
    } finally {
      setLoading(false);
    }
  };
  // ==========================================================
  // TRAFFIC COLOR
  // ==========================================================
  const getTrafficColor =
    (traffic) => {
      const value =
        String(
          traffic || ""
        ).toUpperCase();
      switch (value) {
        case "CRITICAL":
          return "#FF3131";
        case "HEAVY":
        case "HIGH":
          return "#FF6B35";
        case "MODERATE":
          return "#FFD700";
        case "FREE FLOW":
        case "LOW":
          return "#00FF00";
        default:
          return "#00D4FF";
      }
    };
  // ==========================================================
  // SAFE VALUES
  // ==========================================================
  const distance =
    Number(
      result?.distance_km || 0
    );
  const baseTime =
    Number(
      result?.base_travel_time_min || 0
    );
  const currentTime =
    Number(
      result?.current_travel_time_min || 0
    );
  const predictedTime =
    Number(
      result?.predicted_travel_time_min || 0
    );
  const delay =
    Number(
      result?.delay_min || 0
    );
  const currentSpeed =
    Number(
      result?.current_speed || 0
    );
  const predictedSpeed =
    Number(
      result?.predicted_speed || 0
    );
  const confidence =
    Number(
      result?.confidence || 0
    );
  const traffic =
    result?.traffic ||
    "UNKNOWN";
  // ==========================================================
  // COORDINATES
  // ==========================================================
  const sourceCoords =
    Array.isArray(
      result?.source_coords
    )
      ? result.source_coords
      : bengaluruCenter;
  const destCoords =
    Array.isArray(
      result?.destination_coords
    )
      ? result.destination_coords
      : bengaluruCenter;
  // ==========================================================
  // ROUTE COORDINATES
  // ==========================================================
  const routeCoords =
    Array.isArray(
      result?.route_coords
    )
      ? result.route_coords
      : [];
  // ==========================================================
  // TRAFFIC POINTS
  // ==========================================================
  const trafficPoints =
    Array.isArray(
      result?.traffic_points
    )
      ? result.traffic_points
      : [];


  // ==========================================================
  // UI
  // ==========================================================

  return (

    <div className="app-container">


      {/* ====================================================
          HEADER
      ==================================================== */}

      <div className="header">

        <h1 className="title">
          Bengaluru Brain 🚦
        </h1>

        <p>
          AI-Powered Bengaluru Traffic
          Prediction & Route Intelligence
        </p>

      </div>


      {/* ====================================================
          INPUT CARD
      ==================================================== */}

      <div className="input-card">

        <div className="input-group">

          <label>
            📍 Source Location
          </label>

          <input
            type="text"
            placeholder="e.g., Hebbal"
            value={source}
            onChange={(e) =>
              setSource(
                e.target.value
              )
            }
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
            onChange={(e) =>
              setDestination(
                e.target.value
              )
            }
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


      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (

        <div className="error-message">

          ❌ {error}

        </div>

      )}


      {/* ====================================================
          LOADING
      ==================================================== */}

      {loading && (

        <div className="loading-overlay">

          <div className="spinner"></div>

          <p>
            Analyzing Bengaluru traffic...
          </p>

        </div>

      )}


      {/* ====================================================
          RESULTS
      ==================================================== */}

      {result && !loading && (

        <div className="results-container">


          {/* ==================================================
              PREDICTION CARD
          ================================================== */}

          <div className="prediction-card">


            {/* ROUTE HEADER */}

            <div className="route-header">

              <h2>
                {source}
                {" → "}
                {destination}
              </h2>

              <div
                className="traffic-badge"
                style={{
                  background:
                    getTrafficColor(
                      traffic
                    ),
                  color:
                    traffic ===
                    "MODERATE"
                      ? "#000"
                      : "#fff",
                }}
              >

                {traffic}

              </div>

            </div>


            {/* =================================================
                MAIN METRICS
            ================================================= */}

            <div className="metrics-grid">


              <div className="metric-item">

                <div className="metric-label">
                  Predicted Travel Time
                </div>

                <div className="metric-value">

                  {predictedTime.toFixed(2)}
                  {" "}mins

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Current Travel Time
                </div>

                <div className="metric-value">

                  {currentTime.toFixed(2)}
                  {" "}mins

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Base Travel Time
                </div>

                <div className="metric-value">

                  {baseTime.toFixed(2)}
                  {" "}mins

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Delay
                </div>

                <div className="metric-value delay">

                  +{delay.toFixed(2)}
                  {" "}mins

                </div>

              </div>


            </div>


            {/* =================================================
                SECOND METRICS
            ================================================= */}

            <div className="metrics-grid">


              <div className="metric-item">

                <div className="metric-label">
                  Distance
                </div>

                <div className="metric-value">

                  {distance.toFixed(2)}
                  {" "}km

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Current Speed
                </div>

                <div className="metric-value">

                  {currentSpeed.toFixed(1)}
                  {" "}km/h

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Predicted Speed
                </div>

                <div className="metric-value">

                  {predictedSpeed.toFixed(1)}
                  {" "}km/h

                </div>

              </div>


              <div className="metric-item">

                <div className="metric-label">
                  Confidence
                </div>

                <div className="metric-value">

                  {(confidence * 100).toFixed(1)}
                  %

                </div>

              </div>


            </div>


            {/* =================================================
                ROUTE INFORMATION
            ================================================= */}

            <div className="day-info-section">


              <div className="day-info-item">

                <span className="day-info-label">
                  🚦 Traffic:
                </span>

                <span className="day-info-value">

                  {traffic}

                </span>

              </div>


              <div className="day-info-item">

                <span className="day-info-label">
                  🛣️ Roads:
                </span>

                <span className="day-info-value">

                  {Array.isArray(
                    result.road_names
                  )
                    ? result.road_names.length
                    : 0}

                  {" "}roads

                </span>

              </div>


              <div className="day-info-item">

                <span className="day-info-label">
                  📡 Traffic Points:
                </span>

                <span className="day-info-value">

                  {trafficPoints.length}

                </span>

              </div>


            </div>


            {/* =================================================
                TRAFFIC POINTS
            ================================================= */}

            {trafficPoints.length > 0 && (

              <div className="factors-section">

                <h3>
                  📊 Live Traffic Points
                </h3>


                <div className="factors-list">

                  {trafficPoints.map(
                    (point, index) => (

                      <span
                        key={
                          `${point.traffic_location}-${index}`
                        }
                        className="factor-tag"
                      >

                        {point.traffic_location}

                        {" — "}

                        {Number(
                          point.current_speed_kmh || 0
                        ).toFixed(0)}

                        {" km/h"}

                      </span>

                    )
                  )}

                </div>

              </div>

            )}


            {/* =================================================
                ROUTE ROADS
            ================================================= */}

            {Array.isArray(
              result.road_names
            ) &&
            result.road_names.length > 0 && (

              <div className="factors-section">

                <h3>
                  🛣️ Route Roads
                </h3>

                <div className="factors-list">

                  {result.road_names.map(
                    (road, index) => (

                      <span
                        key={index}
                        className="factor-tag"
                      >

                        {road}

                      </span>

                    )
                  )}

                </div>

              </div>

            )}


            {/* =================================================
                STATUS
            ================================================= */}

            <div className="status-section">

              <div className="status-message">

                {traffic === "HEAVY" &&
                  "⚠️ Heavy traffic detected on the route."}

                {traffic === "CRITICAL" &&
                  "🚨 Critical traffic conditions detected."}

                {traffic === "MODERATE" &&
                  "⚠️ Moderate traffic conditions detected."}

                {(traffic ===
                  "FREE FLOW" ||
                  traffic === "LOW") &&
                  "✅ Traffic is flowing normally."}

                {![
                  "HEAVY",
                  "CRITICAL",
                  "MODERATE",
                  "FREE FLOW",
                  "LOW",
                ].includes(traffic) &&
                  "Traffic analysis completed."}

              </div>

            </div>

          </div>


          {/* ==================================================
              MAP
          ================================================== */}

          <div className="map-card">

            <MapContainer
              center={
                sourceCoords ||
                bengaluruCenter
              }
              zoom={11}
              style={{
                height: "500px",
                width: "100%",
                borderRadius: "16px",
              }}
            >

              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution="&copy; OpenStreetMap contributors"
              />


              <RouteBounds
                routeCoords={
                  routeCoords
                }
                sourceCoords={
                  sourceCoords
                }
                destCoords={
                  destCoords
                }
              />


              {/* SOURCE MARKER */}

              <Marker
                position={
                  sourceCoords
                }
              >

                <Popup>

                  <strong>
                    🚩 Source
                  </strong>

                  <br />

                  {source}

                </Popup>

              </Marker>


              {/* DESTINATION MARKER */}

              <Marker
                position={
                  destCoords
                }
              >

                <Popup>

                  <strong>
                    🏁 Destination
                  </strong>

                  <br />

                  {destination}

                </Popup>

              </Marker>


              {/* ROUTE */}

              {routeCoords.length > 1 && (

                <Polyline
                  positions={
                    routeCoords
                  }
                  pathOptions={{
                    color:
                      getTrafficColor(
                        traffic
                      ),
                    weight: 6,
                    opacity: 0.85,
                    lineCap: "round",
                    lineJoin: "round",
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