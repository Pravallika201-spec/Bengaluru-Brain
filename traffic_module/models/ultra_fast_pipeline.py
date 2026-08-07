import torch
import pandas as pd
import numpy as np
import osmnx as ox
import time
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv
import torch.nn as nn
import torch.nn.functional as F
from sklearn.preprocessing import StandardScaler
import folium
from folium.plugins import HeatMap
import warnings
warnings.filterwarnings('ignore')

class UltraFastTrafficGNN(nn.Module):
    """Ultra-optimized GNN for maximum speed"""
    
    def __init__(self, input_dim=3, hidden_dim=16, output_dim=1):
        super(UltraFastTrafficGNN, self).__init__()
        self.conv1 = GCNConv(input_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, output_dim)
        
    def forward(self, x, edge_index):
        x = F.relu(self.conv1(x, edge_index))
        x = torch.sigmoid(self.conv2(x, edge_index))
        return x

class UltraFastPipeline:
    """Ultra-fast pipeline for rapid prototyping"""
    
    def __init__(self, device='auto'):
        self.device = device if device != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"⚡ Ultra-Fast Pipeline | Device: {self.device}")
        
    def load_existing_graph(self):
        """Load pre-downloaded graph to skip download time"""
        print("📥 Loading existing graph...")
        start_time = time.time()
        
        try:
            G = ox.load_graphml("../data/bangalore.graphml")
            print(f"✅ Graph loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
            print(f"⏱️ Load time: {time.time() - start_time:.2f}s")
            return G
        except:
            print("❌ No existing graph found, downloading...")
            return self.download_minimal_graph()
    
    def download_minimal_graph(self):
        """Download minimal graph for speed"""
        print("🌐 Downloading minimal graph...")
        start_time = time.time()
        
        # Use smaller area for demo
        G = ox.graph_from_place("Bangalore, India", network_type='drive', simplify=True)
        
        print(f"✅ Graph downloaded: {G.number_of_nodes():,} nodes")
        print(f"⏱️ Download time: {time.time() - start_time:.2f}s")
        return G
    
    def create_synthetic_data(self, num_nodes=10000):
        """Create synthetic data without graph processing"""
        print("🎲 Creating synthetic data...")
        start_time = time.time()
        
        np.random.seed(42)
        
        # Generate synthetic coordinates (Bangalore area)
        x_coords = np.random.uniform(77.4, 77.7, num_nodes)
        y_coords = np.random.uniform(12.8, 13.1, num_nodes)
        
        # Generate synthetic features
        traffic_speed = np.random.uniform(20, 60, num_nodes)
        rainfall = np.random.uniform(0, 10, num_nodes)
        road_capacity = np.random.choice([1, 2, 3, 4], num_nodes, p=[0.3, 0.4, 0.2, 0.1])
        
        # Generate target
        congestion = (0.4 * (60 - traffic_speed) / 40 + 
                     0.2 * rainfall / 10 + 
                     0.2 * (4 - road_capacity) / 3 + 
                     0.2 * np.random.uniform(0, 1, num_nodes))
        congestion = np.clip(congestion + np.random.normal(0, 0.05, num_nodes), 0, 1)
        
        features_df = pd.DataFrame({
            'node_id': range(num_nodes),
            'x': x_coords,
            'y': y_coords,
            'traffic_speed': traffic_speed,
            'rainfall': rainfall,
            'road_capacity': road_capacity,
            'congestion_score': congestion
        })
        
        print(f"✅ Synthetic data created: {num_nodes:,} nodes")
        print(f"⏱️ Generation time: {time.time() - start_time:.2f}s")
        return features_df
    
    def create_synthetic_edges(self, num_nodes, edge_ratio=0.02):
        """Create synthetic edges for connectivity"""
        print("🔗 Creating synthetic edges...")
        start_time = time.time()
        
        # Create random edges (each node connected to ~2% of others)
        num_edges = int(num_nodes * num_nodes * edge_ratio)
        
        # Generate random edges
        sources = np.random.randint(0, num_nodes, num_edges)
        targets = np.random.randint(0, num_nodes, num_edges)
        
        # Remove self-loops and duplicates
        edges = set()
        for s, t in zip(sources, targets):
            if s != t:
                edges.add((s, t))
                edges.add((t, s))  # Make undirected
        
        edge_list = list(edges)
        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        
        print(f"✅ Edges created: {len(edge_list):,} edges")
        print(f"⏱️ Edge creation time: {time.time() - start_time:.2f}s")
        return edge_index
    
    def create_pyg_data_ultra_fast(self, features_df):
        """Create PyG data with synthetic edges"""
        print("⚡ Creating PyG data...")
        start_time = time.time()
        
        # Features
        features = ['traffic_speed', 'rainfall', 'road_capacity']
        X = StandardScaler().fit_transform(features_df[features].values)
        x = torch.tensor(X, dtype=torch.float32)
        
        # Synthetic edges
        edge_index = self.create_synthetic_edges(len(features_df))
        
        # Target
        y = torch.tensor(features_df['congestion_score'].values, dtype=torch.float32).unsqueeze(1)
        
        data = Data(x=x, edge_index=edge_index, y=y)
        print(f"⏱️ Data creation time: {time.time() - start_time:.2f}s")
        return data
    
    def train_ultra_fast(self, data, epochs=10):
        """Ultra-fast training"""
        print("🚀 Ultra-fast training...")
        start_time = time.time()
        
        model = UltraFastTrafficGNN().to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
        criterion = nn.MSELoss()
        
        data = data.to(self.device)
        
        # Simple training loop
        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            
            out = model(data.x, data.edge_index)
            loss = criterion(out, data.y)
            loss.backward()
            optimizer.step()
            
            if epoch % 2 == 0:
                print(f"Epoch {epoch+1:2d}/{epochs:2d} | Loss: {loss.item():.4f}")
        
        print(f"⏱️ Training time: {time.time() - start_time:.2f}s")
        return model, data
    
    def predict_ultra_fast(self, model, data):
        """Ultra-fast prediction"""
        print("⚡ Ultra-fast prediction...")
        start_time = time.time()
        
        model.eval()
        with torch.no_grad():
            predictions = model(data.x, data.edge_index)
        
        print(f"⏱️ Prediction time: {time.time() - start_time:.2f}s")
        return predictions.cpu().numpy().flatten()
    
    def visualize_ultra_fast(self, features_df, predictions):
        """Ultra-fast visualization"""
        print("🗺️ Creating visualization...")
        start_time = time.time()
        
        # Add predictions
        viz_df = features_df.copy()
        viz_df['predicted_congestion'] = predictions
        
        # Sample for visualization
        sample_df = viz_df.sample(n=min(1000, len(viz_df)), random_state=42)
        
        # Create simple map
        m = folium.Map(location=[12.9716, 77.5946], zoom_start=11)
        
        # Add points
        for _, row in sample_df.iterrows():
            color = 'red' if row['predicted_congestion'] > 0.6 else 'orange' if row['predicted_congestion'] > 0.3 else 'green'
            folium.CircleMarker(
                location=[row['y'], row['x']],
                radius=3,
                color=color,
                fill=True,
                fill_opacity=0.7
            ).add_to(m)
        
        m.save('../output/ultra_fast_map.html')
        print(f"⏱️ Visualization time: {time.time() - start_time:.2f}s")
    
    def run_ultra_fast(self, num_nodes=10000, epochs=10):
        """Run ultra-fast pipeline"""
        print("⚡" * 40)
        print("ULTRA-FAST TRAFFIC PREDICTION PIPELINE")
        print("⚡" * 40)
        
        total_start = time.time()
        
        # Step 1: Create synthetic data (skip graph download)
        features_df = self.create_synthetic_data(num_nodes)
        
        # Step 2: Create PyG data
        data = self.create_pyg_data_ultra_fast(features_df)
        
        # Step 3: Train
        model, data = self.train_ultra_fast(data, epochs)
        
        # Step 4: Predict
        predictions = self.predict_ultra_fast(model, data)
        
        # Step 5: Visualize
        self.visualize_ultra_fast(features_df, predictions)
        
        # Step 6: Save results
        results_df = features_df.copy()
        results_df['predicted_congestion'] = predictions
        results_df.to_csv('../output/ultra_fast_predictions.csv', index=False)
        
        # Metrics
        actual = features_df['congestion_score'].values
        mse = np.mean((predictions - actual) ** 2)
        mae = np.mean(np.abs(predictions - actual))
        
        print("\n⚡" * 40)
        print("ULTRA-FAST PIPELINE COMPLETED")
        print("⚡" * 40)
        print(f"⏱️ Total time: {time.time() - total_start:.2f}s")
        print(f"📊 Nodes processed: {num_nodes:,}")
        print(f"📈 MSE: {mse:.4f}")
        print(f"📈 MAE: {mae:.4f}")
        print(f"💾 Files: ultra_fast_map.html, ultra_fast_predictions.csv")
        
        return model, results_df

# Run ultra-fast pipeline
if __name__ == "__main__":
    pipeline = UltraFastPipeline()
    model, results = pipeline.run_ultra_fast(num_nodes=10000, epochs=10)
