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

class FastTrafficGNN(nn.Module):
    """Optimized GNN for faster training and inference"""
    
    def __init__(self, input_dim=3, hidden_dim=32, output_dim=1):
        super(FastTrafficGNN, self).__init__()
        self.conv1 = GCNConv(input_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, output_dim)
        self.dropout = nn.Dropout(0.1)
        
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.conv2(x, edge_index)
        return torch.sigmoid(x)

class FastTrafficPipeline:
    """Optimized pipeline for faster execution"""
    
    def __init__(self, device='auto'):
        self.device = device if device != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"Using device: {self.device}")
        
    def download_and_process_graph(self, sample_size=50000):
        """Download and process graph with sampling for speed"""
        print("Downloading Bangalore road network (optimized)...")
        start_time = time.time()
        
        # Download with simplified network
        G = ox.graph_from_place("Bangalore, India", network_type='drive', simplify=True)
        
        print(f"Original graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
        
        # Sample nodes for faster processing
        if G.number_of_nodes() > sample_size:
            nodes = list(G.nodes())[:sample_size]
            G = G.subgraph(nodes).copy()
        
        print(f"Sampled graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
        print(f"Graph processing time: {time.time() - start_time:.2f}s")
        
        return G
    
    def generate_features_fast(self, G):
        """Generate features with vectorized operations"""
        print("Generating traffic features (optimized)...")
        start_time = time.time()
        
        nodes = list(G.nodes(data=True))
        node_ids = [n[0] for n in nodes]
        node_data = [n[1] for n in nodes]
        
        # Vectorized feature generation
        n_nodes = len(node_ids)
        np.random.seed(42)
        
        # Traffic speed (inverse correlation with street count)
        street_counts = [d.get('street_count', 2) for d in node_data]
        traffic_speed = np.clip(60 - np.array(street_counts) * 3 + np.random.normal(0, 5, n_nodes), 20, 60)
        
        # Rainfall (random)
        rainfall = np.random.uniform(0, 10, n_nodes)
        
        # Road capacity (based on street count)
        road_capacity = np.where(np.array(street_counts) <= 2, 1,
                               np.where(np.array(street_counts) <= 4, 2, 3))
        
        # Congestion score
        congestion = (0.4 * (60 - traffic_speed) / 40 + 
                     0.2 * rainfall / 10 + 
                     0.2 * (4 - road_capacity) / 3 + 
                     0.2 * np.array(street_counts) / 10)
        congestion = np.clip(congestion + np.random.normal(0, 0.05, n_nodes), 0, 1)
        
        # Create dataframe
        features_df = pd.DataFrame({
            'node_id': node_ids,
            'x': [d.get('x', 77.5) for d in node_data],
            'y': [d.get('y', 12.9) for d in node_data],
            'traffic_speed': traffic_speed,
            'rainfall': rainfall,
            'road_capacity': road_capacity,
            'congestion_score': congestion
        })
        
        print(f"Feature generation time: {time.time() - start_time:.2f}s")
        return features_df, G
    
    def create_pyg_data_fast(self, features_df, G):
        """Create PyTorch Geometric data efficiently"""
        print("Creating PyTorch Geometric data (optimized)...")
        start_time = time.time()
        
        # Node mapping
        node_to_idx = {node: idx for idx, node in enumerate(features_df['node_id'])}
        
        # Features
        features = ['traffic_speed', 'rainfall', 'road_capacity']
        X = StandardScaler().fit_transform(features_df[features].values)
        x = torch.tensor(X, dtype=torch.float32)
        
        # Edge index (vectorized)
        edges = list(G.edges())
        edge_list = []
        for u, v in edges:
            if u in node_to_idx and v in node_to_idx:
                edge_list.extend([[node_to_idx[u], node_to_idx[v]], 
                                [node_to_idx[v], node_to_idx[u]]])
        
        if edge_list:
            edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        else:
            edge_index = torch.empty((2, 0), dtype=torch.long)
        
        # Target
        y = torch.tensor(features_df['congestion_score'].values, dtype=torch.float32).unsqueeze(1)
        
        data = Data(x=x, edge_index=edge_index, y=y)
        print(f"Data creation time: {time.time() - start_time:.2f}s")
        
        return data
    
    def train_fast(self, data, epochs=20):
        """Fast training with optimized settings"""
        print("Training model (optimized)...")
        start_time = time.time()
        
        model = FastTrafficGNN().to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        criterion = nn.MSELoss()
        
        # Train/validation split
        num_nodes = data.num_nodes
        train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        val_mask = torch.zeros(num_nodes, dtype=torch.bool)
        
        indices = torch.randperm(num_nodes)
        split_idx = int(num_nodes * 0.8)
        train_mask[indices[:split_idx]] = True
        val_mask[indices[split_idx:]] = True
        
        data = data.to(self.device)
        
        # Training loop
        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()
            
            out = model(data.x, data.edge_index)
            loss = criterion(out[train_mask], data.y[train_mask])
            loss.backward()
            optimizer.step()
            
            if epoch % 5 == 0:
                model.eval()
                with torch.no_grad():
                    val_loss = criterion(out[val_mask], data.y[val_mask])
                print(f'Epoch {epoch+1:2d}/{epochs:2d} | Train Loss: {loss.item():.4f} | Val Loss: {val_loss.item():.4f}')
        
        print(f"Training time: {time.time() - start_time:.2f}s")
        return model, data
    
    def predict_fast(self, model, data):
        """Fast prediction"""
        print("Generating predictions...")
        start_time = time.time()
        
        model.eval()
        with torch.no_grad():
            predictions = model(data.x, data.edge_index)
        
        print(f"Prediction time: {time.time() - start_time:.2f}s")
        return predictions.cpu().numpy().flatten()
    
    def visualize_fast(self, features_df, predictions, output_path):
        """Fast visualization"""
        print("Creating visualization...")
        start_time = time.time()
        
        # Add predictions to dataframe
        viz_df = features_df.copy()
        viz_df['predicted_congestion'] = predictions
        
        # Sample for visualization
        sample_df = viz_df.sample(n=min(2000, len(viz_df)), random_state=42)
        
        # Create map
        m = folium.Map(location=[12.9716, 77.5946], zoom_start=11, tiles="CartoDB positron")
        
        # Add heatmap
        heat_data = [[row['y'], row['x'], row['predicted_congestion']] 
                    for _, row in sample_df.iterrows()]
        
        HeatMap(heat_data, radius=10, blur=5, 
               gradient={0.2: 'green', 0.5: 'yellow', 0.8: 'red'}).add_to(m)
        
        m.save(output_path)
        print(f"Visualization time: {time.time() - start_time:.2f}s")
        print(f"Map saved to {output_path}")
    
    def run_pipeline(self, sample_size=50000, epochs=20):
        """Run complete fast pipeline"""
        print("="*60)
        print("FAST TRAFFIC PREDICTION PIPELINE")
        print("="*60)
        
        total_start = time.time()
        
        # Step 1: Download and process graph
        G = self.download_and_process_graph(sample_size)
        
        # Step 2: Generate features
        features_df, G = self.generate_features_fast(G)
        
        # Step 3: Create PyG data
        data = self.create_pyg_data_fast(features_df, G)
        
        # Step 4: Train model
        model, data = self.train_fast(data, epochs)
        
        # Step 5: Predict
        predictions = self.predict_fast(model, data)
        
        # Step 6: Visualize
        self.visualize_fast(features_df, predictions, '../output/fast_traffic_map.html')
        
        # Step 7: Save results
        results_df = features_df.copy()
        results_df['predicted_congestion'] = predictions
        results_df.to_csv('../output/fast_traffic_predictions.csv', index=False)
        
        # Performance metrics
        actual = features_df['congestion_score'].values
        mse = np.mean((predictions - actual) ** 2)
        mae = np.mean(np.abs(predictions - actual))
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETED")
        print("="*60)
        print(f"Total time: {time.time() - total_start:.2f}s")
        print(f"Nodes processed: {len(features_df):,}")
        print(f"MSE: {mse:.4f}")
        print(f"MAE: {mae:.4f}")
        print(f"Files saved: fast_traffic_map.html, fast_traffic_predictions.csv")
        
        return model, results_df

# Run the fast pipeline
if __name__ == "__main__":
    pipeline = FastTrafficPipeline()
    model, results = pipeline.run_pipeline(sample_size=50000, epochs=20)
