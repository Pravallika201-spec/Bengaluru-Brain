"""
Traffic GNN v2 - Architecture based on real traffic dataset features
Uses actual observed traffic data from Banglore_traffic_Dataset.csv
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, GATConv, global_mean_pool
from torch_geometric.data import Data, Batch
import numpy as np

class TrafficGNNv2(nn.Module):
    """
    Graph Neural Network for traffic speed prediction using real traffic data.
    
    Architecture:
    - Input: 15 features (traffic volume, speed, congestion, weather, road attributes, etc.)
    - Hidden layers: 64 -> 32
    - Output: 1 (normalized speed prediction)
    
    Target: Normalized average speed (0-1 range)
    """
    
    def __init__(self, input_dim=15, hidden_dim1=64, hidden_dim2=32, output_dim=1, dropout=0.3):
        super(TrafficGNNv2, self).__init__()
        
        # Graph convolution layers (GAT for attention mechanism)
        self.conv1 = GATConv(input_dim, hidden_dim1, heads=4, dropout=dropout)
        self.conv2 = GATConv(hidden_dim1 * 4, hidden_dim2, heads=2, dropout=dropout)
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_dim2 * 2, hidden_dim2)
        self.fc2 = nn.Linear(hidden_dim2, output_dim)
        
        # Dropout for regularization
        self.dropout = nn.Dropout(dropout)
        
        # Batch normalization
        self.bn1 = nn.BatchNorm1d(hidden_dim1 * 4)
        self.bn2 = nn.BatchNorm1d(hidden_dim2 * 2)
        self.bn3 = nn.BatchNorm1d(hidden_dim2)
        
    def forward(self, x, edge_index, batch=None):
        """
        Forward pass of the GNN.
        
        Args:
            x: Node features [num_nodes, input_dim]
            edge_index: Edge connectivity [2, num_edges]
            batch: Batch vector (optional, for mini-batch training)
            
        Returns:
            Predicted normalized speeds [num_nodes, 1]
        """
        # First graph convolution with attention
        x = self.conv1(x, edge_index)
        x = self.bn1(x)
        x = F.elu(x)
        x = self.dropout(x)
        
        # Second graph convolution with attention
        x = self.conv2(x, edge_index)
        x = self.bn2(x)
        x = F.elu(x)
        x = self.dropout(x)
        
        # If batch is provided, compute graph-level representation
        if batch is not None:
            x = global_mean_pool(x, batch)
        else:
            # For single graph, keep node-level predictions
            pass
        
        # Fully connected layers
        x = self.fc1(x)
        x = self.bn3(x)
        x = F.elu(x)
        x = self.dropout(x)
        
        # Output layer
        x = self.fc2(x)
        
        # Apply sigmoid to ensure output is between 0 and 1 (normalized speed)
        x = torch.sigmoid(x)
        
        return x
    
    def predict(self, data):
        """
        Make predictions on the given data.
        
        Args:
            data: PyTorch Geometric Data object
            
        Returns:
            Predicted normalized speeds
        """
        self.eval()
        with torch.no_grad():
            return self.forward(data.x, data.edge_index)

def create_model_v2(input_dim=15, hidden_dim1=64, hidden_dim2=32, output_dim=1, dropout=0.3):
    """
    Create a TrafficGNNv2 model instance.
    
    Args:
        input_dim: Number of input features
        hidden_dim1: Size of first hidden layer
        hidden_dim2: Size of second hidden layer
        output_dim: Size of output layer
        dropout: Dropout rate
        
    Returns:
        TrafficGNNv2 model instance
    """
    model = TrafficGNNv2(input_dim, hidden_dim1, hidden_dim2, output_dim, dropout)
    return model

def count_parameters(model):
    """
    Count the number of trainable parameters in the model.
    
    Args:
        model: PyTorch model
        
    Returns:
        Number of trainable parameters
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

if __name__ == "__main__":
    # Test the model
    print("Testing TrafficGNNv2 model...")
    
    # Create a model
    model = create_model_v2()
    print(f"Model created with {count_parameters(model)} trainable parameters")
    
    # Create dummy data
    num_nodes = 1000
    num_edges = 2000
    input_dim = 15
    
    # Random node features
    x = torch.randn(num_nodes, input_dim)
    
    # Random edges
    edge_index = torch.randint(0, num_nodes, (2, num_edges))
    
    # Test forward pass
    model.eval()
    with torch.no_grad():
        output = model(x, edge_index)
    
    print(f"Input shape: {x.shape}")
    print(f"Edge index shape: {edge_index.shape}")
    print(f"Output shape: {output.shape}")
    print(f"Output range: [{output.min().item():.3f}, {output.max().item():.3f}]")
    
    print("Model test completed successfully!")
