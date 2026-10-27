"""
============================================================
OPTION 1 — PER-CAPITA WASTE GENERATION MODEL
============================================================

An independent, non-satellite prediction of ward-level waste generation,
based on standard municipal solid-waste engineering practice rather than
remote sensing.

METHODOLOGY (real published figures, not invented numbers):

  1. Estimate ward population from residential building counts (OSM),
     using Karnataka's average household size.
       Source: NFHS-5 (2019-21) Karnataka — 4.2 persons/household

  2. Apply a per-capita waste generation rate.
       Source: Bengaluru-specific figure, 0.53 kg/person/day
       (CPHEEO's broader metro-city range is 0.45-0.65 kg/person/day —
        Bengaluru's figure sits within that range)

  3. Add a commercial contribution from shop/restaurant/market density,
     using a flat per-POI estimate (an explicit simplifying assumption —
     CPHEEO gives a per-m^2 commercial rate, but per-POI floor area isn't
     available from OSM tags directly, so a flat estimate is used instead
     and clearly flagged as an assumption below).

  4. Classify wards into CRITICAL/HIGH/MEDIUM/LOW using the SAME
     percentile-rank method as the satellite-based model, so results are
     directly comparable between the two independent approaches.

Input:
    ward_osm_features.csv          (from fetch_osm_ward_features.py)

Output:
    bengaluru_percapita_waste_predictions.csv
============================================================
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)
PROCESSED_DIR = os.path.join(BASE_DIR, "waste_module", "data", "processed")

INPUT_FILE = os.path.join(PROCESSED_DIR, "ward_osm_features.csv")
OUTPUT_FILE = os.path.join(PROCESSED_DIR, "bengaluru_percapita_waste_predictions.csv")

# ============================================================
# GROUNDED ASSUMPTIONS — change these here if you find better sourced
# numbers; every one of these is cited in the docstring above.
# ============================================================

AVG_HOUSEHOLD_SIZE = 4.2                # NFHS-5 Karnataka, 2019-21
PER_CAPITA_WASTE_KG_PER_DAY = 0.53      # Bengaluru-specific published figure
COMMERCIAL_WASTE_KG_PER_POI_PER_DAY = 5.0  # Explicit simplifying assumption —
                                            # flat estimate per shop/restaurant/
                                            # market, not derived from a cited
                                            # per-unit source. Documented as a
                                            # limitation, not hidden.

# Known total population of the Greater Bengaluru Area (GBA), used to CALIBRATE
# the OSM-building-derived estimate below. OSM's building footprint coverage in
# India is nowhere near complete (most real houses aren't individually mapped),
# so raw building counts drastically UNDER-estimate absolute population — a raw
# run of this model summed to ~334,000 people citywide against a real population
# in the crores. Rather than present that obviously wrong absolute number, OSM
# building density is used to determine the RELATIVE distribution across wards
# (which wards likely have proportionally more people), then scaled so the
# total matches this known, real figure. This is a standard technique called
# dasymetric mapping calibrated to a known total.
#   Source: Bengaluru's population cited as 1.50 crore (15,000,000) in the
#   Greater Bengaluru Governance Act debate, Karnataka Legislative Assembly, 2025.
KNOWN_TOTAL_POPULATION = 15_000_000


def load_features():
    print("\nLoading ward OSM features...")
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"\n{INPUT_FILE} not found.\n"
            "Run fetch_osm_ward_features.py first to generate it."
        )
    df = pd.read_csv(INPUT_FILE)
    print(f"Wards loaded: {len(df):,}")
    return df


def estimate_population(df):
    df = df.copy()

    # Raw estimate from OSM building counts — kept visible in the output for
    # transparency, but NOT used directly, since OSM's incomplete building
    # coverage makes this badly under-estimate the real total.
    df["raw_osm_estimated_population"] = (
        df["residential_building_count"] * AVG_HOUSEHOLD_SIZE
    ).round().astype(int)

    raw_total = df["raw_osm_estimated_population"].sum()
    calibration_factor = KNOWN_TOTAL_POPULATION / raw_total if raw_total > 0 else 1.0

    print(f"\nRaw OSM-derived population estimate (all wards): {raw_total:,}")
    print(f"Known real GBA population: {KNOWN_TOTAL_POPULATION:,}")
    print(f"Calibration factor applied: {calibration_factor:.2f}x")
    print("(This scales the relative distribution from OSM building density up")
    print(" to match the real citywide total — see KNOWN_TOTAL_POPULATION's")
    print(" comment for why this is necessary and what it does and doesn't fix.)")

    df["estimated_population"] = (
        df["raw_osm_estimated_population"] * calibration_factor
    ).round().astype(int)

    return df


# Mumbai's Dharavi — often cited as one of the densest urban settlements on
# Earth — runs around 270,000-330,000 people/km^2. Nothing in Bengaluru should
# plausibly exceed that. Any ward that does is a data artifact, not a real
# population, and gets capped rather than presented as-is.
MAX_PLAUSIBLE_DENSITY_PER_KM2 = 100_000

# A density cap alone isn't enough — a large-AREA ward can satisfy it while
# still being implausible in absolute terms (e.g. 100,000/km2 x 4.24 km2 =
# 424,059 people in one ward, over 10x this city's average ward population of
# ~40,650). The GBA's 2025 restructuring specifically created MORE, SMALLER
# wards than the previous 198-ward system for more manageable governance —
# a single ward holding 10x the average defeats that purpose and isn't
# credible. Capped at roughly 3x the citywide average ward population as a
# generous but bounded ceiling.
MAX_ABSOLUTE_POPULATION_PER_WARD = 120_000


def cap_and_redistribute_population(df, max_density=MAX_PLAUSIBLE_DENSITY_PER_KM2, max_iterations=20):
    """
    Cap any ward whose implied density exceeds a physically plausible bound,
    and redistribute the excess population across the remaining wards — so
    the citywide total still matches the known real population, but no
    single ward can show an impossible number.

    Redistribution is proportional to each ward's remaining HEADROOM (its own
    cap minus its current population), not its current population. This
    matters: distributing proportional to current population can push
    already-large wards over the cap too, causing an endless back-and-forth
    that never actually converges (this was tried first and failed — it
    oscillated between ~23 and ~52 violating wards indefinitely). Distributing
    by headroom guarantees no redistributed amount can ever exceed a ward's
    own remaining capacity, so this always converges.
    """
    df = df.copy()
    target_total = df["estimated_population"].sum()
    df["was_capped"] = False
    density_capacity = max_density * df["ward_area_km2"]
    max_capacity = density_capacity.clip(upper=MAX_ABSOLUTE_POPULATION_PER_WARD).round().astype(int)

    converged = False
    for iteration in range(max_iterations):
        over_mask = df["estimated_population"] > max_capacity
        n_over = int(over_mask.sum())

        if n_over == 0:
            converged = True
            if iteration == 0:
                print(f"\nNo wards exceed the {max_density:,}/km² plausibility bound.")
            break

        excess = int((df.loc[over_mask, "estimated_population"] - max_capacity.loc[over_mask]).sum())
        print(f"\nCapping pass {iteration + 1}: {n_over} ward(s) exceed "
              f"{max_density:,}/km² (total excess: {excess:,} people) — "
              f"capping and redistributing by available headroom...")

        df.loc[over_mask, "was_capped"] = True
        df.loc[over_mask, "estimated_population"] = max_capacity.loc[over_mask]

        under_mask = ~over_mask
        headroom = (max_capacity.loc[under_mask] - df.loc[under_mask, "estimated_population"]).clip(lower=0)
        total_headroom = int(headroom.sum())

        if total_headroom <= 0:
            print("WARNING: no remaining headroom anywhere to absorb the excess — "
                  "the plausibility cap may be too strict for this city's total area. "
                  "Stopping redistribution; some excess may be lost from the total.")
            break

        distribute = (headroom / total_headroom * min(excess, total_headroom))
        distribute = distribute.clip(upper=headroom)  # never exceed a ward's own headroom
        df.loc[under_mask, "estimated_population"] = (
            df.loc[under_mask, "estimated_population"] + distribute
        ).round().astype(int)

    if not converged:
        remaining = int((df["estimated_population"] > max_capacity).sum())
        if remaining:
            print(f"\nWARNING: stopped after {max_iterations} passes with {remaining} ward(s) "
                  f"still technically over the cap. This is a real limitation to disclose, "
                  f"not something to present as fully resolved.")

    # Redistribution happens in whole-person rounding, so re-normalize back to
    # the exact known total to correct any small drift.
    final_total = df["estimated_population"].sum()
    if final_total > 0:
        adjustment = target_total / final_total
        df["estimated_population"] = (df["estimated_population"] * adjustment).round().astype(int)

    # The normalization above can nudge an already-capped ward fractionally
    # back over the line (by rounding, e.g. 1 person) — clip one last time so
    # the cap is a hard guarantee, not "usually true." This costs a handful of
    # people off the exact total citywide, which is negligible next to
    # presenting even one technically-over-cap value in the final output.
    df["estimated_population"] = df["estimated_population"].clip(upper=max_capacity)

    n_capped = int(df["was_capped"].sum())
    if n_capped:
        print(f"\n{n_capped} ward(s) were capped at the plausibility bound and had their "
              f"excess population redistributed to the other {len(df) - n_capped} wards.")
        print("These are flagged in the output with was_capped=True — worth checking their")
        print("OSM building data directly if you want to understand the root cause, but the")
        print("final numbers are now all physically plausible.")

    df["population_density_per_km2"] = (
        df["estimated_population"] / df["ward_area_km2"].replace(0, pd.NA)
    ).round(0)
    # Population is already correctly capped above — this just guards against
    # a stray 1-unit rounding overshoot when density gets recomputed from the
    # (rounded) population and the exact area, so the reported metric can
    # never show a value technically over the stated cap.
    df["population_density_per_km2"] = df["population_density_per_km2"].clip(upper=max_density)

    return df


def estimate_waste(df):
    df = df.copy()
    df["residential_waste_kg"] = (
        df["estimated_population"] * PER_CAPITA_WASTE_KG_PER_DAY
    ).round(2)
    df["commercial_waste_kg"] = (
        df["commercial_poi_count"] * COMMERCIAL_WASTE_KG_PER_POI_PER_DAY
    ).round(2)
    df["total_predicted_waste_kg"] = (
        df["residential_waste_kg"] + df["commercial_waste_kg"]
    ).round(2)
    return df


def classify_risk(df):
    """Same percentile-rank + weighted-index method as the satellite-based
    model (area_overflow_predictor.py), so the two are directly comparable."""
    print("\nClassifying overflow risk (percentile-rank method, matching the satellite model)...")

    df = df.copy()
    df["Waste_Percentage"] = df["total_predicted_waste_kg"].rank(pct=True) * 100
    df["Density_Percentage"] = (
        df["total_predicted_waste_kg"] / df["ward_area_km2"].replace(0, pd.NA)
    ).rank(pct=True) * 100
    df["Density_Percentage"] = df["Density_Percentage"].fillna(df["Waste_Percentage"])

    # Total waste 70%, waste-per-area (density) 30% — density matters more
    # here than in the satellite model, since this model has no peak-cell
    # signal to draw on, only ward totals and ward size.
    df["Overflow_Index"] = (
        0.70 * df["Waste_Percentage"] + 0.30 * df["Density_Percentage"]
    ).round(2)

    def classify(value):
        if value >= 85:
            return "CRITICAL"
        elif value >= 65:
            return "HIGH"
        elif value >= 40:
            return "MEDIUM"
        return "LOW"

    df["Overflow_Risk"] = df["Overflow_Index"].apply(classify)
    return df


def display_results(df):
    print("\n" + "=" * 70)
    print("PER-CAPITA MODEL — RESULTS")
    print("=" * 70)

    print(f"\nTotal estimated population (all wards): {df['estimated_population'].sum():,}")
    print(f"Total predicted waste: {df['total_predicted_waste_kg'].sum():,.0f} kg/day "
          f"({df['total_predicted_waste_kg'].sum()/1000:,.1f} tonnes/day)")

    print("\nRisk distribution:")
    print(df["Overflow_Risk"].value_counts().to_string())

    print("\nTop 15 wards by predicted waste:")
    print(df.sort_values("total_predicted_waste_kg", ascending=False)
          .head(15)[["area_name", "estimated_population", "total_predicted_waste_kg", "Overflow_Risk"]]
          .to_string(index=False))

    print("\n" + "-" * 70)
    print("HONEST LIMITATION — read before presenting these numbers:")
    print("-" * 70)
    print("Calibration fixes the CITYWIDE TOTAL to match the real population,")
    print("but it does NOT fix uneven OSM mapping quality between wards. If")
    print("some wards are much better-mapped in OSM than others (e.g. newer")
    print("apartment complexes vs. older or informal settlements), those")
    print("well-mapped wards will still look disproportionately populous")
    print("relative to poorly-mapped ones, even after calibration. Absolute")
    print("totals are now realistic; relative ranking between specific wards")
    print("should be treated as approximate, not precise.")


def main():
    print("=" * 70)
    print("OPTION 1 — PER-CAPITA WASTE GENERATION MODEL")
    print("(independent of satellite imagery)")
    print("=" * 70)

    df = load_features()
    df = estimate_population(df)
    df = cap_and_redistribute_population(df)
    df = estimate_waste(df)
    df = classify_risk(df)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved to:\n{OUTPUT_FILE}")

    display_results(df)

    print("\n" + "=" * 70)
    print("PER-CAPITA MODEL COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()