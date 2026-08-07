import pandas as pd
import numpy as np
from datetime import datetime

print("Loading nodes data...")
nodes_df = pd.read_csv('nodes.csv')

np.random.seed(42)

print("Generating features...")

# -----------------------------
# BASIC FEATURES
# -----------------------------
street_count = nodes_df['street_count'].values

# deterministic speed (no randomness)
traffic_speed = 60 - street_count * 4
traffic_speed = np.clip(traffic_speed, 20, 60)

# structured capacity
road_capacity = np.where(street_count <= 2, 1,
                 np.where(street_count <= 4, 2, 3))

# -----------------------------
# IT PARK SHIFT EFFECT
# -----------------------------
print("Adding IT park shift effect...")

# Define IT park coordinates in Bangalore (major tech parks)
it_parks = [
    {'name': 'Electronic City', 'lat': 12.8452, 'lon': 77.6721, 'radius': 2.0},
    {'name': 'Whitefield', 'lat': 12.9698, 'lon': 77.7499, 'radius': 2.5},
    {'name': 'Manyata Tech Park', 'lat': 13.0787, 'lon': 77.6305, 'radius': 1.5},
    {'name': 'HSR Layout', 'lat': 12.9106, 'lon': 77.6474, 'radius': 1.2},
    {'name': 'Koramangala', 'lat': 12.9279, 'lon': 77.6271, 'radius': 1.8},
    {'name': 'Indiranagar', 'lat': 12.9784, 'lon': 77.6408, 'radius': 1.3}
]

# Calculate IT park proximity effect
def calculate_it_proximity(lat, lon):
    """Calculate proximity factor to IT parks"""
    max_effect = 0.0
    for park in it_parks:
        # Simple distance calculation (approximate)
        dist = np.sqrt((lat - park['lat'])**2 + (lon - park['lon'])**2)
        if dist < park['radius']:
            effect = (1 - dist/park['radius']) * 0.5  # Max 0.5 effect
            max_effect = max(max_effect, effect)
    return max_effect

# Get current time for peak hour calculation
current_hour = datetime.now().hour

def calculate_peak_hour_factor(hour, it_proximity):
    """Calculate peak hour factor with IT park influence"""
    # Base peak hour logic
    if (8 <= hour <= 11) or (17 <= hour <= 21):  # 8-11 AM, 5-9 PM
        base_factor = 1.0
    else:
        base_factor = 0.3
    
    # IT park proximity boost during peak hours
    if base_factor == 1.0:
        it_boost = it_proximity * 0.3  # Additional boost near IT parks
        return min(1.0, base_factor + it_boost)
    else:
        return base_factor

# Calculate IT proximity for all nodes
it_proximity_factors = []
for _, row in nodes_df.iterrows():
    lat = row['y']
    lon = row['x']
    it_proximity = calculate_it_proximity(lat, lon)
    it_proximity_factors.append(it_proximity)

# Calculate peak hour factor for all nodes
peak_hour_factors = []
for it_proximity in it_proximity_factors:
    peak_factor = calculate_peak_hour_factor(current_hour, it_proximity)
    peak_hour_factors.append(peak_factor)

# -----------------------------
# CREATE DATAFRAME
# -----------------------------
traffic_nodes_df = nodes_df.copy()

traffic_nodes_df['traffic_speed'] = traffic_speed
traffic_nodes_df['road_capacity'] = road_capacity
traffic_nodes_df['it_proximity_factor'] = it_proximity_factors
traffic_nodes_df['peak_hour_factor'] = peak_hour_factors

print(f"Current hour: {current_hour}:00")
print(f"Peak hour factor range: {min(peak_hour_factors):.3f} - {max(peak_hour_factors):.3f}")
print(f"IT proximity factor range: {min(it_proximity_factors):.3f} - {max(it_proximity_factors):.3f}")

print("Generating congestion...")

# -----------------------------
# UPDATED CONGESTION FORMULA
# -----------------------------
max_street_count = max(street_count)

congestion_score = (
    0.5 * (60 - traffic_speed) / 60 +                    # Speed factor (50% weight)
    0.3 * (street_count / max_street_count) +            # Street count factor (30% weight)
    0.2 * np.array(peak_hour_factors)                      # Peak hour factor (20% weight)
)

# normalize between 0 and 1
congestion_score = np.clip(congestion_score, 0, 1)

traffic_nodes_df['congestion_score'] = congestion_score

print(f"New congestion score range: {min(congestion_score):.3f} - {max(congestion_score):.3f}")

# -----------------------------
# SAVE
# -----------------------------
traffic_nodes_df.to_csv('traffic_nodes.csv', index=False)

print("✅ Data saved successfully!")