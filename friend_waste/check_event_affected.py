"""
Checks why event_affected in bengaluru_event_aware_waste_predictions.csv
flags far more grid cells than the single tracked event in
bengaluru_events.csv would plausibly explain.

USAGE (from waste_module/, with the venv active):
    python check_event_affected.py
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SATELLITE_OUTPUT = os.path.join(BASE_DIR, "satellite", "outputs")

EVENT_WASTE_FILE = os.path.join(SATELLITE_OUTPUT, "bengaluru_event_aware_waste_predictions.csv")
EVENT_FILE = os.path.join(SATELLITE_OUTPUT, "bengaluru_events.csv")

def main():
    if not os.path.exists(EVENT_WASTE_FILE):
        print(f"Not found: {EVENT_WASTE_FILE}")
        return

    df = pd.read_csv(EVENT_WASTE_FILE)
    print(f"Total grid cells in file: {len(df):,}")
    print(f"Columns: {list(df.columns)}\n")

    if "event_affected" not in df.columns:
        print("No 'event_affected' column found — can't diagnose further.")
        return

    print("Value counts for event_affected:")
    print(df["event_affected"].value_counts(dropna=False).to_string())
    print()

    affected = df[df["event_affected"] == 1] if df["event_affected"].dtype != bool else df[df["event_affected"]]
    print(f"Rows flagged as event_affected: {len(affected):,}")

    if "additional_event_waste_kg" in df.columns:
        print(f"\nadditional_event_waste_kg stats for affected rows:")
        print(affected["additional_event_waste_kg"].describe().to_string())
        zero_extra = (affected["additional_event_waste_kg"] == 0).sum()
        print(f"\nAffected rows with ZERO additional waste: {zero_extra:,} "
              f"({zero_extra/len(affected)*100:.1f}% of flagged rows)" if len(affected) else "")

    if os.path.exists(EVENT_FILE):
        events = pd.read_csv(EVENT_FILE)
        print(f"\nEvents file has {len(events)} row(s). Columns: {list(events.columns)}")
        print(events.to_string())

if __name__ == "__main__":
    main()