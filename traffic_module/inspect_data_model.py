import pandas as pd
from pathlib import Path
import os
print('cwd', os.getcwd())
print('traffic_nodes exists', Path('data/traffic_nodes.csv').exists())
threads = []
if Path('data/traffic_nodes.csv').exists():
    df = pd.read_csv('data/traffic_nodes.csv')
    print('traffic_nodes cols', list(df.columns))
    print(df.head(3).to_dict(orient='records'))
    print('traffic_speed min/max', df['traffic_speed'].min(), df['traffic_speed'].max())
    print('congestion_score min/max', df['congestion_score'].min(), df['congestion_score'].max())
if Path('data/edges.csv').exists():
    df2 = pd.read_csv('data/edges.csv', nrows=3)
    print('edges cols', list(df2.columns))
    print('edges sample', df2.to_dict(orient='records'))
    print('edges highway sample', df2['highway'].unique()[:10])
path = Path('models/traffic_model.pth')
print('model exists', path.exists())
try:
    import torch
    if path.exists():
        d = torch.load(str(path), map_location='cpu')
        print('model type', type(d))
        if isinstance(d, dict):
            print('keys', list(d.keys())[:10])
        else:
            print('loaded object repr', repr(d)[:200])
except Exception as e:
    print('torch load failed', e)
