"""
Backend Traffic Predictor V2 - Integration with trained GNN model
Uses real traffic data and actual OSM routes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.predict_route_v2 import RoutePredictorV2

# Global predictor instance
_predictor = None

def get_predictor():
    """Get or initialize the route predictor"""
    global _predictor
    if _predictor is None:
        # Use absolute paths based on backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(backend_dir)
        
        _predictor = RoutePredictorV2(
            model_path=os.path.join(project_root, 'models', 'traffic_model_v2.pth'),
            graph_path=os.path.join(backend_dir, 'data', 'bengaluru_graph.pkl'),
            traffic_dataset_path=os.path.join(project_root, 'data', 'traffic_gnn_dataset.csv')
        )
    return _predictor

def predict_route_v2(source, destination):
    """
    Predict route using trained GNN model
    
    Args:
        source: Source location name
        destination: Destination location name
        
    Returns:
        Dictionary with prediction results compatible with frontend
    """
    try:
        predictor = get_predictor()
        result = predictor.predict_route(source, destination)
        
        # Convert to frontend-compatible format
        return {
            'distance_km': result['distance_km'],
            'predicted_mins': result['predicted_mins'],
            'free_flow_mins': result['free_flow_mins'],
            'delay_mins': result['delay_mins'],
            'delay_percentage': result['delay_percentage'],
            'avg_speed_kmh': result['avg_speed_kmh'],
            'status': result['status'],
            'route_coords': result['route_coords'],
            'src_coords': result['src_coords'],
            'dst_coords': result['dst_coords'],
            'traffic_score': int(result['delay_percentage']),  # Use delay as traffic score
            'confidence': 0.7,  # Fixed confidence based on model performance
            'model_info': result['model_info'],
            'temporal_limitation': result['temporal_limitation'],
            # Add forecast placeholder (not supported with daily data)
            'forecast_2hr': {
                'predicted_mins': result['predicted_mins'],
                'delay_mins': result['delay_mins'],
                'status': result['status'],
                'note': 'Hourly forecast not available - model trained on daily data'
            }
        }
    except Exception as e:
        print(f"V2 prediction failed: {e}")
        raise e
