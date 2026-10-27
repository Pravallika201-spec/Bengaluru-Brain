import pickle
import pandas as pd

# -----------------------------
# FILE PATHS
# -----------------------------

GRAPH_PATH = r"D:\major project\traffic_module\backend\data\bengaluru_graph.pkl"

# IMPORTANT:
# We will update this path once we locate your traffic dataset.
TRAFFIC_FILE = r"C:\Users\ravip\OneDrive\Desktop\Banglore_traffic_Dataset.csv"


# -----------------------------
# LOAD BENGALURU ROAD GRAPH
# -----------------------------

print("Loading Bengaluru road graph...")

with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

print("Graph loaded.")
print("Nodes:", len(G.nodes))
print("Edges:", len(G.edges))


# -----------------------------
# LOAD TRAFFIC DATASET
# -----------------------------

print("\nLoading traffic dataset...")

df = pd.read_csv(TRAFFIC_FILE)

print("Rows:", len(df))

print("\nColumns:")
print(df.columns.tolist())


# -----------------------------
# FIND ROAD COLUMN
# -----------------------------

road_column = "Road/Intersection Name"


print("\nUsing road column:", road_column)


# -----------------------------
# UNIQUE TRAFFIC LOCATIONS
# -----------------------------

roads = (
    df[road_column]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)


print("\nTraffic locations found:")

for road in roads:
    print("-", road)


print("\nTotal unique locations:", len(roads))