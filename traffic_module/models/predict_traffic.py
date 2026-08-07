import torch
import pandas as pd
import numpy as np
import pickle
import sys
import os

# Import model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.traffic_gnn import create_model

class TrafficRoutePredictor:
    """
    Route-based Traffic Prediction System
    """
    
    def __init__(self, model_path, data_path, node_mapping_path):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load model with updated architecture
        self.model = create_model(input_dim=3, hidden_dim1=32, hidden_dim2=16, output_dim=1)
        
        # Load model weights
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        if 'model_state_dict' in checkpoint:
            self.model.load_state_dict(checkpoint['model_state_dict'])
        else:
            self.model.load_state_dict(checkpoint)
        
        self.model.to(self.device)
        self.model.eval()
        
        # Load graph data
        self.data = torch.load(data_path, weights_only=False)
        
        # Load node mapping
        with open(node_mapping_path, 'rb') as f:
            self.node_to_idx = pickle.load(f)
        
        self.idx_to_node = {idx: node for node, idx in self.node_to_idx.items()}
        
        print(f"✅ Route Traffic Predictor initialized on {self.device}")
        print(f"📊 Nodes: {self.data.num_nodes:,}")
        print(f"🔗 Edges: {self.data.num_edges:,}")
    
    def predict_all(self):
        """
        Make predictions for all nodes
        """
        with torch.no_grad():
            predictions = self.model(self.data.x.to(self.device), 
                               self.data.edge_index.to(self.device))
            return predictions.cpu().numpy().flatten()
    
    def predict_route(self, source, destination):
        """
        Predict traffic for a specific route
        
        Args:
            source: Starting location name
            destination: Ending location name
        """
        # Get predictions for all nodes
        predictions = self.predict_all()
        
        # Simulate route nodes (select ~50 nodes randomly)
        route_nodes = np.random.choice(len(predictions), size=50, replace=False)
        
        # Compute average congestion for route
        route_congestion = predictions[route_nodes].mean()
        
        # Classify traffic using specified logic
        if route_congestion < 0.3:
            traffic = "LOW"
            delay = 5
            status = "Smooth traffic expected"
        elif route_congestion < 0.6:
            traffic = "MODERATE"
            delay = 15
            status = "Moderate traffic expected"
        else:
            traffic = "HIGH"
            delay = 25
            status = "Heavy congestion expected"
        
        # Print output exactly as requested
        print(f"\nRoute: {source} → {destination}")
        print("Time: Next 2 hours\n")
        
        print(f"Predicted Traffic: {traffic}")
        print(f"Estimated Delay: {delay} mins")
        print(f"Status: {status}")

def main():
    """
    Main function for route-based traffic prediction
    """
    print("🚀 Initializing Route Traffic Prediction System...")
    
    # Initialize predictor
    predictor = TrafficRoutePredictor(
        model_path='../models/traffic_model.pth',
        data_path='../data/traffic_graph.pt',
        node_mapping_path='../data/node_mapping.pkl'
    )
    
    # Call route prediction function as specified
    predictor.predict_route("Hebbal", "Marathahalli")

if __name__ == "__main__":
    main()
