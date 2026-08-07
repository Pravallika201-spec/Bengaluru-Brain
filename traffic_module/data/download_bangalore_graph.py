import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Download Bangalore road graph
print("Downloading Bangalore road network...")
G = ox.graph_from_place("Bangalore, India", network_type='drive')

# Save as GraphML
print("Saving graph as bangalore.graphml...")
ox.save_graphml(G, filepath="bangalore.graphml")

print(f"Graph downloaded successfully!")
print(f"Number of nodes: {G.number_of_nodes()}")
print(f"Number of edges: {G.number_of_edges()}")

# Basic visualization
print("Creating basic visualization...")
fig, ax = ox.plot_graph(G, figsize=(12, 12), node_size=0, edge_linewidth=0.5, show=False, close=False)
plt.title("Bangalore Road Network")
plt.savefig("bangalore_road_network.png", dpi=300, bbox_inches='tight')
plt.show()

print("Visualization saved as bangalore_road_network.png")
