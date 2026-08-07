import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv
from torch_geometric.data import Data
import numpy as np
import os
import pandas as pd

class TrafficGNN(nn.Module):
    """
    Graph Attention Network — predicts congestion score
    per node (junction) across Bengaluru road graph.
    3 GAT layers. Input: 12 node features. Output: score 0-1.
    """
    def __init__(self, node_features=12, hidden=64, heads=2):
        super(TrafficGNN, self).__init__()
        self.gat1 = GATConv(node_features, hidden,
                            heads=heads, dropout=0.2)
        self.gat2 = GATConv(hidden * heads, hidden,
                            heads=heads, dropout=0.2)
        self.gat3 = GATConv(hidden * heads, 1,
                            heads=1, concat=False)
        self.dropout = nn.Dropout(0.2)

    def forward(self, x, edge_index):
        x = F.elu(self.gat1(x, edge_index))
        x = self.dropout(x)
        x = F.elu(self.gat2(x, edge_index))
        x = self.dropout(x)
        x = torch.sigmoid(self.gat3(x, edge_index))
        return x


def build_pyg_data(G, hour, is_weekday, weather_code, 
                   it_shift_load=0.0, event_load=0.0,
                   traffic_nodes_df=None, edges_df=None):
    """
    Converts OSMnx graph to PyTorch Geometric Data.
    Node features (12):
        1. degree / 10.0
        2. avg_speed / 80.0
        3. hour_sin
        4. hour_cos
        5. is_weekday
        6. weather_code / 4.0
        7. it_proximity_factor (from traffic_nodes.csv)
        8. peak_hour_factor (from traffic_nodes.csv)
        9. historical_congestion (from traffic_nodes.csv)
        10. it_shift_load
        11. event_load
        12. road_capacity / 10.0 (from traffic_nodes.csv)
    """
    nodes = list(G.nodes(data=True))
    node_ids = {node[0]: i for i, node in enumerate(nodes)}

    # Load traffic nodes data if available
    traffic_data = {}
    if traffic_nodes_df is not None:
        for _, row in traffic_nodes_df.iterrows():
            traffic_data[row['node_id']] = {
                'traffic_speed': row.get('traffic_speed', 48),
                'road_capacity': row.get('road_capacity', 2),
                'it_proximity_factor': row.get('it_proximity_factor', 0.0),
                'peak_hour_factor': row.get('peak_hour_factor', 1.0),
                'congestion_score': row.get('congestion_score', 0.0)
            }

    node_features = []
    for node_id, _ in nodes:
        degree = G.degree(node_id)
        
        # Get edge speeds
        speeds = [
            d.get("speed_kph", 30)
            for _, _, d in G.edges(node_id, data=True)
        ]
        avg_speed = float(np.mean(speeds)) if speeds else 30.0
        
        # Time features
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)
        
        # Traffic data features
        tdata = traffic_data.get(node_id, {})
        it_proximity = tdata.get('it_proximity_factor', 0.0)
        peak_factor = tdata.get('peak_hour_factor', 1.0)
        hist_congestion = tdata.get('congestion_score', 0.0)
        road_capacity = tdata.get('road_capacity', 2)
        
        node_features.append([
            min(degree / 10.0, 1.0),
            avg_speed / 80.0,
            hour_sin,
            hour_cos,
            float(is_weekday),
            weather_code / 4.0,
            it_proximity,
            peak_factor,
            hist_congestion,
            it_shift_load,
            event_load,
            road_capacity / 10.0,
        ])

    edge_index = []
    edge_features = []
    
    for u, v, data in G.edges(data=True):
        if u in node_ids and v in node_ids:
            edge_index.append([node_ids[u], node_ids[v]])
            edge_index.append([node_ids[v], node_ids[u]])
            
            # Edge features
            length = data.get('length', 100.0) / 1000.0  # km
            maxspeed = data.get('maxspeed', 50)
            highway = data.get('highway', 'residential')
            
            # Encode highway type
            highway_encoding = 0.0
            if 'primary' in highway:
                highway_encoding = 0.8
            elif 'secondary' in highway:
                highway_encoding = 0.6
            elif 'tertiary' in highway:
                highway_encoding = 0.4
            elif 'residential' in highway:
                highway_encoding = 0.2
            
            edge_features.append([
                min(length / 10.0, 1.0),
                maxspeed / 100.0,
                highway_encoding,
                1.0 if data.get('oneway', False) else 0.0
            ])
            edge_features.append([
                min(length / 10.0, 1.0),
                maxspeed / 100.0,
                highway_encoding,
                1.0 if data.get('oneway', False) else 0.0
            ])

    x = torch.tensor(node_features, dtype=torch.float)
    ei = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
    ef = torch.tensor(edge_features, dtype=torch.float) if edge_features else None
    
    return Data(x=x, edge_index=ei, edge_attr=ef), node_ids


def run_gnn(G, hour, is_weekday, weather_code, 
            it_shift_load=0.0, event_load=0.0,
            traffic_nodes_df=None, edges_df=None):
    """
    Runs GNN on full Bengaluru graph.
    Returns dict: {node_id: congestion_score (0-1)}
    """
    model = TrafficGNN(node_features=12)
    model_path = "data/traffic_gnn.pt"

    if os.path.exists(model_path):
        model.load_state_dict(
            torch.load(model_path, map_location="cpu")
        )
        print("Loaded trained GNN weights")
    else:
        print("Using untrained GNN (train later with Kaggle data)")

    model.eval()
    data, node_ids = build_pyg_data(G, hour, is_weekday, weather_code,
                                     it_shift_load, event_load,
                                     traffic_nodes_df, edges_df)

    with torch.no_grad():
        scores = model(data.x, data.edge_index)

    nodes = list(G.nodes())
    return {
        node_id: float(scores[idx].item())
        for node_id, idx in node_ids.items()
    }


def get_route_congestion_score(route_coords, gnn_scores, G):
    """
    Calculate average congestion score for route by finding
    nodes near the route polyline.
    """
    if not route_coords or not gnn_scores:
        return 50.0  # Default moderate congestion
    
    # Find nodes near route (simplified approach)
    route_scores = []
    for lat, lon in route_coords:
        # Find nearest node in graph
        min_dist = float('inf')
        nearest_node = None
        for node_id, node_data in G.nodes(data=True):
            if 'x' in node_data and 'y' in node_data:
                node_lat = node_data['y']
                node_lon = node_data['x']
                dist = ((lat - node_lat)**2 + (lon - node_lon)**2)**0.5
                if dist < min_dist:
                    min_dist = dist
                    nearest_node = node_id
        
        if nearest_node and nearest_node in gnn_scores:
            route_scores.append(gnn_scores[nearest_node])
    
    if route_scores:
        return np.mean(route_scores) * 100  # Convert to 0-100 scale
    return 50.0
