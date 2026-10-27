"""
End-to-end verification: REAL DATA -> traffic severity + waste severity ->
USI fusion -> band -> bilingual citizen alert -> simulated SMS.

Run: python integration/demo_usi_pipeline.py

Only exercises the areas that genuinely exist, verbatim, in BOTH modules'
location data (see integration/README.md for why it's only these 6) — no
area names or scores are invented for this demo.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from usi_engine import compute_usi
from alerts import maybe_alert_and_send

AREAS = ["Hebbal", "Whitefield", "Marathahalli", "Indiranagar", "HSR Layout", "Shivajinagar"]


def main():
    print("=" * 78)
    print("URBAN SEVERITY INDEX (USI) — end-to-end pipeline on real data")
    print("=" * 78)

    results = []
    for area in AREAS:
        result = compute_usi(area)
        results.append(result)

        print(f"\nArea: {result['area_name']}")
        print(f"  Traffic : {result['traffic']['score']} "
              f"({result['traffic']['level']}, source={result['traffic']['source']})")
        print(f"  Waste   : {result['waste']['score']} "
              f"({result['waste']['level']}, source={result['waste']['source']})")
        print(f"  USI     : {result['usi']}  Band: {result['band']}"
              f"{'  [partial data]' if result['partial_data'] else ''}"
              f"{'  [compounding bonus applied]' if result['compounding_bonus_applied'] else ''}")
        print(f"  Reason  : {result['reason']}")

        sms_result = maybe_alert_and_send(result)
        if sms_result is None:
            print("  Alert   : (band below threshold, no citizen alert triggered)")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usi_demo_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
