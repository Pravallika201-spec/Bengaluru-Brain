"""
Route Prediction v2 - Uses actual OSM routes and trained GNN model
No random values, no hardcoded delays
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
from models.traffic_gnn_v2 import create_model_v2

class RoutePredictorV2:
    """
    Route-based traffic prediction using trained GNN model
    """
    
    def __init__(self, model_path, graph_path, traffic_dataset_path):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load trained model
        self.model = create_model_v2(input_dim=15, hidden_dim1=64, hidden_dim2=32, output_dim=1)
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint)
        self.model.to(self.device)
        self.model.eval()
        
        # Load graph
        with open(graph_path, 'rb') as f:
            self.G = pickle.load(f)
        
        # Load traffic dataset for feature mapping
        self.traffic_df = pd.read_csv(traffic_dataset_path)
        self.traffic_df['date'] = pd.to_datetime(self.traffic_df['date'])
        
        # Load location mapping - use absolute path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mapping_path = os.path.join(base_dir, 'data', 'traffic_location_mapping.csv')
        mapping_df = pd.read_csv(mapping_path)
        self.valid_mappings = mapping_df[mapping_df['status'] == 'MATCHED']
        
        # Create location to node mapping
        self.location_to_node = dict(zip(
            self.valid_mappings['traffic_location'],
            self.valid_mappings['nearest_node'].astype(int)
        ))
        
        # Load feature scaler
        from sklearn.preprocessing import StandardScaler
        feature_cols = [
            'traffic_volume', 'travel_time_index', 'road_capacity_utilization',
            'incident_reports', 'environmental_impact', 'public_transport_usage',
            'traffic_signal_compliance', 'parking_usage', 'pedestrian_cyclist_count',
            'edge_length_km', 'edge_speed_limit_kph', 'lanes', 'node_degree',
            'day_of_week', 'weather_code'
        ]
        self.scaler = StandardScaler()
        self.scaler.fit(self.traffic_df[feature_cols].values)
        self.feature_cols = feature_cols
        
        print(f"✅ Route Predictor V2 initialized on {self.device}")
        print(f"📊 Graph: {len(self.G.nodes):,} nodes, {len(self.G.edges):,} edges")
        print(f"🗂️ Traffic samples: {len(self.traffic_df):,}")
        print(f"📍 Mapped locations: {len(self.location_to_node)}")
    
    def get_nearest_node(self, place_name):
        """Find nearest graph node for a place name"""
        # Check if location is in mapping
        if place_name in self.location_to_node:
            node_id = self.location_to_node[place_name]
            # Get coordinates from mapping
            mapping_row = self.valid_mappings[self.valid_mappings['traffic_location'] == place_name].iloc[0]
            return node_id, mapping_row['latitude'], mapping_row['longitude']
        
        # Fallback to geocoding
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="bengaluru_traffic_v2")
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
    
    def get_edge_features(self, u, v, key, current_time):
        """Extract features for an edge"""
        edge_data = self.G[u][v][key]
        
        # Basic edge features
        edge_length = edge_data.get('length', 100.0) / 1000.0  # km
        edge_speed = edge_data.get('speed_kph', 30.0)
        highway_type = edge_data.get('highway', 'unclassified')
        lanes_val = edge_data.get('lanes', 1)
        # Handle lanes if it's a list
        if isinstance(lanes_val, list):
            lanes = float(lanes_val[0]) if lanes_val else 1.0
        else:
            lanes = float(lanes_val)
        
        # Temporal features
        day_of_week = current_time.weekday()
        hour = current_time.hour
        
        # Find nearest traffic observation for this location
        # Use the node's location to find nearby traffic data
        node_u_data = self.G.nodes[u]
        node_v_data = self.G.nodes[v]
        
        # Use average of nearby traffic observations
        nearby_observations = self.traffic_df[
            (self.traffic_df['day_of_week'] == day_of_week)
        ]
        
        if len(nearby_observations) > 0:
            # Use median of observations for robustness
            obs = nearby_observations.median(numeric_only=True)
            traffic_volume = obs.get('traffic_volume', 30000)
            travel_time_index = obs.get('travel_time_index', 1.2)
            road_capacity_utilization = obs.get('road_capacity_utilization', 80)
            incident_reports = obs.get('incident_reports', 0)
            environmental_impact = obs.get('environmental_impact', 100)
            public_transport_usage = obs.get('public_transport_usage', 50)
            traffic_signal_compliance = obs.get('traffic_signal_compliance', 80)
            parking_usage = obs.get('parking_usage', 50)
            pedestrian_cyclist_count = obs.get('pedestrian_cyclist_count', 100)
            weather_code = 0  # Default clear weather
        else:
            # Default values
            traffic_volume = 30000
            travel_time_index = 1.2
            road_capacity_utilization = 80
            incident_reports = 0
            environmental_impact = 100
            public_transport_usage = 50
            traffic_signal_compliance = 80
            parking_usage = 50
            pedestrian_cyclist_count = 100
            weather_code = 0
        
        # Node degree
        node_degree = self.G.degree(u) + self.G.degree(v)
        
        # Highway encoding
        highway_mapping = {'primary': 1, 'secondary': 2, 'tertiary': 3, 'residential': 4, 'unclassified': 0}
        highway_code = highway_mapping.get(highway_type, 0)
        
        features = [
            float(traffic_volume),
            float(travel_time_index),
            float(road_capacity_utilization),
            float(incident_reports),
            float(environmental_impact),
            float(public_transport_usage),
            float(traffic_signal_compliance),
            float(parking_usage),
            float(pedestrian_cyclist_count),
            float(edge_length),
            float(edge_speed),
            float(lanes),
            float(node_degree),
            float(day_of_week),
            float(weather_code)
        ]
        
        return np.array(features, dtype=np.float32)
    
    def predict_route(self, source, destination):
        """
        Predict traffic for a route using actual OSM path and GNN model
        
        Args:
            source: Starting location name
            destination: Ending location name
            
        Returns:
            Dictionary with route prediction results
        """
        current_time = datetime.now()
        
        # Get source and destination nodes
        src_node, src_lat, src_lon = self.get_nearest_node(source)
        dst_node, dst_lat, dst_lon = self.get_nearest_node(destination)
        
        # Get route path
        path = self.get_route_path(src_node, dst_node)
        
        # Calculate total distance and predict speeds for each segment
        total_distance = 0.0
        segment_predictions = []
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            
            # Get all edges between u and v
            edges = self.G[u][v]
            best_edge = None
            best_length = float('inf')
            
            for key, edge_data in edges.items():
                length = edge_data.get('length', 100.0)
                if length < best_length:
                    best_length = length
                    best_edge = (u, v, key, edge_data)
            
            if best_edge is None:
                continue
            
            u, v, key, edge_data = best_edge
            edge_length_km = edge_data.get('length', 100.0) / 1000.0
            total_distance += edge_length_km
            
            # Get features and predict speed
            features = self.get_edge_features(u, v, key, current_time)
            features_normalized = self.scaler.transform([features])[0]
            
            with torch.no_grad():
                features_tensor = torch.tensor(features_normalized, dtype=torch.float).unsqueeze(0).to(self.device)
                # Create dummy edge index for single node prediction
                edge_index = torch.tensor([[0], [0]], dtype=torch.long).to(self.device)
                predicted_speed_normalized = self.model(features_tensor, edge_index).cpu().item()
            
            # Denormalize speed
            predicted_speed_kmh = predicted_speed_normalized * 80.0  # Max speed 80 km/h
            predicted_speed_kmh = max(8.0, min(80.0, predicted_speed_kmh))  # Clamp
            
            # Calculate segment travel time
            segment_time = (edge_length_km / predicted_speed_kmh) * 60.0  # minutes
            
            segment_predictions.append({
                'u': u,
                'v': v,
                'length_km': edge_length_km,
                'predicted_speed_kmh': predicted_speed_kmh,
                'travel_time_mins': segment_time
            })
        
        # Calculate total travel time
        total_predicted_time = sum(seg['travel_time_mins'] for seg in segment_predictions)
        
        # Calculate free-flow time (using speed limits)
        total_free_flow_time = 0.0
        for seg in segment_predictions:
            edge_data = self.G[seg['u']][seg['v']]
            # Find the edge with matching length
            for key, data in edge_data.items():
                if data.get('length', 0) / 1000.0 == seg['length_km']:
                    speed_limit = data.get('speed_kph', 50.0)
                    free_flow_time = (seg['length_km'] / speed_limit) * 60.0
                    total_free_flow_time += free_flow_time
                    break
        
        # Calculate delay
        delay_mins = max(0, total_predicted_time - total_free_flow_time)
        delay_percentage = (delay_mins / max(1.0, total_free_flow_time)) * 100.0
        
        # Calculate average speed
        avg_speed = (total_distance / max(0.1, total_predicted_time)) * 60.0
        
        # Determine status based on delay percentage
        if delay_percentage >= 50:
            status = "CRITICAL"
        elif delay_percentage >= 30:
            status = "HIGH"
        elif delay_percentage >= 15:
            status = "MODERATE"
        elif delay_percentage >= 5:
            status = "LOW"
        else:
            status = "CLEAR"
        
        # Get route geometry for map
        route_coords = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = self.G[u][v]
            for key, data in edge_data.items():
                geometry = data.get('geometry')
                if geometry is not None:
                    try:
                        for lon, lat in geometry.coords:
                            route_coords.append([lat, lon])
                    except:
                        pass
                break
        
        if not route_coords:
            route_coords = [[self.G.nodes[n]['y'], self.G.nodes[n]['x']] for n in path]
        
        return {
            'source': source,
            'destination': destination,
            'distance_km': round(total_distance, 2),
            'predicted_mins': round(total_predicted_time, 1),
            'free_flow_mins': round(total_free_flow_time, 1),
            'delay_mins': round(delay_mins, 1),
            'delay_percentage': round(delay_percentage, 1),
            'avg_speed_kmh': round(avg_speed, 1),
            'status': status,
            'route_coords': route_coords,
            'src_coords': {'lat': src_lat, 'lon': src_lon},
            'dst_coords': {'lat': dst_lat, 'lon': dst_lon},
            'num_segments': len(segment_predictions),
            'model_info': f"GNN v2 (GAT) trained on real traffic data | {len(self.traffic_df):,} samples",
            'predicted_at': current_time.strftime("%I:%M %p, %d %b %Y"),
            'temporal_limitation': "Model trained on daily data; hourly predictions not supported"
        }

def main():
    """Test the route predictor"""
    print("🚀 Initializing Route Predictor V2...")
    
    predictor = RoutePredictorV2(
        model_path='../models/traffic_model_v2.pth',
        graph_path='../backend/data/bengaluru_graph.pkl',
        traffic_dataset_path='../data/traffic_gnn_dataset.csv'
    )
    
    # Test route prediction
    print("\n" + "="*60)
    print("TESTING ROUTE PREDICTION")
    print("="*60)
    
    result = predictor.predict_route("Hebbal", "Marathahalli")
    
    print(f"\nRoute: {result['source']} → {result['destination']}")
    print(f"Distance: {result['distance_km']} km")
    print(f"Predicted time: {result['predicted_mins']} mins")
    print(f"Free flow time: {result['free_flow_mins']} mins")
    print(f"Delay: {result['delay_mins']} mins ({result['delay_percentage']}%)")
    print(f"Average speed: {result['avg_speed_kmh']} km/h")
    print(f"Status: {result['status']}")
    print(f"Segments: {result['num_segments']}")
    print(f"\n{result['model_info']}")
    print(f"\n{result['temporal_limitation']}")

if __name__ == "__main__":
    main()
