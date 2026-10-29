import geopandas as gpd
import pandas as pd

# Check what's in boundaries file
bounds = gpd.read_file(
    'data/processed/bengaluru_area_boundaries.gpkg'
)
print('=== BOUNDARIES FILE ===')
print(f'Total rows: {len(bounds)}')
print(f'Columns: {list(bounds.columns)}')
print()
print('First 5 rows:')
print(bounds[bounds.columns[:5]].head())
print()

# Check admin levels if exists
if 'area_admin_level' in bounds.columns:
    print('Admin levels:')
    print(bounds['area_admin_level'].value_counts())
elif 'admin_level' in bounds.columns:
    print('Admin levels:')
    print(bounds['admin_level'].value_counts())

print()
# Check overflow CSV area count
ov = pd.read_csv('data/processed/bengaluru_area_overflow_predictions.csv')
print(f'=== OVERFLOW CSV ===')
print(f'Total areas: {len(ov)}')
print(f'Sample names: {list(ov["area_name"].head(5))}')