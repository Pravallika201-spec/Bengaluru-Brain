import pandas as pd
import torch
from torch_geometric.data import Data
import pickle

print("Converting graph to PyTorch Geometric format...")

# Load data
print("Loading traffic nodes and edges data...")
traffic_nodes = pd.read_csv("traffic_nodes.csv")
edges = pd.read_csv("edges.csv")

# Create node mapping (node_id → index)
print("Creating node mapping...")
node_ids = traffic_nodes['node_id'].values
node_to_idx = {node_id: i for i, node_id in enumerate(node_ids)}

# Save mapping
with open("node_mapping.pkl", "wb") as f:
    pickle.dump(node_to_idx, f)

# ✅ FEATURES (3 FEATURES: traffic_speed, street_count, peak_hour_factor)
print("Preparing node features...")
features = traffic_nodes[['traffic_speed', 'street_count', 'peak_hour_factor']].values
x = torch.tensor(features, dtype=torch.float)

# Target (congestion score)
y = torch.tensor(traffic_nodes['congestion_score'].values, dtype=torch.float).view(-1, 1)

# Build edge index
print("Preparing edge index...")
edge_list = []

for _, row in edges.iterrows():
   u = row['source']
   v = row['target']
   if u in node_to_idx and v in node_to_idx:
       edge_list.append([node_to_idx[u], node_to_idx[v]])

edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()

# Create graph data
data = Data(x=x, edge_index=edge_index, y=y)

# Save graph
torch.save(data, "traffic_graph.pt")

print("Graph created successfully!")
print(data)