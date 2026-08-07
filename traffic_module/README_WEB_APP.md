# 🚦 Bengaluru Traffic Prediction Web App

A full-stack route-based traffic prediction system powered by Graph Neural Networks (GNN) with real-time map visualization.

## 🏗️ Architecture

### Backend (FastAPI)
- **GNN Model**: PyTorch Geometric traffic prediction
- **Route Calculation**: NetworkX shortest path
- **API Endpoints**: `/predict-route`, `/locations`
- **Features**: IT park shift effects, peak hour analysis

### Frontend (React + Mapbox)
- **Map Visualization**: Interactive Bangalore map
- **Route Display**: Color-coded traffic routes
- **UI Components**: Location dropdowns, prediction results
- **Real-time Updates**: Dynamic traffic classification

## 📁 Project Structure

```
traffic_module/
├── backend/
│   ├── app.py              # FastAPI server
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.js         # Main React component
│   │   ├── App.css        # Styling
│   │   ├── index.js       # React entry point
│   │   └── index.css     # Global styles
│   ├── public/
│   │   └── index.html     # HTML template
│   └── package.json       # Node dependencies
├── models/                # Trained GNN model
├── data/                 # Traffic data
└── README_WEB_APP.md      # This file
```

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js 16+
- Trained traffic model (`traffic_model.pth`)
- Mapbox Access Token

### Step 1: Setup Backend

```bash
cd traffic_module/backend

# Install Python dependencies
pip install -r requirements.txt

# Start FastAPI server
python app.py
```

Backend will run on: `http://localhost:8000`

### Step 2: Setup Frontend

```bash
cd traffic_module/frontend

# Install Node dependencies
npm install

# Set Mapbox token in src/App.js
# Replace: mapboxgl.accessToken = 'your-token-here'

# Start React development server
npm start
```

Frontend will run on: `http://localhost:3000`

## 🎯 Usage

### Web Interface
1. Open `http://localhost:3000`
2. Select **Source** location from dropdown
3. Select **Destination** location from dropdown
4. Click **"Predict Route"**
5. View:
   - Route on interactive map
   - Traffic prediction (LOW/MODERATE/HIGH)
   - Delay estimate
   - Status message

### Available Locations
- Hebbal
- Whitefield
- Electronic City
- Indiranagar
- Marathahalli
- Koramangala
- KR Puram
- Nagawara
- HSR Layout
- Manyata Tech Park

## 🎨 Traffic Color Coding

- 🟢 **GREEN**: Low traffic (0-5 min delay)
- 🟡 **YELLOW**: Moderate traffic (15 min delay)
- 🔴 **RED**: High traffic (25 min delay)

## 📡 API Endpoints

### POST /predict-route
```json
Request:
{
  "source": "Hebbal",
  "destination": "Marathahalli"
}

Response:
{
  "route": ["Hebbal", "Point 1", "Point 2", "Point 3", "Marathahalli"],
  "traffic": "HIGH",
  "delay": 25,
  "status": "Heavy congestion expected"
}
```

### GET /locations
```json
Response:
["Hebbal", "Whitefield", "Electronic City", ...]
```

## 🔧 Configuration

### Backend Settings
- Model path: `../models/traffic_model.pth`
- Data path: `../data/traffic_graph.pt`
- Node mapping: `../data/node_mapping.pkl`

### Frontend Settings
- Mapbox token: Set in `src/App.js`
- API proxy: Configured in `package.json`

## 🚀 Features

### ✅ Implemented
- [x] Route-based traffic prediction
- [x] Interactive map visualization
- [x] Color-coded traffic levels
- [x] Real-time API integration
- [x] Location dropdowns
- [x] Responsive design
- [x] NetworkX shortest path
- [x] GNN-powered predictions

### 🎯 Advanced Features
- IT park shift effects
- Peak hour traffic patterns
- Bangalore-specific locations
- Professional UI/UX
- Error handling
- Loading states

## 🛠️ Development

### Backend Development
```bash
cd backend
pip install -r requirements.txt
python app.py  # Development server
```

### Frontend Development
```bash
cd frontend
npm install
npm start  # Development server
```

### Production Deployment
```bash
# Backend
pip install gunicorn
gunicorn app:app --host 0.0.0.0 --port 8000

# Frontend
npm run build
# Deploy build/ folder to web server
```

## 🎯 Example Output

When you run the web app and select "Hebbal → Marathahalli":

```
Route: Hebbal → Point 1 → Point 2 → Point 3 → Marathahalli
Traffic: HIGH
Delay: 25 mins
Status: Heavy congestion expected
```

The map will show:
- Bangalore city view
- Red route line (HIGH traffic)
- Zoomed to route area
- Interactive controls

## 📊 Technology Stack

### Backend
- **FastAPI**: Modern Python web framework
- **PyTorch Geometric**: GNN model inference
- **NetworkX**: Graph algorithms and shortest path
- **Pandas**: Data processing
- **Uvicorn**: ASGI server

### Frontend
- **React**: Modern JavaScript framework
- **Mapbox GL JS**: Interactive maps
- **CSS3**: Responsive styling
- **Fetch API**: HTTP requests

## 🎯 Next Steps

### Potential Enhancements
- Real-time traffic data integration
- Multiple route options
- Historical traffic patterns
- Mobile app version
- Traffic alerts system
- Weather integration

### Model Improvements
- Temporal GNN (STGCN)
- More granular predictions
- Real-time sensor data
- Traffic flow optimization

## 🚦 Bengaluru Brain Integration

This web app serves as the **M1 Traffic Module** for the Bengaluru Brain Urban Predictive Intelligence System, providing:

- ✅ Real-time traffic predictions
- ✅ Route optimization
- ✅ Urban mobility insights
- ✅ GNN-powered analytics

Ready for integration with the larger Bengaluru Brain ecosystem! 🎯
