import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import numpy as np
import matplotlib.pyplot as plt
import os
import sys

# Import model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.traffic_gnn import create_model, count_parameters


class TrafficTrainer:
    def __init__(self, model, device='cpu'):
        self.model = model.to(device)
        self.device = device
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(model.parameters(), lr=0.001)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, patience=5)

        self.train_losses = []
        self.val_losses = []

        self.best_val_loss = float('inf')
        self.best_model_state = None

    def train_epoch(self, data):
        self.model.train()
        self.optimizer.zero_grad()

        output = self.model(data.x.to(self.device), data.edge_index.to(self.device))

        loss = self.criterion(
            output[data.train_mask],
            data.y[data.train_mask].to(self.device)
        )

        loss.backward()
        self.optimizer.step()

        return loss.item()

    def validate(self, data):
        self.model.eval()
        with torch.no_grad():
            output = self.model(data.x.to(self.device), data.edge_index.to(self.device))

            loss = self.criterion(
                output[data.val_mask],
                data.y[data.val_mask].to(self.device)
            )

            y_true = data.y[data.val_mask].cpu().numpy()
            y_pred = output[data.val_mask].cpu().numpy()

            mse = mean_squared_error(y_true, y_pred)
            mae = mean_absolute_error(y_true, y_pred)
            r2 = r2_score(y_true, y_pred)

        return loss.item(), mse, mae, r2

    def train(self, data, epochs=50, val_split=0.2, patience=10):
        print(f"Training for {epochs} epochs...")

        num_nodes = data.num_nodes
        indices = np.random.permutation(num_nodes)
        split = int(num_nodes * (1 - val_split))

        train_idx = indices[:split]
        val_idx = indices[split:]

        data.train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        data.val_mask = torch.zeros(num_nodes, dtype=torch.bool)

        data.train_mask[train_idx] = True
        data.val_mask[val_idx] = True

        print(f"Train nodes: {data.train_mask.sum().item()}")
        print(f"Val nodes: {data.val_mask.sum().item()}")

        no_improve = 0

        for epoch in range(epochs):
            train_loss = self.train_epoch(data)
            val_loss, mse, mae, r2 = self.validate(data)

            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)

            self.scheduler.step(val_loss)

            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.best_model_state = self.model.state_dict()
                no_improve = 0
            else:
                no_improve += 1

            if epoch % 5 == 0:
                print(f"Epoch {epoch+1}/{epochs} | "
                      f"Train Loss: {train_loss:.4f} | "
                      f"Val Loss: {val_loss:.4f} | "
                      f"R²: {r2:.4f}")

            if no_improve >= patience:
                print("Early stopping")
                break

        # Load best model
        self.model.load_state_dict(self.best_model_state)

    def save(self, path):
        torch.save(self.model.state_dict(), path)
        print(f"Model saved at {path}")

    def plot(self):
        plt.plot(self.train_losses, label='Train')
        plt.plot(self.val_losses, label='Val')
        plt.legend()
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.title("Training Curve")
        plt.show()


def main():
    print("Loading graph...")

    data = torch.load('../data/traffic_graph.pt', weights_only=False)
    print(data)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = create_model(input_dim=3, hidden_dim1=32, hidden_dim2=16, output_dim=1)

    trainer = TrafficTrainer(model, device)

    trainer.train(data)

    trainer.save('../models/traffic_model.pth')

    trainer.plot()

    print("\nFinal Evaluation:")
    val_loss, mse, mae, r2 = trainer.validate(data)

    print(f"MSE: {mse:.4f}")
    print(f"MAE: {mae:.4f}")
    print(f"R²: {r2:.4f}")


if __name__ == "__main__":
    main()