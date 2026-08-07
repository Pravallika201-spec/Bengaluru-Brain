import osmnx as ox
import pandas as pd
import numpy as np

# Load the Bangalore graph
print("Loading Bangalore graph...")
G = ox.load_graphml("bangalore.graphml")

print(f"Graph loaded successfully!")
print(f"Number of nodes: {G.number_of_nodes()}")
print(f"Number of edges: {G.number_of_edges()}")

# Convert nodes to CSV
print("Converting nodes to CSV...")
nodes_data = []
for node, data in G.nodes(data=True):
    node_info = {
        'node_id': node,
        'x': data.get('x', 0),
        'y': data.get('y', 0),
        'street_count': data.get('street_count', 0)
    }
    nodes_data.append(node_info)

nodes_df = pd.DataFrame(nodes_data)
nodes_df.to_csv('nodes.csv', index=False)
print(f"Nodes CSV saved with {len(nodes_df)} nodes")

# Convert edges to CSV
print("Converting edges to CSV...")
edges_data = []
for u, v, data in G.edges(data=True):
    edge_info = {
        'source': u,
        'target': v,
        'length': data.get('length', 0),
        'maxspeed': data.get('maxspeed', None),
        'highway': data.get('highway', None),
        'name': data.get('name', None),
        'oneway': data.get('oneway', False)
    }
    edges_data.append(edge_info)

edges_df = pd.DataFrame(edges_data)
edges_df.to_csv('edges.csv', index=False)
print(f"Edges CSV saved with {len(edges_df)} edges")

# Display sample data
print("\nSample nodes data:")
print(nodes_df.head())
print("\nSample edges data:")
print(edges_df.head())
