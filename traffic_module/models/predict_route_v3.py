"""
Route Prediction v3 - Uses actual OSM routes and trained GNN model (GCNConv)
Matches saved checkpoint architecture exactly
"""

import torch
import pandas as pd
import numpy as np
import pickle
import networkx as nx
from datetime import datetime
import sys
import os

# Import model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.traffic_gnn_v3 import create_model_v3

class RoutePredictorV3:
    """
    Route-based traffic prediction using trained GNN model (GCNConv architecture)
    """
    
    def __init__(self, model_path, graph_path, traffic_dataset_path):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load trained model with correct architecture
        self.model = create_model_v3(input_dim=12, hidden_dim1=64, hidden_dim2=32, hidden_dim3=16, output_dim=1)
        
        # Load checkpoint
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        
        # Handle checkpoint format - it might be a dict with model_state_dict
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
        else:
            state_dict = checkpoint
        
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        
        # Load feature normalization from checkpoint
        self.feature_mean = checkpoint.get('feature_mean', None)
        self.feature_std = checkpoint.get('feature_std', None)
        
        # Load graph
        with open(graph_path, 'rb') as f:
            self.G = pickle.load(f)
        
        # Load traffic dataset for feature mapping
        self.traffic_df = pd.read_csv(traffic_dataset_path)
        
        # Feature columns matching the saved model (12 features)
        self.feature_cols = [
            'Traffic Volume', 'Travel Time Index', 'Congestion Level',
            'Road Capacity Utilization', 'Incident Reports', 'Environmental Impact',
            'Public Transport Usage', 'Traffic Signal Compliance', 'Parking Usage',
            'Pedestrian and Cyclist Count', 'road_length_m', 'node_degree'
        ]
        
        print(f"✅ Route Predictor V3 initialized on {self.device}")
        print(f"📊 Graph: {len(self.G.nodes):,} nodes, {len(self.G.edges):,} edges")
        print(f"🗂️ Traffic samples: {len(self.traffic_df):,}")
        print(f"🎯 Model: GCNConv(12→64→32→16→1)")
    
    def get_nearest_node(self, place_name):
        """Find nearest graph node for a place name"""
        # Use location_data for known locations
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from backend.location_data import BENGALURU_LOCATIONS
        
        if place_name in BENGALURU_LOCATIONS:
            loc = BENGALURU_LOCATIONS[place_name]
            import osmnx as ox
            node = ox.distance.nearest_nodes(self.G,	loc['lon'], loc['lat'])
            return node, loc['lat'], loc['lon']
        
        # Fallback to geocoding
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="bengaluru_traffic_v3")
        location = geolocator.geocode(f"{place_name}, Bengaluru, Karnataka, India")
        if location:
            import osmnx as ox
            node = ox.distance.nearest_nodes(self.G, location.longitude, location.latitude)
            return node, location.latitude, location.longitude
        
        raise ValueError(f"Unable to find location: {place_name}")
    
    def get_route_path(self, source_node, dest_node):
        """Get shortest path between two nodes"""
        try:
            path = nx.shortest_path(self.G, source_node, dest_node, weight='length')
            return path
        except nx.NetworkXNoPath:
            raise ValueError(f"No path found between nodes {source_node} and {dest_node}")
    
    def normalize_features(self, features_dict):
        """Normalize features using saved mean/std"""
        if self.feature_mean is None or self.feature_std is None:
            # No normalization data, return raw features
            return np.array([features_dict.get(col, 0.0) for col in self.feature_cols])
        
        features = np.array([features_dict.get(col, 0.0) for col in self.feature_cols])
        return (features - self.feature_mean) / (self.feature_std + 1e-8)
    
    def predict_route(self, source, destination, hour=None, is_weekday=None, weather_code=0):
        """
        Predict traffic for a route using GNN
        
        Returns:
            dict with prediction results
        """
        # Get time context
        if hour is None:
            hour = datetime.now().hour
        if is_weekday is None:
            is_weekday = datetime.now().weekday() < 5
        
        # Get nodes
        src_node, src_lat, src_lon = self.get_nearest_node(source)
        dst_node, dst_lat, dst_lon = self.get_nearest_node(destination)
        
        # Get path
        path = self.get_route_path(src_node, dst_node)
        
        # Build node features for GNN
        from torch_geometric.data import Data
        node_features = []
        node_ids = []
        
        for node in path:
            node_ids.append(node)
            node_data = self.G.nodes[node]
            
            # Extract features matching training data
            features = {
                'Traffic Volume': node_data.get('traffic_volume', 500),
                'Travel Time Index': node_data.get('travel_time_index', 1.0),
                'Congestion Level': node_data.get('congestion_level', 0.3),
                'Road Capacity Utilization': node_data.get('capacity_utilization', 0.5),
                'Incident Reports': node_data.get('incident_reports', 0),
                'Environmental Impact': node_data.get('environmental_impact', 0.1),
                'Public Transport Usage': node_data.get('public_transport', 0.3),
                'Traffic Signal Compliance': node_data.get('signal_compliance', 0.8),
                'Parking Usage': node_data.get('parking_usage', 0.2),
                'Pedestrian and Cyclist Count': node_data.get('pedestrian_count', 10),
                'road_length_m': node_data.get('length', 100),
                'node_degree': self.G.degree(node)
            }
            
            # Add time-based features
            features['hour'] = hour
            features['is_weekday'] = 1.0 if is_weekday else 0.0
            features['weather_code'] = weather_code
            
            normalized = self.normalize_features(features)
            node_features.append(normalized)
        
        # Create PyG data
        x = torch.tensor(node_features, dtype=torch.float32).to(self.device)
        
        # Build edge index from path
        edge_index = []
        for i in range(len(path) - 1):
            edge_index.append([i, i + 1])
            edge_index.append([i + 1, i])
        
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(self.device)
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long).to(self.device)
        
        data = Data(x=x, edge_index=edge_index)
        
        # Run GNN prediction
        with torch.no_grad():
            predictions = self.model.predict(data)
        
        # Convert predictions to speeds
        # GNN outputs normalized speed (0-1), convert to actual km/h
        # Assume range 5-60 km/h
        node_speeds = (predictions.cpu().numpy().flatten() * 55 + 5).tolist()
        
        # Calculate route statistics
        total_distance = 0
        total_time = 0
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = self.G.get_edge_data(u, v)
            
            if edge_data:
                # Get the best edge
                edges = list(edge_data.values())
                best = min(edges, key=lambda d: d.get('length', 9999))
                length = best.get('length', 100)
                total_distance += length
                
                # Use predicted speed for this segment
                avg_speed = (node_speeds[i] + node_speeds[i + 1]) / 2
                segment_time = (length / 1000) / avg_speed * 60  # minutes
                total_time += segment_time
        
        distance_km = round(total_distance / 1000, 2)
        avg_speed = round((distance_km / total_time) * 60, 1) if total_time > 0 else 20.0
        predicted_time = round(total_time, 1)
        
        # Get path coordinates
        path_coords = []
        for node in path[::max(1, len(path)//50)]:
            path_coords.append([self.G.nodes[node]['y'], self.G.nodes[node]['x']])
        
        return {
            'source': source,
            'destination': destination,
            'distance_km': distance_km,
            'predicted_travel_time_min': predicted_time,
            'predicted_speed_kmh': avg_speed,
            'node_speeds': node_speeds,
            'path_coords': path_coords,
            'source_coords': [src_lat, src_lon],
            'destination_coords': [dst_lat, dst_lon],
            'model_used': 'TrafficGNNv3 (GCNConv)',
            'confidence': 0.65  # Based on test R²
        }

# Singleton predictor instance
_predictor_v3 = None

def get_predictor_v3():
    """Get or create singleton predictor instance"""
    global _predictor_v3
    if _predictor_v3 is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(base_dir, 'models', 'traffic_model_v2.pth')
        graph_path = os.path.join(base_dir, 'backend', 'data', 'bengaluru_graph.pkl')
        dataset_path = os.path.join(base_dir, 'data', 'traffic_gnn_dataset.csv')
        
        _predictor_v3 = RoutePredictorV3(model_path, graph_path, dataset_path)
    return _predictor_v3

def predict_route_v3(source, destination, hour=None, is_weekday=None, weather_code=0):
    """
    Public function to predict route using GNN v3
    
    Args:
        source: Source location name
        destination: Destination location name
        hour: Hour of day (0-23)
        is_weekday: Whether it's a weekday
        weather_code: Weather condition code
    
    Returns:
        dict with prediction results
    """
    try:
        predictor = get_predictor_v3()
        return predictor.predict_route(source, destination, hour, is_weekday, weather_code)
    except Exception as e:
        print(f"V3 prediction failed: {e}")
        raise
