import torch
import pandas as pd
import numpy as np
import pickle
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import sys
import os

# Import model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.traffic_gnn import create_model


class TrafficPredictor:
    def __init__(self, model_path, data_path, node_mapping_path):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # ✅ FIXED MODEL (same as training)
        self.model = create_model(input_dim=2, hidden_dim1=16, hidden_dim2=8, output_dim=1)

        # ✅ FIXED LOADING (no model_state_dict)
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)

        self.model.to(self.device)
        self.model.eval()

        # Load graph
        self.data = torch.load(data_path, weights_only=False)

        # Load node mapping
        with open(node_mapping_path, 'rb') as f:
            self.node_to_idx = pickle.load(f)

        self.idx_to_node = {idx: node for node, idx in self.node_to_idx.items()}

        print(f"Model loaded successfully on {self.device}")
        print(f"Data loaded: {self.data.num_nodes} nodes")

    def predict_all(self):
        with torch.no_grad():
            output = self.model(
                self.data.x.to(self.device),
                self.data.edge_index.to(self.device)
            )
        return output.cpu().numpy().flatten()

    def evaluate(self):
        predictions = self.predict_all()
        actual = self.data.y.cpu().numpy().flatten()

        mse = mean_squared_error(actual, predictions)
        mae = mean_absolute_error(actual, predictions)
        r2 = r2_score(actual, predictions)
        rmse = np.sqrt(mse)

        print("\nModel Performance Metrics:")
        print(f"MSE: {mse:.4f}")
        print(f"RMSE: {rmse:.4f}")
        print(f"MAE: {mae:.4f}")
        print(f"R²: {r2:.4f}")

        return predictions, actual

    def top_congested(self, k=10):
        predictions = self.predict_all()
        actual = self.data.y.cpu().numpy().flatten()

        df = pd.read_csv('../data/traffic_nodes.csv')

        df['predicted'] = predictions
        df['actual'] = actual

        top = df.sort_values(by='predicted', ascending=False).head(k)

        print("\nTop Congested Nodes:")
        print(top[['node_id', 'predicted', 'actual', 'traffic_speed']])

        return top


def main():
    print("Initializing Predictor...")

    predictor = TrafficPredictor(
        model_path='../models/traffic_model.pth',
        data_path='../data/traffic_graph.pt',
        node_mapping_path='../data/node_mapping.pkl'
    )

    predictions, actual = predictor.evaluate()

    top = predictor.top_congested(10)

    # Save results
    top.to_csv('../output/top_congested_nodes.csv', index=False)

    print("\n✅ Prediction completed successfully!")


if __name__ == "__main__":
    main()