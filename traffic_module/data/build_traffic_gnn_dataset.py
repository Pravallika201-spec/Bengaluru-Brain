"""
Build GNN Training Dataset from Traffic Observations and OSM Graph
Connects real traffic data to OSM road edges for supervised learning
"""

import pandas as pd
import pickle
import numpy as np
from datetime import datetime
import networkx as nx

# -----------------------------
# FILE PATHS
# -----------------------------

TRAFFIC_FILE = r"C:\Users\ravip\OneDrive\Desktop\Banglore_traffic_Dataset.csv"
GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"
MAPPING_FILE = r"D:\major project\traffic_module\data\traffic_location_mapping.csv"
OUTPUT_FILE = r"D:\major project\traffic_module\data\traffic_gnn_dataset.csv"

# -----------------------------
# LOAD DATA
# -----------------------------

print("Loading traffic dataset...")
df = pd.read_csv(TRAFFIC_FILE)
print(f"Traffic rows: {len(df)}")

print("\nLoading Bengaluru graph...")
with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)
print(f"Graph nodes: {len(G.nodes)}, edges: {len(G.edges)}")

print("\nLoading location mapping...")
mapping_df = pd.read_csv(MAPPING_FILE)
print(f"Locations mapped: {len(mapping_df)}")

# -----------------------------
# FILTER VALID MAPPINGS
# -----------------------------

# Only use MATCHED locations (distance <= 300m)
valid_mappings = mapping_df[mapping_df['status'] == 'MATCHED'].copy()
print(f"\nValid mappings: {len(valid_mappings)}")

# Exclude Ballari Road (too far)
valid_mappings = valid_mappings[valid_mappings['traffic_location'] != 'Ballari Road']
print(f"After excluding Ballari Road: {len(valid_mappings)}")

# Create location to node mapping
location_to_node = dict(zip(valid_mappings['traffic_location'], valid_mappings['nearest_node']))
print(f"\nLocation to node mapping:")
for loc, node in location_to_node.items():
    print(f"  {loc} -> {int(node)}")

# -----------------------------
# CONNECT TRAFFIC TO OSM EDGES
# -----------------------------

print("\nConnecting traffic observations to OSM edges...")

dataset_rows = []

for _, row in df.iterrows():
    location = row['Road/Intersection Name']
    
    # Skip if location not in valid mappings
    if location not in location_to_node:
        continue
    
    node_id = int(location_to_node[location])
    
    # Find edges connected to this node
    if node_id not in G:
        continue
    
    connected_edges = list(G.edges(node_id, keys=True, data=True))
    
    if not connected_edges:
        continue
    
    # For each connected edge, create a training sample
    for u, v, key, edge_data in connected_edges:
        # Extract edge features
        edge_length = edge_data.get('length', 100.0)  # meters
        edge_speed_kph = edge_data.get('speed_kph', 30.0)
        highway_type = edge_data.get('highway', 'unclassified')
        lanes = edge_data.get('lanes', 1)
        
        # Calculate edge-level features
        edge_length_km = edge_length / 1000.0
        
        # Create training row
        dataset_row = {
            # Identification
            'date': row['Date'],
            'area_name': row['Area Name'],
            'road_name': location,
            'osm_node_id': node_id,
            'edge_u': u,
            'edge_v': v,
            'edge_key': key,
            
            # Traffic observations (from dataset)
            'traffic_volume': row['Traffic Volume'],
            'average_speed': row['Average Speed'],
            'travel_time_index': row['Travel Time Index'],
            'congestion_level': row['Congestion Level'],
            'road_capacity_utilization': row['Road Capacity Utilization'],
            'incident_reports': row['Incident Reports'],
            'environmental_impact': row['Environmental Impact'],
            'public_transport_usage': row['Public Transport Usage'],
            'traffic_signal_compliance': row['Traffic Signal Compliance'],
            'parking_usage': row['Parking Usage'],
            'pedestrian_cyclist_count': row['Pedestrian and Cyclist Count'],
            'weather_conditions': row['Weather Conditions'],
            'roadwork_construction': row['Roadwork and Construction Activity'],
            
            # OSM edge features
            'edge_length_m': edge_length,
            'edge_length_km': edge_length_km,
            'edge_speed_limit_kph': edge_speed_kph,
            'highway_type': highway_type,
            'lanes': lanes,
            
            # Node degree (graph connectivity)
            'node_degree': G.degree(node_id),
        }
        
        dataset_rows.append(dataset_row)

print(f"Total training samples: {len(dataset_rows)}")

# -----------------------------
# CREATE DATASET
# -----------------------------

dataset_df = pd.DataFrame(dataset_rows)

# Convert date to datetime
dataset_df['date'] = pd.to_datetime(dataset_df['date'])

# Add temporal features
dataset_df['day_of_week'] = dataset_df['date'].dt.dayofweek
dataset_df['month'] = dataset_df['date'].dt.month
dataset_df['day_of_month'] = dataset_df['date'].dt.day

# Encode weather conditions
weather_mapping = {
    'Clear': 0,
    'Overcast': 1,
    'Fog': 2,
    'Rain': 3,
    'Windy': 4,
    'Storm': 5
}
dataset_df['weather_code'] = dataset_df['weather_conditions'].map(weather_mapping).fillna(0)

# Encode roadwork
dataset_df['roadwork_code'] = (dataset_df['roadwork_construction'] == 'Yes').astype(int)

# Encode highway type
highway_mapping = {
    'primary': 1,
    'secondary': 2,
    'tertiary': 3,
    'residential': 4,
    'unclassified': 0
}
dataset_df['highway_code'] = dataset_df['highway_type'].map(highway_mapping).fillna(0)

# -----------------------------
# DEFINE TARGET VARIABLE
# -----------------------------

# Target: Normalized average speed (0-1 range)
# We'll normalize by a reasonable max speed (e.g., 80 km/h)
dataset_df['target_speed_normalized'] = dataset_df['average_speed'] / 80.0
dataset_df['target_speed_normalized'] = dataset_df['target_speed_normalized'].clip(0, 1)

# Alternative target: Congestion level (0-1)
dataset_df['target_congestion'] = dataset_df['congestion_level'] / 100.0
dataset_df['target_congestion'] = dataset_df['target_congestion'].clip(0, 1)

# -----------------------------
# SAVE DATASET
# -----------------------------

dataset_df.to_csv(OUTPUT_FILE, index=False)
print(f"\nDataset saved to: {OUTPUT_FILE}")

# -----------------------------
# PRINT SUMMARY
# -----------------------------

print("\n" + "="*60)
print("DATASET SUMMARY")
print("="*60)
print(f"Total samples: {len(dataset_df)}")
print(f"Date range: {dataset_df['date'].min()} to {dataset_df['date'].max()}")
print(f"Unique locations: {dataset_df['road_name'].nunique()}")
print(f"Unique OSM nodes: {dataset_df['osm_node_id'].nunique()}")

print("\nFeature statistics:")
print(f"Average speed: {dataset_df['average_speed'].mean():.2f} ± {dataset_df['average_speed'].std():.2f} km/h")
print(f"Traffic volume: {dataset_df['traffic_volume'].mean():.2f} ± {dataset_df['traffic_volume'].std():.2f}")
print(f"Congestion level: {dataset_df['congestion_level'].mean():.2f} ± {dataset_df['congestion_level'].std():.2f}")

print("\nTarget variable statistics:")
print(f"Target speed (normalized): {dataset_df['target_speed_normalized'].mean():.3f} ± {dataset_df['target_speed_normalized'].std():.3f}")
print(f"Target congestion: {dataset_df['target_congestion'].mean():.3f} ± {dataset_df['target_congestion'].std():.3f}")

print("\nWeather distribution:")
print(dataset_df['weather_conditions'].value_counts())

print("\nHighway type distribution:")
print(dataset_df['highway_type'].value_counts())

print("\n" + "="*60)
print("READY FOR GNN TRAINING")
print("="*60)
