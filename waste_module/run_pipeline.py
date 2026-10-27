import subprocess
import sys


def run_step(number, name, module):

    print("\n" + "=" * 70)
    print(f"STEP {number}: {name}")
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, "-m", module],
        check=False
    )

    if result.returncode != 0:
        print("\n" + "=" * 70)
        print(f"STEP {number} FAILED")
        print("=" * 70)
        print(f"Module: {module}")
        sys.exit(result.returncode)

    print(f"\nSTEP {number} COMPLETED SUCCESSFULLY")


def main():

    print("=" * 70)
    print("BENGALURU SATELLITE-BASED WASTE INTELLIGENCE PIPELINE")
    print("=" * 70)

    # 1. Acquire latest Sentinel-2 image
    run_step(
        1,
        "SENTINEL-2 SATELLITE ACQUISITION",
        "waste_module.satellite.acquisition.sentinel2_loader"
    )

    # 2. Generate spectral features
    run_step(
        2,
        "SPECTRAL FEATURE GENERATION",
        "waste_module.satellite.features.spectral_features"
    )

    # 3. Train satellite + land-use Random Forest
    run_step(
        3,
        "SATELLITE WASTE MODEL",
        "waste_module.ml.satellite_waste_model"
    )

    # 4. Generate predictions for all 3,053 grids
    run_step(
        4,
        "PRODUCTION WASTE PREDICTION",
        "waste_module.ml.satellite_production_predictor"
    )

    # 5. Integrate satellite predictions with routing data
    run_step(
        5,
        "SATELLITE ROUTE INTEGRATION",
        "waste_module.ml.satellite_route_integration"
    )

    # 6. Generate dynamic routes directly from satellite predictions
    run_step(
        6,
        "DYNAMIC SATELLITE ROUTE OPTIMIZATION",
        "waste_module.satellite.routing.satellite_route_optimizer"
    )

    print("\n" + "=" * 70)
    print("ENTIRE PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 70)

    print("""
Pipeline:

Sentinel-2
    ↓
Spectral Features
    ↓
Satellite + Land-use Features
    ↓
Random Forest
    ↓
3,053 Waste Predictions
    ↓
Waste Risk Classification
    ↓
Collection Priority
    ↓
50 Trucks
    ↓
Dynamic Routes
""")


if __name__ == "__main__":
    main()