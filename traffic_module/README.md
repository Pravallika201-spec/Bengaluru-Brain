# Bengaluru Brain: M1 Traffic Module

## Overview
A comprehensive traffic prediction system for Bangalore, India using Graph Neural Networks (GNN). This module implements the complete pipeline from road network data collection to congestion prediction and visualization.

## 🚀 Features
- **Road Network Analysis**: Bangalore road network using OSMnx
- **Graph Neural Networks**: GCN-based traffic congestion prediction
- **Synthetic Traffic Data**: Realistic traffic features (speed, rainfall, capacity)
- **Interactive Visualizations**: Folium-based traffic heatmaps
- **Comprehensive Pipeline**: End-to-end ML pipeline with PyTorch Geometric

## 📁 Project Structure
```
traffic_module/
├── data/                    # Raw and processed data
│   ├── bangalore.graphml    # Road network graph
│   ├── nodes.csv           # Node coordinates
│   ├── edges.csv           # Edge connections
│   ├── traffic_nodes.csv   # Traffic features
│   └── traffic_graph.pt   # PyTorch Geometric data
├── models/                  # ML models and training
│   ├── traffic_gnn.py      # GNN model architecture
│   ├── train_model.py      # Training pipeline
│   ├── predict_traffic.py  # Prediction engine
│   ├── visualize_predictions.py  # Visualization
│   └── traffic_model.pth   # Trained model checkpoint
├── notebooks/              # Jupyter notebooks
│   └── traffic_prediction_pipeline.ipynb  # Complete pipeline
├── output/                 # Results and visualizations
│   ├── traffic_predictions.csv
│   ├── traffic_heatmap.html
│   ├── training_history.png
│   └── prediction_analysis.png
└── README.md              # This file
```

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- PyTorch 2.0+
- CUDA (optional, for GPU acceleration)

### Setup
```bash
# Clone and navigate to project
cd traffic_module

# Install dependencies
pip install osmnx geopandas torch torch-geometric pandas numpy matplotlib networkx scikit-learn folium

# Run the complete pipeline
python models/train_model.py
python models/predict_traffic.py
python models/visualize_predictions.py
```

## 📊 Data Pipeline

### 1. Road Network Collection
```python
# Download Bangalore road network
G = ox.graph_from_place("Bangalore, India", network_type='drive')
ox.save_graphml(G, "bangalore.graphml")
```

### 2. Feature Engineering
- **Traffic Speed**: 20-60 km/h (inversely related to congestion)
- **Rainfall**: 0-10 mm (increases congestion)
- **Road Capacity**: 1-4 lanes (higher capacity = less congestion)
- **Target**: Congestion score (0-1)

### 3. Graph Processing
- Nodes: 154,902 road intersections
- Edges: 786,178 road connections
- Features: 3 normalized traffic features
- Target: Congestion prediction

## 🤖 Model Architecture

### TrafficGNN
```
Input (3 features) → GCN(16) → ReLU → Dropout → GCN(8) → ReLU → Dropout → FC(4) → ReLU → FC(1) → Sigmoid
```

- **Input Layer**: 3 traffic features
- **Hidden Layers**: 16 → 8 neurons with batch normalization
- **Output**: 1 congestion score (0-1)
- **Parameters**: 297 trainable parameters
- **Regularization**: Dropout (0.2) + L2 weight decay

## 📈 Performance Metrics

### Model Results
- **MSE**: 0.0299
- **RMSE**: 0.1729
- **MAE**: 0.1397
- **R²**: -0.1199
- **Training Time**: ~5 minutes (CPU)
- **Inference Time**: <2 seconds for full graph

### Training Details
- **Epochs**: 50 (early stopping at 16)
- **Optimizer**: Adam (lr=0.001, weight_decay=1e-4)
- **Loss**: MSE with learning rate scheduling
- **Split**: 80% train, 20% validation

## 🗺️ Visualizations

### Interactive Maps
1. **Traffic Heatmap**: Color-coded congestion intensity
2. **Congestion Colormap**: Node-level traffic predictions
3. **Top Congested Areas**: Highlighted high-congestion zones

### Analysis Plots
1. **Training History**: Loss curves over epochs
2. **Prediction Analysis**: Predicted vs actual congestion
3. **Error Distribution**: Residual analysis
4. **Feature Relationships**: Traffic speed vs congestion

## 🚀 Usage Examples

### Quick Start
```python
# Load trained model and predict
from models.predict_traffic import TrafficPredictor

predictor = TrafficPredictor(
    model_path='models/traffic_model.pth',
    data_path='data/traffic_graph.pt',
    scaler_path='data/feature_scaler.pkl',
    node_mapping_path='data/node_mapping.pkl'
)

# Get top congested areas
top_congested = predictor.predict_top_congested(top_k=10)
print(top_congested)
```

### Custom Predictions
```python
# Load model
from models.traffic_gnn import create_model
import torch

model = create_model()
checkpoint = torch.load('models/traffic_model.pth', weights_only=False)
model.load_state_dict(checkpoint['model_state_dict'])

# Make predictions
data = torch.load('data/traffic_graph.pt', weights_only=False)
predictions = model.predict(data)
```

## 📋 Deliverables

### Core Files
- ✅ `bangalore.graphml` - Road network data
- ✅ `traffic_graph.pt` - PyTorch Geometric format
- ✅ `traffic_model.pth` - Trained GNN model
- ✅ `traffic_predictions.csv` - All predictions
- ✅ Interactive HTML maps
- ✅ Analysis plots and documentation

### Performance Targets
- ✅ **Nodes processed**: 154,902
- ✅ **Inference time**: <2 seconds
- ⏳ **Prediction accuracy**: Needs improvement (current R²: -0.12)
- ⏳ **False positive rate**: To be optimized in Phase 3

## 🔮 Next Steps (Phase 3 & 4)

### Phase 3 - Enhanced Features
1. **IT Shift Dataset**: Add office hours and tech park data
2. **External APIs**:
   - IMD rainfall forecasts
   - KSNDMC flood risk data
   - BESCOM power load
   - BBMP event calendar
   - Citizen incident reports

### Phase 4 - Advanced Architecture
1. **Temporal GNN**: Upgrade to STGCN or GraphWaveNet
2. **Sequence Prediction**: 2-hour ahead forecasting
3. **Performance Targets**:
   - >75% prediction accuracy
   - <20% false positives
   - <2 minutes inference time

## 🤝 Contributing

### Development Workflow
1. **Environment**: Use the provided conda/environment.yml
2. **Data**: Process new data in `data/` directory
3. **Models**: Update architectures in `models/`
4. **Experiments**: Track results in `notebooks/`

### Code Style
- Follow PEP 8 guidelines
- Use type hints for functions
- Add comprehensive docstrings
- Include unit tests for new features

## 📄 License

This project is part of the Bengaluru Brain initiative. See LICENSE file for details.

## 📞 Contact

For questions or contributions:
- Project Repository: [GitHub link]
- Documentation: [Wiki link]
- Issues: [Issues link]

---

**Status**: ✅ Phase 1 & 2 Complete | 🔄 Phase 3 In Progress | ⏳ Phase 4 Planned
