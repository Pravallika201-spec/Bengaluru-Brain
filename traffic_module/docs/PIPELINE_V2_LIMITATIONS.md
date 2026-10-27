# Traffic Prediction Pipeline V2 - Limitations and Documentation

## Overview
This document describes the limitations and constraints of the Traffic Prediction Pipeline V2, which uses real traffic data from the Bangalore Traffic Dataset and a trained Graph Neural Network (GNN) model.

## Data Limitations

### 1. No Hourly Timestamps
**Issue**: The traffic dataset (`Banglore_traffic_Dataset.csv`) contains only daily date information, not hourly timestamps.

**Impact**:
- The model cannot provide hourly traffic predictions
- Time-of-day patterns are inferred from day-of-week features, not actual hourly data
- Peak hour predictions are based on general patterns, not specific hourly observations

**Mitigation**:
- The model uses day-of-week as a temporal feature
- Hourly predictions are not supported and are explicitly documented
- The forecast endpoint returns the same prediction for all hours (no temporal variation)

### 2. No Real-Time Traffic Data
**Issue**: The dataset contains historical traffic observations from 2022-2024, not real-time live traffic feeds.

**Impact**:
- Predictions are based on historical patterns, not current conditions
- No live traffic incident data is incorporated
- Weather and event data are simulated or from external APIs, not integrated with live traffic

**Mitigation**:
- The model is trained on historical data to learn general traffic patterns
- Backend includes fallback to ORS (OpenRouteService) for routing
- Weather API integration provides current weather context

### 3. Limited Location Coverage
**Issue**: Only 13 traffic locations are mapped to OSM nodes in the `traffic_location_mapping.csv`.

**Mapped Locations**:
- 100 Feet Road
- CMH Road
- Marathahalli Bridge
- Sarjapur Road
- Trinity Circle
- Anil Kumble Circle
- Jayanagar 4th Block
- South End Circle
- Hebbal Flyover
- Tumkur Road
- ITPL Main Road
- Silk Board Junction
- Hosur Road

**Unmapped Locations**:
- Sony World Junction (NOT_FOUND)
- Yeshwanthpur Circle (NOT_FOUND)
- Ballari Road (CHECK_MANUALLY - too far from OSM node)

**Impact**:
- Predictions for unmapped locations rely on geocoding fallback
- Feature extraction for unmapped locations uses median values from mapped locations
- Reduced accuracy for unmapped areas

### 4. Temporal Data Gap
**Issue**: Dataset spans 2022-01-01 to 2024-08-09, but may not include recent traffic patterns.

**Impact**:
- Model may not capture very recent changes in traffic patterns
- Infrastructure changes (new roads, closures) not reflected
- Seasonal patterns may be incomplete

## Model Limitations

### 1. Graph Neural Network Architecture
**Architecture**: GAT (Graph Attention Network) with 15 input features

**Input Features**:
- Traffic volume
- Travel time index
- Road capacity utilization
- Incident reports
- Environmental impact
- Public transport usage
- Traffic signal compliance
- Parking usage
- Pedestrian/cyclist count
- Edge length
- Edge speed limit
- Lanes
- Node degree
- Day of week
- Weather code

**Limitations**:
- Model predicts normalized speed (0-1 range), not absolute values
- Edge-level predictions are aggregated for route-level results
- Graph connectivity is based on temporal proximity (7-day window), not spatial adjacency

### 2. Training Performance
**Metrics** (Test Set):
- MSE: 0.016971
- MAE: 0.104366 (normalized)
- MAE (speed): 8.35 km/h
- R²: 0.035332
- MAPE: 24.29%

**Interpretation**:
- Low R² indicates limited predictive power
- MAE of 8.35 km/h means speed predictions can be off by ±8 km/h
- Model explains only ~3.5% of variance in speed predictions
- This is a baseline model; performance can be improved with more data

### 3. Sample Size
**Training Samples**: 15,537 edge-level observations
**Graph Nodes**: 15,537 (one per sample)
**Graph Edges**: 291,868 (based on temporal proximity)

**Limitations**:
- Relatively small sample size for deep learning
- Limited geographic coverage (13 locations)
- Temporal coverage is limited to 2.5 years

## Prediction Limitations

### 1. Route Prediction
**Method**: Uses actual OSMnx shortest path with GNN-predicted edge speeds

**Limitations**:
- Route is based on shortest path by distance, not by predicted travel time
- No alternative route suggestions
- No dynamic rerouting based on predicted congestion

### 2. Travel Time Calculation
**Formula**: `travel_time = (distance_km / predicted_speed_kmh) * 60`

**Limitations**:
- Assumes constant speed across entire segment
- Does not account for traffic lights, intersections, or turns
- Speed predictions are aggregated from historical data, not real-time conditions

### 3. Delay Calculation
**Formula**: `delay = predicted_time - free_flow_time`

**Limitations**:
- Free-flow time is based on speed limits, which may not be accurate
- Delay can be negative (predicted faster than free-flow), clamped to 0
- No distinction between different types of delay (congestion, incidents, etc.)

## API Limitations

### 1. Forecast Endpoint
**Current Behavior**: Returns same prediction for 2-hour forecast

**Reason**: No hourly data to support temporal forecasting

**Recommendation**: Remove forecast endpoint or clearly document limitation

### 2. Confidence Score
**Current Value**: Fixed at 0.7 (70%)

**Reason**: Model R² is low (0.035), so confidence is not calculated from model performance

**Recommendation**: Calculate confidence from prediction intervals or use ensemble methods

## What Was Removed (Per User Requirements)

### 1. Random Route Node Selection
**Previous**: `np.random.choice(len(predictions), size=50, replace=False)` in `predict_traffic.py`
**Current**: Uses actual OSMnx shortest path between source and destination nodes

### 2. Hardcoded Delay Values
**Previous**: Fixed delays of 5, 15, 25 minutes based on congestion thresholds
**Current**: Delays calculated from predicted speeds vs free-flow speeds

### 3. Hardcoded Traffic Multipliers
**Previous**: Time-of-day multipliers applied uniformly
**Current**: GNN model learns patterns from data; multipliers not used in v2 pipeline

### 4. Fabricated Traffic Data
**Previous**: Synthetic traffic data generated for training
**Current**: Uses real traffic observations from Bangalore Traffic Dataset

## Recommendations for Improvement

### 1. Data Collection
- Collect hourly traffic data for better temporal resolution
- Expand location coverage to more areas of Bangalore
- Include real-time traffic feeds (e.g., Google Maps Traffic API)
- Add incident reports and road closure data

### 2. Model Improvements
- Increase sample size with more observations
- Add spatial features (road type, lane count, speed limits)
- Use ensemble methods for better uncertainty quantification
- Incorporate external data sources (weather, events, holidays)

### 3. Prediction Enhancements
- Implement dynamic routing based on predicted congestion
- Add alternative route suggestions
- Calculate prediction intervals for uncertainty
- Integrate real-time traffic data for live predictions

### 4. API Improvements
- Remove or clearly document forecast limitation
- Calculate confidence from model performance
- Add error handling for unmapped locations
- Provide more detailed factor explanations

## Conclusion

The Traffic Prediction Pipeline V2 represents a significant improvement over the previous version by:
- Using real traffic data instead of fabricated data
- Removing random node selection and hardcoded values
- Implementing actual OSM route prediction
- Calculating travel times from predicted speeds

However, the model has significant limitations due to:
- Lack of hourly timestamps
- No real-time data integration
- Limited location coverage
- Low predictive performance (R² = 0.035)

These limitations are clearly documented and should be communicated to users. Future work should focus on improving data quality and model performance.
