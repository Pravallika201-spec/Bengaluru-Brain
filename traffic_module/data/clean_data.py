import pandas as pd

print("Loading datasets...")

# Load Excel files
it_df = pd.read_excel('IT PARKS DATASET.xlsx')
shift_df = pd.read_excel('Shift Data.xlsx')

# -----------------------------
# CLEAN IT DATA
# -----------------------------
it_df = it_df.dropna(how='all')   # remove empty rows
it_df = it_df.ffill()             # fill missing values
it_df = it_df.drop_duplicates()   # remove duplicates

# -----------------------------
# CLEAN SHIFT DATA
# -----------------------------
shift_df = shift_df.dropna(how='all')
shift_df = shift_df.ffill()
shift_df = shift_df.drop_duplicates()

# -----------------------------
# SAVE CLEAN DATA
# -----------------------------
it_df.to_csv('clean_it_parks.csv', index=False)
shift_df.to_csv('clean_shift_data.csv', index=False)

print("✅ Cleaned files saved successfully!")
print("IT Data shape:", it_df.shape)
print("Shift Data shape:", shift_df.shape)