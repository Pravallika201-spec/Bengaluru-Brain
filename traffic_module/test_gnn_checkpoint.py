import sys
sys.path.append('.')
from models.traffic_gnn_v3 import create_model_v3
import torch
import os

model_path = 'models/traffic_model_v2.pth'
print(f'Testing GNN checkpoint load from: {model_path}')
print(f'File exists: {os.path.exists(model_path)}')
print(f'File size: {os.path.getsize(model_path)} bytes')

try:
    checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
    checkpoint_type = type(checkpoint)
    print(f'Checkpoint type: {checkpoint_type}')
    
    if isinstance(checkpoint, dict):
        print(f'Checkpoint keys: {list(checkpoint.keys())}')
        if 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
            print(f'Loaded state dict with {len(state_dict)} keys')
            print(f'Sample keys: {list(state_dict.keys())[:5]}')
        else:
            state_dict = checkpoint
            print(f'Using direct state dict with {len(state_dict)} keys')
            print(f'Sample keys: {list(state_dict.keys())[:5]}')
    else:
        print('Checkpoint is not a dict')
        state_dict = None
    
    # Create model
    model = create_model_v3(input_dim=12, hidden_dim1=64, hidden_dim2=32, hidden_dim3=16, output_dim=1)
    if state_dict:
        model.load_state_dict(state_dict)
    print('SUCCESS: Model loaded successfully')
    print(f'Model architecture: {model}')
    
    # Test inference
    model.eval()
    with torch.no_grad():
        # Create dummy input
        x = torch.randn(10, 12)  # 10 nodes, 12 features
        edge_index = torch.randint(0, 10, (2, 20))  # 20 edges
        output = model(x, edge_index)
        print('SUCCESS: Inference test successful')
        print(f'Output shape: {output.shape}')
        print(f'Output range: [{output.min().item():.3f}, {output.max().item():.3f}]')
        
        # Model output is predicted speed in km/h directly
        speed_kmh = output.mean().item()
        print(f'Predicted speed: {speed_kmh:.1f} km/h')
    
except Exception as e:
    print(f'ERROR: Failed to load checkpoint: {e}')
    import traceback
    traceback.print_exc()
