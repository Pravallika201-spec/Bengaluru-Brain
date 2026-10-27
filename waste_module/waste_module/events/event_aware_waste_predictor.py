"""
BENGALURU EVENT-AWARE WASTE PREDICTION ENGINE

Combines:
    1. Baseline satellite + land-use waste prediction
    2. Dynamic event-to-grid impact

The event impact increases the predicted waste only for
grids affected by upcoming events.

INPUT:
    waste_module/satellite/outputs/bengaluru_production_waste_predictions.csv
    waste_module/satellite/outputs/bengaluru_event_grid_impact.csv

OUTPUT:
    waste_module/satellite/outputs/bengaluru_event_aware_waste_predictions.csv
"""

from pathlib import Path

import pandas as pd


# ============================================================
# PATH CONFIGURATION
# ============================================================

WASTE_MODULE_DIR = Path(
    __file__
).resolve().parents[1]

OUTPUT_DIR = (
    WASTE_MODULE_DIR
    / "satellite"
    / "outputs"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# Baseline production prediction
BASELINE_FILE = (
    OUTPUT_DIR
    / "bengaluru_production_waste_predictions.csv"
)


# Event-grid impact
EVENT_IMPACT_FILE = (
    OUTPUT_DIR
    / "bengaluru_event_grid_impact.csv"
)


# Final output
OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_event_aware_waste_predictions.csv"
)


# ============================================================
# EVENT ADJUSTMENT CONFIGURATION
# ============================================================

# Maximum percentage increase caused by an event.
#
# event_impact_factor can reach approximately 0.20 for a
# high-intensity event located very close to a grid.
#
# We therefore use the impact factor directly as the
# percentage increase.
#
# Example:
#
# baseline = 1000 kg
# impact = 0.15
#
# event-adjusted =
# 1000 * (1 + 0.15)
# = 1150 kg

MAX_EVENT_INCREASE = 0.25


# ============================================================
# LOAD BASELINE PREDICTIONS
# ============================================================

def load_baseline_predictions():

    print("\nLoading baseline waste predictions...")

    print(
        f"File:\n{BASELINE_FILE}"
    )

    if not BASELINE_FILE.exists():

        raise FileNotFoundError(
            "\nBaseline prediction file not found:\n"
            f"{BASELINE_FILE}\n\n"
            "Run the production predictor first:\n"
            "python -m waste_module.ml.satellite_production_predictor"
        )

    df = pd.read_csv(
        BASELINE_FILE
    )

    print(
        f"Baseline rows: {len(df)}"
    )

    required_columns = [
        "Grid_ID",
        "Latitude",
        "Longitude",
        "predicted_daily_waste_kg",
        "waste_risk",
        "collection_priority"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "\nMissing required columns in baseline "
            f"prediction file:\n{missing}"
        )

    return df


# ============================================================
# LOAD EVENT IMPACT
# ============================================================

def load_event_impact():

    print("\nLoading event-grid impact data...")

    print(
        f"File:\n{EVENT_IMPACT_FILE}"
    )

    if not EVENT_IMPACT_FILE.exists():

        raise FileNotFoundError(
            "\nEvent impact file not found:\n"
            f"{EVENT_IMPACT_FILE}\n\n"
            "Run the event-grid mapper first:\n"
            "python -m waste_module.events.event_grid_mapper"
        )

    df = pd.read_csv(
        EVENT_IMPACT_FILE
    )

    print(
        f"Event-grid rows: {len(df)}"
    )

    required_columns = [
        "Grid_ID",
        "event_name",
        "event_date",
        "event_intensity",
        "event_impact_factor",
        "distance_from_event_km"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "\nMissing required columns in event impact file:\n"
            f"{missing}"
        )

    return df


# ============================================================
# PREPARE EVENT IMPACT
# ============================================================

def prepare_event_impact(
    event_df
):

    print(
        "\nPreparing event impact..."
    )

    # --------------------------------------------------------
    # Keep the strongest event impact for each grid.
    #
    # This is important if multiple events are available.
    # --------------------------------------------------------

    event_df = (
        event_df
        .sort_values(
            "event_impact_factor",
            ascending=False
        )
        .drop_duplicates(
            subset=["Grid_ID"],
            keep="first"
        )
        .copy()
    )

    # --------------------------------------------------------
    # Convert impact to numeric
    # --------------------------------------------------------

    event_df[
        "event_impact_factor"
    ] = pd.to_numeric(
        event_df[
            "event_impact_factor"
        ],
        errors="coerce"
    ).fillna(0.0)

    # --------------------------------------------------------
    # Safety limit
    # --------------------------------------------------------

    event_df[
        "event_impact_factor"
    ] = (
        event_df[
            "event_impact_factor"
        ]
        .clip(
            lower=0.0,
            upper=MAX_EVENT_INCREASE
        )
    )

    print(
        f"Unique event-affected grids: "
        f"{event_df['Grid_ID'].nunique()}"
    )

    print(
        "Maximum event adjustment: "
        f"{event_df['event_impact_factor'].max():.4f}"
    )

    return event_df


# ============================================================
# APPLY EVENT IMPACT
# ============================================================

def apply_event_impact(
    baseline,
    event_impact
):

    print(
        "\nApplying event impact to waste predictions..."
    )

    # --------------------------------------------------------
    # Select event columns needed for merging
    # --------------------------------------------------------

    event_columns = [
        "Grid_ID",
        "event_name",
        "event_date",
        "event_intensity",
        "event_impact_factor",
        "distance_from_event_km"
    ]

    event_data = event_impact[
        event_columns
    ].copy()

    # --------------------------------------------------------
    # Merge with all 3,053 baseline grids
    # --------------------------------------------------------

    result = baseline.merge(
        event_data,
        on="Grid_ID",
        how="left"
    )

    # --------------------------------------------------------
    # Grids without events
    # --------------------------------------------------------

    result[
        "event_impact_factor"
    ] = result[
        "event_impact_factor"
    ].fillna(0.0)

    result[
        "event_intensity"
    ] = result[
        "event_intensity"
    ].fillna(0)

    result[
        "distance_from_event_km"
    ] = result[
        "distance_from_event_km"
    ].fillna(-1)

    result[
        "event_name"
    ] = result[
        "event_name"
    ].fillna("No nearby event")

    result[
        "event_date"
    ] = result[
        "event_date"
    ].fillna("")

    # --------------------------------------------------------
    # Calculate event-adjusted waste
    # --------------------------------------------------------

    result[
        "event_adjusted_waste_kg"
    ] = (
        result[
            "predicted_daily_waste_kg"
        ]
        *
        (
            1
            +
            result[
                "event_impact_factor"
            ]
        )
    )

    result[
        "event_adjusted_waste_kg"
    ] = result[
        "event_adjusted_waste_kg"
    ].round(2)

    # --------------------------------------------------------
    # Calculate additional waste caused by event
    # --------------------------------------------------------

    result[
        "additional_event_waste_kg"
    ] = (
        result[
            "event_adjusted_waste_kg"
        ]
        -
        result[
            "predicted_daily_waste_kg"
        ]
    )

    result[
        "additional_event_waste_kg"
    ] = result[
        "additional_event_waste_kg"
    ].round(2)

    # --------------------------------------------------------
    # Event affected flag
    # --------------------------------------------------------

    result[
        "event_affected"
    ] = (
        result[
            "event_impact_factor"
        ]
        > 0
    )

    return result


# ============================================================
# CLASSIFY EVENT-AWARE RISK
# ============================================================

def classify_risk(
    waste
):

    if waste >= 1277.99:

        return "CRITICAL"

    elif waste >= 1180.28:

        return "HIGH"

    elif waste >= 1091.04:

        return "MEDIUM"

    else:

        return "LOW"


# ============================================================
# APPLY EVENT-AWARE RISK
# ============================================================

def apply_event_aware_risk(
    result
):

    print(
        "\nReclassifying event-aware waste risk..."
    )

    result[
        "event_aware_waste_risk"
    ] = result[
        "event_adjusted_waste_kg"
    ].apply(
        classify_risk
    )

    # --------------------------------------------------------
    # Collection priority
    #
    # Lower number = higher priority
    # --------------------------------------------------------

    def priority(row):

        risk = row[
            "event_aware_waste_risk"
        ]

        event = row[
            "event_affected"
        ]

        if risk == "CRITICAL":

            return "P1 - Critical"

        elif risk == "HIGH":

            if event:

                return "P2 - Event High"

            return "P2 - Urgent"

        elif risk == "MEDIUM":

            if event:

                return "P3 - Event Medium"

            return "P3 - High"

        else:

            return "P4 - Normal"

    result[
        "event_aware_collection_priority"
    ] = result.apply(
        priority,
        axis=1
    )

    return result


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_output(
    result
):

    result.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nEvent-aware prediction dataset saved:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(
    result
):

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT-AWARE WASTE PREDICTION SUMMARY"
    )

    print(
        "=" * 60
    )

    total_grids = len(
        result
    )

    affected_grids = int(
        result[
            "event_affected"
        ].sum()
    )

    unaffected_grids = (
        total_grids
        -
        affected_grids
    )

    print(
        f"\nTotal grids: "
        f"{total_grids}"
    )

    print(
        f"Event-affected grids: "
        f"{affected_grids}"
    )

    print(
        f"Unaffected grids: "
        f"{unaffected_grids}"
    )

    # --------------------------------------------------------
    # Waste totals
    # --------------------------------------------------------

    baseline_total = result[
        "predicted_daily_waste_kg"
    ].sum()

    event_total = result[
        "event_adjusted_waste_kg"
    ].sum()

    additional_total = result[
        "additional_event_waste_kg"
    ].sum()

    print(
        "\nWaste comparison:"
    )

    print(
        f"Baseline predicted waste: "
        f"{baseline_total:,.2f} kg"
    )

    print(
        f"Event-adjusted waste: "
        f"{event_total:,.2f} kg"
    )

    print(
        f"Additional event-related waste: "
        f"{additional_total:,.2f} kg"
    )

    # --------------------------------------------------------
    # Risk distribution
    # --------------------------------------------------------

    print(
        "\nBaseline risk distribution:"
    )

    print(
        result[
            "waste_risk"
        ].value_counts()
    )

    print(
        "\nEvent-aware risk distribution:"
    )

    print(
        result[
            "event_aware_waste_risk"
        ].value_counts()
    )

    # --------------------------------------------------------
    # Priority distribution
    # --------------------------------------------------------

    print(
        "\nEvent-aware collection priority:"
    )

    print(
        result[
            "event_aware_collection_priority"
        ].value_counts()
    )

    # --------------------------------------------------------
    # Top event-affected grids
    # --------------------------------------------------------

    affected = (
        result[
            result[
                "event_affected"
            ]
        ]
        .sort_values(
            "additional_event_waste_kg",
            ascending=False
        )
        .head(10)
    )

    if not affected.empty:

        print(
            "\nTop 10 event-affected grids:"
        )

        print(
            affected[
                [
                    "Grid_ID",
                    "event_name",
                    "distance_from_event_km",
                    "predicted_daily_waste_kg",
                    "event_impact_factor",
                    "event_adjusted_waste_kg",
                    "additional_event_waste_kg",
                    "event_aware_waste_risk",
                    "event_aware_collection_priority"
                ]
            ].to_string(
                index=False
            )
        )

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT-AWARE PREDICTION COMPLETED"
    )

    print(
        "=" * 60
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU EVENT-AWARE WASTE "
        "PREDICTION ENGINE"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------

    baseline = (
        load_baseline_predictions()
    )

    event_impact = (
        load_event_impact()
    )

    # --------------------------------------------------------
    # Prepare event impact
    # --------------------------------------------------------

    event_impact = (
        prepare_event_impact(
            event_impact
        )
    )

    # --------------------------------------------------------
    # Apply event adjustment
    # --------------------------------------------------------

    result = (
        apply_event_impact(
            baseline,
            event_impact
        )
    )

    # --------------------------------------------------------
    # Risk + priority
    # --------------------------------------------------------

    result = (
        apply_event_aware_risk(
            result
        )
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_output(
        result
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print_summary(
        result
    )


if __name__ == "__main__":

    main()