import folium
import pandas as pd
import numpy as np
import osmnx as ox
import networkx as nx
from folium.plugins import HeatMap
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from branca.colormap import LinearColormap

class TrafficVisualizer:
    """
    Visualizer for traffic predictions on Bangalore map.
    """
    
    def __init__(self, predictions_path, graph_path):
        """
        Initialize the visualizer.
        
        Args:
            predictions_path: Path to predictions CSV
            graph_path: Path to road graph
        """
        # Load predictions
        self.predictions_df = pd.read_csv(predictions_path)
        
        # Load graph
        self.G = ox.load_graphml(graph_path)
        
        print(f"Loaded {len(self.predictions_df)} predictions")
        print(f"Loaded graph with {self.G.number_of_nodes()} nodes and {self.G.number_of_edges()} edges")
    
    def create_congestion_heatmap(self, output_path, zoom_start=12):
        """
        Create a heatmap of traffic congestion.
        
        Args:
            output_path: Path to save the HTML map
            zoom_start: Initial zoom level
        """
        # Create base map centered on Bangalore
        bangalore_coords = [12.9716, 77.5946]
        m = folium.Map(location=bangalore_coords, zoom_start=zoom_start, tiles='OpenStreetMap')
        
        # Prepare heat data
        heat_data = []
        for idx, row in self.predictions_df.iterrows():
            if not pd.isna(row['y']) and not pd.isna(row['x']):
                # Use predicted congestion as intensity
                intensity = row['predicted_congestion']
                heat_data.append([row['y'], row['x'], intensity])
        
        # Create heatmap
        if heat_data:
            HeatMap(heat_data, 
                   min_opacity=0.2,
                   max_zoom=18,
                   radius=15,
                   blur=10,
                   gradient={0.2: 'green', 0.4: 'yellow', 0.6: 'orange', 0.8: 'red', 1.0: 'darkred'}
                  ).add_to(m)
        
        # Add title
        title_html = '''
        <h3 align="center" style="font-size:20px"><b>Bangalore Traffic Congestion Heatmap</b></h3>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Save map
        m.save(output_path)
        print(f"Heatmap saved to {output_path}")
        
        return m
    
    def create_congestion_colormap(self, output_path, zoom_start=12, sample_size=5000):
        """
        Create a color-coded map of traffic congestion.
        
        Args:
            output_path: Path to save the HTML map
            zoom_start: Initial zoom level
            sample_size: Number of nodes to display (to avoid overcrowding)
        """
        # Create base map
        bangalore_coords = [12.9716, 77.5946]
        m = folium.Map(location=bangalore_coords, zoom_start=zoom_start, tiles='OpenStreetMap')
        
        # Create colormap
        colormap = LinearColormap(
            colors=['green', 'yellow', 'orange', 'red', 'darkred'],
            vmin=self.predictions_df['predicted_congestion'].min(),
            vmax=self.predictions_df['predicted_congestion'].max(),
            caption='Traffic Congestion Level'
        )
        
        # Sample nodes to display (to avoid overcrowding)
        sample_df = self.predictions_df.sample(n=min(sample_size, len(self.predictions_df)), random_state=42)
        
        # Add markers for each node
        for idx, row in sample_df.iterrows():
            if not pd.isna(row['y']) and not pd.isna(row['x']):
                congestion = row['predicted_congestion']
                color = colormap(congestion)
                
                # Create popup with information
                popup_text = f"""
                Node ID: {int(row['node_id'])}<br>
                Predicted Congestion: {congestion:.3f}<br>
                Actual Congestion: {row['congestion_score']:.3f}<br>
                Traffic Speed: {row['traffic_speed']:.1f} km/h<br>
                Rainfall: {row['rainfall']:.1f} mm<br>
                Road Capacity: {int(row['road_capacity'])} lanes
                """
                
                folium.CircleMarker(
                    location=[row['y'], row['x']],
                    radius=5,
                    popup=folium.Popup(popup_text, max_width=300),
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=1
                ).add_to(m)
        
        # Add colormap to map
        colormap.add_to(m)
        
        # Add title
        title_html = '''
        <h3 align="center" style="font-size:20px"><b>Bangalore Traffic Congestion Map</b></h3>
        <p align="center" style="font-size:14px">Color: Green (Low) → Red (High Congestion)</p>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Save map
        m.save(output_path)
        print(f"Colormap saved to {output_path}")
        
        return m
    
    def create_top_congested_map(self, output_path, top_k=50, zoom_start=13):
        """
        Create a map highlighting top congested areas.
        
        Args:
            output_path: Path to save the HTML map
            top_k: Number of top congested nodes to highlight
            zoom_start: Initial zoom level
        """
        # Get top congested nodes
        top_congested = self.predictions_df.nlargest(top_k, 'predicted_congestion')
        
        # Create base map
        # Center on the average location of top congested nodes
        center_lat = top_congested['y'].mean()
        center_lon = top_congested['x'].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles='OpenStreetMap')
        
        # Add markers for top congested nodes
        for idx, row in top_congested.iterrows():
            if not pd.isna(row['y']) and not pd.isna(row['x']):
                congestion = row['predicted_congestion']
                
                # Size based on congestion level
                radius = 5 + congestion * 15
                
                # Color based on congestion level
                if congestion > 0.8:
                    color = 'darkred'
                elif congestion > 0.6:
                    color = 'red'
                elif congestion > 0.4:
                    color = 'orange'
                else:
                    color = 'yellow'
                
                # Create popup
                popup_text = f"""
                <b>Top Congested Area</b><br>
                Node ID: {int(row['node_id'])}<br>
                Predicted Congestion: {congestion:.3f}<br>
                Actual Congestion: {row['congestion_score']:.3f}<br>
                Traffic Speed: {row['traffic_speed']:.1f} km/h<br>
                Rainfall: {row['rainfall']:.1f} mm<br>
                Road Capacity: {int(row['road_capacity'])} lanes
                """
                
                folium.CircleMarker(
                    location=[row['y'], row['x']],
                    radius=radius,
                    popup=folium.Popup(popup_text, max_width=300),
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.8,
                    weight=2
                ).add_to(m)
        
        # Add title
        title_html = f'''
        <h3 align="center" style="font-size:20px"><b>Top {top_k} Most Congested Areas in Bangalore</b></h3>
        <p align="center" style="font-size:14px">Circle size indicates congestion level</p>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Save map
        m.save(output_path)
        print(f"Top congested map saved to {output_path}")
        
        return m
    
    def create_prediction_analysis_plot(self, output_path):
        """
        Create analysis plots for predictions.
        
        Args:
            output_path: Path to save the plot
        """
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # Plot 1: Predicted vs Actual
        axes[0, 0].scatter(self.predictions_df['congestion_score'], 
                          self.predictions_df['predicted_congestion'], 
                          alpha=0.5, s=1)
        axes[0, 0].plot([0, 1], [0, 1], 'r--', label='Perfect Prediction')
        axes[0, 0].set_xlabel('Actual Congestion')
        axes[0, 0].set_ylabel('Predicted Congestion')
        axes[0, 0].set_title('Predicted vs Actual Congestion')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # Plot 2: Prediction Error Distribution
        errors = self.predictions_df['predicted_congestion'] - self.predictions_df['congestion_score']
        axes[0, 1].hist(errors, bins=50, alpha=0.7, edgecolor='black')
        axes[0, 1].set_xlabel('Prediction Error')
        axes[0, 1].set_ylabel('Frequency')
        axes[0, 1].set_title('Prediction Error Distribution')
        axes[0, 1].grid(True, alpha=0.3)
        
        # Plot 3: Congestion Distribution
        axes[1, 0].hist(self.predictions_df['predicted_congestion'], bins=50, alpha=0.7, 
                       label='Predicted', edgecolor='black')
        axes[1, 0].hist(self.predictions_df['congestion_score'], bins=50, alpha=0.7, 
                       label='Actual', edgecolor='black')
        axes[1, 0].set_xlabel('Congestion Score')
        axes[1, 0].set_ylabel('Frequency')
        axes[1, 0].set_title('Congestion Score Distribution')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        
        # Plot 4: Traffic Speed vs Congestion
        axes[1, 1].scatter(self.predictions_df['traffic_speed'], 
                          self.predictions_df['predicted_congestion'], 
                          alpha=0.5, s=1)
        axes[1, 1].set_xlabel('Traffic Speed (km/h)')
        axes[1, 1].set_ylabel('Predicted Congestion')
        axes[1, 1].set_title('Traffic Speed vs Predicted Congestion')
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"Analysis plot saved to {output_path}")

def main():
    """Main visualization function."""
    print("Creating traffic prediction visualizations...")
    
    # Initialize visualizer
    visualizer = TrafficVisualizer(
        predictions_path='../output/traffic_predictions.csv',
        graph_path='../data/bangalore.graphml'
    )
    
    # Create different visualizations
    print("\n1. Creating congestion heatmap...")
    visualizer.create_congestion_heatmap('../output/traffic_heatmap.html')
    
    print("\n2. Creating congestion colormap...")
    visualizer.create_congestion_colormap('../output/traffic_colormap.html')
    
    print("\n3. Creating top congested areas map...")
    visualizer.create_top_congested_map('../output/top_congested_map.html', top_k=50)
    
    print("\n4. Creating prediction analysis plots...")
    visualizer.create_prediction_analysis_plot('../output/prediction_analysis.png')
    
    print("\nAll visualizations created successfully!")
    print("Open the HTML files in your browser to view the interactive maps.")

if __name__ == "__main__":
    main()
