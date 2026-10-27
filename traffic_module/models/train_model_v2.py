"""
Train Traffic GNN v2 with real traffic data
Uses chronological train/val/test split for time-series data
"""

import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
from torch_geometric.data import Data

# Import model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.traffic_gnn_v2 import create_model_v2, count_parameters

class TrafficTrainerV2:
    def __init__(self, model, device='cpu'):
        self.model = model.to(device)
        self.device = device
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, patience=8, factor=0.5)

        self.train_losses = []
        self.val_losses = []

        self.best_val_loss = float('inf')
        self.best_model_state = None

    def train_epoch(self, data):
        self.model.train()
        self.optimizer.zero_grad()

        output = self.model(data.x.to(self.device), data.edge_index.to(self.device))

        loss = self.criterion(
            output[data.train_mask],
            data.y[data.train_mask].to(self.device)
        )

        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()

        return loss.item()

    def validate(self, data):
        self.model.eval()
        with torch.no_grad():
            output = self.model(data.x.to(self.device), data.edge_index.to(self.device))

            loss = self.criterion(
                output[data.val_mask],
                data.y[data.val_mask].to(self.device)
            )

            y_true = data.y[data.val_mask].cpu().numpy()
            y_pred = output[data.val_mask].cpu().numpy()

            mse = mean_squared_error(y_true, y_pred)
            mae = mean_absolute_error(y_true, y_pred)
            r2 = r2_score(y_true, y_pred)

        return loss.item(), mse, mae, r2

    def train(self, data, epochs=100, patience=15):
        print(f"Training for {epochs} epochs...")

        print(f"Train samples: {data.train_mask.sum().item()}")
        print(f"Val samples: {data.val_mask.sum().item()}")
        print(f"Test samples: {data.test_mask.sum().item()}")

        no_improve = 0

        for epoch in range(epochs):
            train_loss = self.train_epoch(data)
            val_loss, mse, mae, r2 = self.validate(data)

            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)

            self.scheduler.step(val_loss)

            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.best_model_state = self.model.state_dict()
                no_improve = 0
            else:
                no_improve += 1

            if epoch % 5 == 0:
                print(f"Epoch {epoch+1}/{epochs} | "
                      f"Train Loss: {train_loss:.4f} | "
                      f"Val Loss: {val_loss:.4f} | "
                      f"MAE: {mae:.4f} | "
                      f"R²: {r2:.4f}")

            if no_improve >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

        # Load best model
        self.model.load_state_dict(self.best_model_state)

    def save(self, path):
        torch.save(self.model.state_dict(), path)
        print(f"Model saved at {path}")

    def plot(self):
        plt.figure(figsize=(10, 6))
        plt.plot(self.train_losses, label='Train Loss')
        plt.plot(self.val_losses, label='Val Loss')
        plt.legend()
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.title("Training Curve")
        plt.grid(True)
        plt.savefig('training_curve_v2.png')
        print("Training curve saved to training_curve_v2.png")

def prepare_graph_data():
    """
    Prepare PyTorch Geometric data from the traffic dataset
    Uses edge-level samples directly for better training data utilization
    """
    print("Loading traffic dataset...")
    df = pd.read_csv('../data/traffic_gnn_dataset.csv')
    
    print(f"Total samples: {len(df)}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    
    # Convert date to datetime
    df['date'] = pd.to_datetime(df['date'])
    
    # Sort by date for chronological split
    df = df.sort_values('date')
    
    # Define feature columns (excluding target and identification columns)
    feature_cols = [
        'traffic_volume',
        'travel_time_index',
        'road_capacity_utilization',
        'incident_reports',
        'environmental_impact',
        'public_transport_usage',
        'traffic_signal_compliance',
        'parking_usage',
        'pedestrian_cyclist_count',
        'edge_length_km',
        'edge_speed_limit_kph',
        'lanes',
        'node_degree',
        'day_of_week',
        'weather_code'
    ]
    
    # Normalize features
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    
    X = df[feature_cols].values
    X_normalized = scaler.fit_transform(X)
    
    # Target: normalized speed
    y = df['target_speed_normalized'].values
    
    # Create a fully connected graph between all samples
    # Each sample is a node in the graph
    num_samples = len(df)
    
    # Create edges based on temporal proximity (connect samples within 7 days)
    from math import radians, sin, cos, sqrt, atan2
    
    def haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    
    edge_list = []
    
    # Connect samples from the same location within 7 days
    for i in range(num_samples):
        for j in range(i+1, min(i+100, num_samples)):  # Limit to next 100 samples for efficiency
            # Check if same location
            if df.iloc[i]['road_name'] == df.iloc[j]['road_name']:
                # Check temporal proximity (within 7 days)
                date_diff = (df.iloc[j]['date'] - df.iloc[i]['date']).days
                if date_diff <= 7:
                    edge_list.append((i, j))
                    edge_list.append((j, i))
    
    if len(edge_list) == 0:
        # Fallback: create a k-nearest neighbor graph based on features
        from sklearn.neighbors import NearestNeighbors
        nbrs = NearestNeighbors(n_neighbors=5, algorithm='ball_tree').fit(X_normalized)
        distances, indices = nbrs.kneighbors(X_normalized)
        
        for i in range(num_samples):
            for j in indices[i]:
                if i != j:
                    edge_list.append((i, j))
                    edge_list.append((j, i))
    
    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    print(f"Created {len(edge_list)//2} edges")
    
    # Create PyTorch Geometric Data object
    x = torch.tensor(X_normalized, dtype=torch.float)
    y = torch.tensor(y, dtype=torch.float).unsqueeze(1)
    
    data = Data(x=x, edge_index=edge_index, y=y)
    
    # Chronological train/val/test split (70% train, 15% val, 15% test)
    train_end = int(num_samples * 0.70)
    val_end = int(num_samples * 0.85)
    
    train_mask = torch.zeros(num_samples, dtype=torch.bool)
    val_mask = torch.zeros(num_samples, dtype=torch.bool)
    test_mask = torch.zeros(num_samples, dtype=torch.bool)
    
    train_mask[:train_end] = True
    val_mask[train_end:val_end] = True
    test_mask[val_end:] = True
    
    data.train_mask = train_mask
    data.val_mask = val_mask
    data.test_mask = test_mask
    
    print(f"\nData preparation complete:")
    print(f"Nodes (samples): {data.num_nodes}")
    print(f"Edges: {data.num_edges}")
    print(f"Features: {data.num_features}")
    print(f"Train samples: {train_mask.sum().item()}")
    print(f"Val samples: {val_mask.sum().item()}")
    print(f"Test samples: {test_mask.sum().item()}")
    
    return data

def main():
    print("="*60)
    print("TRAINING TRAFFIC GNN V2 WITH REAL DATA")
    print("="*60)
    
    # Prepare graph data
    data = prepare_graph_data()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\nUsing device: {device}")
    
    # Create model
    input_dim = data.num_features
    model = create_model_v2(input_dim=input_dim, hidden_dim1=64, hidden_dim2=32, output_dim=1)
    print(f"Model created with {count_parameters(model)} trainable parameters")
    
    # Train
    trainer = TrafficTrainerV2(model, device)
    trainer.train(data, epochs=100, patience=15)
    
    # Save model
    trainer.save('../models/traffic_model_v2.pth')
    
    # Plot training curve
    trainer.plot()
    
    # Final evaluation on test set
    print("\n" + "="*60)
    print("FINAL EVALUATION ON TEST SET")
    print("="*60)
    
    model.eval()
    with torch.no_grad():
        output = model(data.x.to(device), data.edge_index.to(device))
        
        y_true = data.y[data.test_mask].cpu().numpy()
        y_pred = output[data.test_mask].cpu().numpy()
        
        mse = mean_squared_error(y_true, y_pred)
        mae = mean_absolute_error(y_true, y_pred)
        r2 = r2_score(y_true, y_pred)
        
        # Calculate MAPE (Mean Absolute Percentage Error)
        mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-8))) * 100
        
        print(f"Test MSE: {mse:.6f}")
        print(f"Test MAE: {mae:.6f}")
        print(f"Test R²: {r2:.6f}")
        print(f"Test MAPE: {mape:.2f}%")
        
        # Denormalize speed predictions
        y_true_speed = y_true * 80.0  # Denormalize
        y_pred_speed = y_pred * 80.0
        
        mae_speed = mean_absolute_error(y_true_speed, y_pred_speed)
        print(f"Test MAE (speed in km/h): {mae_speed:.2f} km/h")

if __name__ == "__main__":
    main()
