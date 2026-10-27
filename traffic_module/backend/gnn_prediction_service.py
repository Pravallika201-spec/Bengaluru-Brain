"""
GNN Prediction Service - Unified GNN inference using TrafficGNNv3
Loads the existing checkpoint with correct architecture (GCNConv, 12 features)
"""

import torch
import numpy as np
import pickle
import os
import sys
from typing import Dict, Optional

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.traffic_gnn_v3 import create_model_v3

class GNNPredictionService:
    """
    Singleton service for GNN-based traffic prediction
    Uses TrafficGNNv3 architecture matching the saved checkpoint
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GNNPredictionService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.feature_mean = None
        self.feature_std = None
        self.feature_columns = None
        self.G = None
        self.checkpoint_loaded = False
        
        # Paths
        self.model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                      'models', 'traffic_model_v2.pth')
        self.graph_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                      'data', 'bengaluru_graph.pkl')
        
        print("GNN Prediction Service initialized")
        self._initialized = True
    
    def load_checkpoint(self) -> bool:
        """Load the GNN checkpoint with correct architecture"""
        if self.checkpoint_loaded:
            return True
        
        try:
            print(f"Loading checkpoint from: {self.model_path}")
            
            # Load checkpoint
            checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
            
            # Extract model state dict
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                state_dict = checkpoint['model_state_dict']
                self.feature_mean = checkpoint.get('feature_mean')
                self.feature_std = checkpoint.get('feature_std')
                self.feature_columns = checkpoint.get('feature_columns')
                input_dim = checkpoint.get('input_dim', 12)
            else:
                state_dict = checkpoint
                input_dim = 12
            
            # Create model with correct architecture (GCNConv, 12 features)
            self.model = create_model_v3(input_dim=input_dim, hidden_dim1=64, hidden_dim2=32, hidden_dim3=16, output_dim=1)
            
            # Load weights
            self.model.load_state_dict(state_dict)
            self.model.to(self.device)
            self.model.eval()
            
            # Load graph
            if os.path.exists(self.graph_path):
                with open(self.graph_path, 'rb') as f:
                    self.G = pickle.load(f)
                print(f"SUCCESS: Graph loaded: {len(self.G.nodes)} nodes, {len(self.G.edges)} edges")
            else:
                print(f"WARNING: Graph file not found: {self.graph_path}")
            
            self.checkpoint_loaded = True
            print(f"SUCCESS: GNN checkpoint loaded successfully")
            print(f"   Architecture: GCNConv({input_dim}->64->32->16->1)")
            print(f"   Device: {self.device}")
            
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to load GNN checkpoint: {e}")
            return False
    
    def normalize_features(self, features_dict: Dict) -> np.ndarray:
        """
        Normalize features using saved mean/std from checkpoint
        
        Args:
            features_dict: Dictionary with feature names as keys
            
        Returns:
            Normalized feature array
        """
        if self.feature_columns is None:
            # Use default feature order if not in checkpoint
            self.feature_columns = [
                'Traffic Volume', 'Travel Time Index', 'Congestion Level',
                'Road Capacity Utilization', 'Incident Reports', 'Environmental Impact',
                'Public Transport Usage', 'Traffic Signal Compliance', 'Parking Usage',
                'Pedestrian and Cyclist Count', 'road_length_m', 'node_degree'
            ]
        
        # Extract features in correct order
        features = np.array([features_dict.get(col, 0.0) for col in self.feature_columns])
        
        # Normalize if mean/std available
        if self.feature_mean is not None and self.feature_std is not None:
            mean_array = np.array([self.feature_mean.get(col, 0.0) for col in self.feature_columns])
            std_array = np.array([self.feature_std.get(col, 1.0) for col in self.feature_columns])
            features = (features - mean_array) / (std_array + 1e-8)
        
        return features
    
    def predict_speed(self, route_coords, incident_count=0, weather_multiplier=1.0) -> Dict:
        """
        Predict traffic speed for a route using GNN
        
        Args:
            route_coords: List of [lat, lon] coordinates
            incident_count: Number of incidents on route
            weather_multiplier: Weather impact multiplier
            
        Returns:
            Dictionary with prediction results
        """
        if not self.load_checkpoint():
            # Fallback if checkpoint fails
            return {
                "predicted_speed_kmh": 25.0,
                "confidence": 0.0,
                "source": "GNN_UNAVAILABLE",
                "error": "Checkpoint load failed"
            }
        
        try:
            # Route-sampled GNN inference does not require the OSM pickle graph.
            if route_coords and len(route_coords) > 0:
                return self._predict_with_graph(route_coords, incident_count, weather_multiplier)
            return self._predict_simple(incident_count, weather_multiplier)
                
        except Exception as e:
            print(f"GNN prediction error: {e}")
            return {
                "predicted_speed_kmh": 25.0,
                "confidence": 0.0,
                "source": "GNN_ERROR",
                "error": str(e)
            }
    
    def _predict_with_graph(self, route_coords, incident_count, weather_multiplier) -> Dict:
        """Predict using graph structure and sampled route coordinates"""
        from torch_geometric.data import Data
        
        # Sample points along route (15-20 points for robust GNN representation)
        num_samples = min(20, max(2, len(route_coords)))
        sample_indices = np.linspace(0, len(route_coords) - 1, num_samples, dtype=int)
        sample_coords = [route_coords[i] for i in sample_indices]
        
        node_features = []
        for i in range(len(sample_coords)):
            lat, lon = sample_coords[i]
            # Calculate distance to next sample point in meters
            if i < len(sample_coords) - 1:
                next_lat, next_lon = sample_coords[i + 1]
                lat1_rad, lon1_rad = np.radians(lat), np.radians(lon)
                lat2_rad, lon2_rad = np.radians(next_lat), np.radians(next_lon)
                dlat = lat2_rad - lat1_rad
                dlon = lon2_rad - lon1_rad
                a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
                c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
                dist_m = float(6371000.0 * c)
            else:
                dist_m = 250.0
            
            features = self._extract_node_features(lat, lon, incident_count, weather_multiplier, dist_m)
            normalized = self.normalize_features(features)
            node_features.append(normalized)
        
        if not node_features:
            return self._predict_simple(incident_count, weather_multiplier)
        
        node_features_array = np.array(node_features, dtype=np.float32)
        x = torch.from_numpy(node_features_array).to(self.device)
        
        # Build bidirectional sequential edge index
        edge_index = []
        for i in range(len(node_features) - 1):
            edge_index.append([i, i + 1])
            edge_index.append([i + 1, i])
        
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(self.device)
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long).to(self.device)
        
        data = Data(x=x, edge_index=edge_index)
        
        with torch.no_grad():
            predictions = self.model.predict(data)
        
        raw_values = predictions.cpu().numpy().flatten()
        # Checkpoint target is normalized speed (0-1) in train_model_v2;
        # some saved weights already emit km/h-scale values. Convert only when needed.
        if len(raw_values) > 0 and float(np.nanmax(np.abs(raw_values))) <= 1.5:
            converted = (raw_values * 55.0) + 5.0
            conversion = "normalized_to_kmh"
        else:
            converted = raw_values
            conversion = "checkpoint_kmh"
        node_speeds = [float(np.clip(s, 5.0, 80.0)) for s in converted]
        avg_speed = float(np.mean(node_speeds)) if node_speeds else 30.0
        
        return {
            "predicted_speed_kmh": round(avg_speed, 2),
            "confidence": 0.65,
            "source": "TrafficGNNv3",
            "checkpoint": os.path.basename(self.model_path),
            "output_conversion": conversion,
            "raw_output_mean": round(float(np.mean(raw_values)), 4) if len(raw_values) else None,
            "node_speeds": [round(s, 2) for s in node_speeds]
        }
    
    def _predict_simple(self, incident_count, weather_multiplier) -> Dict:
        """Simple prediction without graph"""
        base_speed = 35.0
        incident_penalty = min(15.0, incident_count * 5.0)
        weather_penalty = (weather_multiplier - 1.0) * 10.0
        
        predicted_speed = max(10.0, base_speed - incident_penalty - weather_penalty)
        
        return {
            "predicted_speed_kmh": round(float(predicted_speed), 2),
            "confidence": 0.3,
            "source": "GNN_SIMPLE_FALLBACK"
        }
    
    def _extract_node_features(self, lat, lon, incident_count, weather_multiplier, dist_m=250.0) -> Dict:
        """Extract features for a node matching the checkpoint training distribution"""
        features = {
            'Traffic Volume': 29064.0,
            'Travel Time Index': 1.375,
            'Congestion Level': 80.97,
            'Road Capacity Utilization': 92.35,
            'Incident Reports': float(incident_count),
            'Environmental Impact': 108.13 * weather_multiplier,
            'Public Transport Usage': 45.02,
            'Traffic Signal Compliance': 79.61,
            'Parking Usage': 75.52,
            'Pedestrian and Cyclist Count': 113.31,
            'road_length_m': max(30.0, min(2000.0, float(dist_m))),
            'node_degree': 4.0
        }
        
        return features


# Singleton instance
_gnn_service = None

def get_gnn_service() -> GNNPredictionService:
    """Get or create the GNN prediction service singleton"""
    global _gnn_service
    if _gnn_service is None:
        _gnn_service = GNNPredictionService()
    return _gnn_service
