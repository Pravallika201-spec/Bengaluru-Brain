"""
Traffic GNN v3 - Matches saved checkpoint architecture (GCNConv)
Based on actual saved model: traffic_model_v2.pth
Architecture: GCNConv(12, 64) -> GCNConv(64, 32) -> GCNConv(32, 16) -> Linear(16, 1)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv
import numpy as np
class TrafficGNNv3(nn.Module):    
    def __init__(self, input_dim=12, hidden_dim1=64, hidden_dim2=32, hidden_dim3=16, output_dim=1):
        super(TrafficGNNv3, self).__init__()
        self.conv1 = GCNConv(input_dim, hidden_dim1)
        self.conv2 = GCNConv(hidden_dim1, hidden_dim2)
        self.conv3 = GCNConv(hidden_dim2, hidden_dim3)
        self.output = nn.Linear(hidden_dim3, output_dim)
    def forward(self, x, edge_index, batch=None):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.conv2(x, edge_index)
        x = F.relu(x)
        x = self.conv3(x, edge_index)
        x = F.relu(x)
        x = self.output(x)
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

def create_model_v3(input_dim=12, hidden_dim1=64, hidden_dim2=32, hidden_dim3=16, output_dim=1):
    """
    Create a TrafficGNNv3 model instance matching saved checkpoint.
    
    Args:
        input_dim: Number of input features (12 for saved model)
        hidden_dim1: Size of first hidden layer (64)
        hidden_dim2: Size of second hidden layer (32)
        hidden_dim3: Size of third hidden layer (16)
        output_dim: Size of output layer (1)
        
    Returns:
        TrafficGNNv3 model instance
    """
    model = TrafficGNNv3(input_dim, hidden_dim1, hidden_dim2, hidden_dim3, output_dim)
    return model

def count_parameters(model):
    """
    Count the number of trainable parameters in the model.
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

if __name__ == "__main__":
    # Test the model
    print("Testing TrafficGNNv3 model...")
    
    # Create a model matching saved checkpoint
    model = create_model_v3()
    print(f"Model created with {count_parameters(model)} trainable parameters")
    
    # Create dummy data
    num_nodes = 1000
    num_edges = 2000
    input_dim = 12
    
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
