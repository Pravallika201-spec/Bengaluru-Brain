import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, global_mean_pool
from torch_geometric.data import Data, Batch
import numpy as np

class TrafficGNN(nn.Module):
    """
    Graph Neural Network for traffic congestion prediction.
    
    Architecture:
    - Input: 3 features (traffic_speed, street_count, peak_hour_factor)
    - Hidden layers: 32, 16
    - Output: 1 (congestion score)
    """
    
    def __init__(self, input_dim=3, hidden_dim1=32, hidden_dim2=16, output_dim=1, dropout=0.2):
        super(TrafficGNN, self).__init__()
        
        # Graph convolution layers
        self.conv1 = GCNConv(input_dim, hidden_dim1)
        self.conv2 = GCNConv(hidden_dim1, hidden_dim2)
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_dim2, hidden_dim2 // 2)
        self.fc2 = nn.Linear(hidden_dim2 // 2, output_dim)
        
        # Dropout for regularization
        self.dropout = nn.Dropout(dropout)
        
        # Batch normalization
        self.bn1 = nn.BatchNorm1d(hidden_dim1)
        self.bn2 = nn.BatchNorm1d(hidden_dim2)
        self.bn3 = nn.BatchNorm1d(hidden_dim2 // 2)
        
    def forward(self, x, edge_index, batch=None):
        """
        Forward pass of the GNN.
        
        Args:
            x: Node features [num_nodes, input_dim]
            edge_index: Edge connectivity [2, num_edges]
            batch: Batch vector (optional, for mini-batch training)
            
        Returns:
            Predicted congestion scores [num_nodes, 1] or [batch_size, 1]
        """
        # First graph convolution
        x = self.conv1(x, edge_index)
        x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout(x)
        
        # Second graph convolution
        x = self.conv2(x, edge_index)
        x = self.bn2(x)
        x = F.relu(x)
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
        x = F.relu(x)
        x = self.dropout(x)
        
        # Output layer
        x = self.fc2(x)
        
        # Apply sigmoid to ensure output is between 0 and 1
        x = torch.sigmoid(x)
        
        return x
    
    def predict(self, data):
        """
        Make predictions on the given data.
        
        Args:
            data: PyTorch Geometric Data object
            
        Returns:
            Predicted congestion scores
        """
        self.eval()
        with torch.no_grad():
            return self.forward(data.x, data.edge_index)
    
    def get_embeddings(self, x, edge_index):
        """
        Get node embeddings from the second-to-last layer.
        
        Args:
            x: Node features
            edge_index: Edge connectivity
            
        Returns:
            Node embeddings
        """
        self.eval()
        with torch.no_grad():
            x = self.conv1(x, edge_index)
            x = self.bn1(x)
            x = F.relu(x)
            
            x = self.conv2(x, edge_index)
            x = self.bn2(x)
            x = F.relu(x)
            
            return x

def create_model(input_dim=3, hidden_dim1=32, hidden_dim2=16, output_dim=1, dropout=0.2):
    """
    Create a TrafficGNN model instance.
    
    Args:
        input_dim: Number of input features
        hidden_dim1: Size of first hidden layer
        hidden_dim2: Size of second hidden layer
        output_dim: Size of output layer
        dropout: Dropout rate
        
    Returns:
        TrafficGNN model instance
    """
    model = TrafficGNN(input_dim, hidden_dim1, hidden_dim2, output_dim, dropout)
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
    print("Testing TrafficGNN model...")
    
    # Create a model
    model = create_model()
    print(f"Model created with {count_parameters(model)} trainable parameters")
    
    # Create dummy data
    num_nodes = 1000
    num_edges = 2000
    input_dim = 3
    
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
