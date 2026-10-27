"""
BENGALURU DYNAMIC EVENT INGESTION ENGINE

Source:
Karnataka Tourism public Events & Festivals page.

Purpose:
1. Download upcoming events from Karnataka Tourism.
2. Extract Bengaluru-related events.
3. Remove website navigation/irrelevant sections.
4. Parse event dates.
5. Classify event type.
6. Estimate event intensity.
7. Save standardized event data.

Output:
waste_module/satellite/outputs/bengaluru_events.csv
"""

import re
import requests
import pandas as pd

from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_URL = (
    "https://karnatakatourism.org/en/events/"
)

CITY_NAME = "Bengaluru"

FORECAST_DAYS = 90


# ============================================================
# OUTPUT PATH
# ============================================================

OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "satellite"
    / "outputs"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_events.csv"
)


# ============================================================
# EVENT DATASET COLUMNS
# ============================================================

EVENT_COLUMNS = [
    "event_id",
    "event_name",
    "event_type",
    "description",
    "start_datetime",
    "end_datetime",
    "latitude",
    "longitude",
    "location",
    "city",
    "expected_attendance",
    "event_intensity",
    "source",
    "last_updated"
]


# ============================================================
# DOWNLOAD KARNATAKA TOURISM PAGE
# ============================================================

def download_page():

    print(
        "\nConnecting to Karnataka Tourism..."
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        )
    }

    try:

        response = requests.get(
            SOURCE_URL,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        print(
            "Page downloaded successfully."
        )

        print(
            f"HTTP status: {response.status_code}"
        )

        return response.text

    except requests.RequestException as e:

        print(
            "\nERROR: Unable to download "
            "Karnataka Tourism page."
        )

        print(e)

        return None


# ============================================================
# PARSE DATE
# ============================================================

def parse_event_dates(text):

    if not text:

        return None, None

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    current_year = datetime.now().year

    month_map = {

        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12

    }

    # --------------------------------------------------------
    # Date range
    # Example:
    # 14Sept-14Sept
    # 23Sept-2Oct
    # --------------------------------------------------------

    range_match = re.search(
        r"(\d{1,2})\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)"
        r"\s*[-]\s*"
        r"(\d{1,2})\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)",
        text,
        re.IGNORECASE
    )

    try:

        if range_match:

            start_day = int(
                range_match.group(1)
            )

            start_month = month_map[
                range_match.group(2).lower()
            ]

            end_day = int(
                range_match.group(3)
            )

            end_month = month_map[
                range_match.group(4).lower()
            ]

            start_date = datetime(
                current_year,
                start_month,
                start_day
            )

            end_date = datetime(
                current_year,
                end_month,
                end_day
            )

            if end_date < start_date:

                end_date = end_date.replace(
                    year=current_year + 1
                )

            return start_date, end_date

        # ----------------------------------------------------
        # Single date
        # ----------------------------------------------------

        single_match = re.search(
            r"(\d{1,2})\s*"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
            r"Sep|Sept|Oct|Nov|Dec)",
            text,
            re.IGNORECASE
        )

        if single_match:

            day = int(
                single_match.group(1)
            )

            month = month_map[
                single_match.group(2).lower()
            ]

            date = datetime(
                current_year,
                month,
                day
            )

            return date, date

    except ValueError:

        return None, None

    return None, None


# ============================================================
# DETERMINE EVENT TYPE
# ============================================================

def determine_event_type(
    event_name
):

    name = event_name.lower()

    if any(
        word in name
        for word in [
            "festival",
            "utsava",
            "utsav",
            "mela",
            "dasara",
            "ganesha",
            "karaga",
            "deepavali",
            "diwali",
            "holi",
            "ugadi",
            "ganesh"
        ]
    ):

        return "Festival"

    if any(
        word in name
        for word in [
            "flower",
            "garden",
            "exhibition",
            "expo"
        ]
    ):

        return "Exhibition"

    if any(
        word in name
        for word in [
            "fair",
            "market",
            "mela"
        ]
    ):

        return "Fair"

    if any(
        word in name
        for word in [
            "concert",
            "music",
            "cultural"
        ]
    ):

        return "Cultural Event"

    return "Public Event"


# ============================================================
# ESTIMATE EVENT INTENSITY
# ============================================================

def estimate_event_intensity(
    event_name
):

    name = event_name.lower()

    # --------------------------------------------------------
    # Level 3 = major city-scale event
    # --------------------------------------------------------

    major_keywords = [

        "ganesha",
        "ganesh",
        "dasara",
        "karaga",
        "utsava",
        "utsav",
        "deepavali",
        "diwali",
        "flower show"

    ]

    if any(
        word in name
        for word in major_keywords
    ):

        return 3

    # --------------------------------------------------------
    # Level 2 = medium/large gathering
    # --------------------------------------------------------

    medium_keywords = [

        "mela",
        "festival",
        "fair",
        "exhibition",
        "expo",
        "concert"

    ]

    if any(
        word in name
        for word in medium_keywords
    ):

        return 2

    # --------------------------------------------------------
    # Level 1 = normal public event
    # --------------------------------------------------------

    return 1


# ============================================================
# CHECK WHETHER EVENT IS VALID
# ============================================================

def is_valid_event_name(
    event_name
):

    if not event_name:

        return False

    name = (
        event_name
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # Website navigation / non-event content
    # --------------------------------------------------------

    invalid_names = [

        "related links",
        "related link",
        "links",
        "bengaluru",
        "bangalore",
        "events",
        "event",
        "events & festivals",
        "upcoming events",
        "upcoming events & festivals",
        "featured events",
        "featured events & festivals",
        "read more",
        "learn more",
        "contact us",
        "home",
        "about us",
        "destinations",
        "related destinations"

    ]

    if name in invalid_names:

        return False

    # --------------------------------------------------------
    # Very short headings are usually not events
    # --------------------------------------------------------

    if len(name) < 6:

        return False

    # --------------------------------------------------------
    # Navigation words
    # --------------------------------------------------------

    if name.startswith(
        "related "
    ):

        return False

    if name.startswith(
        "read "
    ):

        return False

    if name.startswith(
        "view "
    ):

        return False

    return True


# ============================================================
# EXTRACT EVENTS
# ============================================================

def extract_events(
    html
):

    print(
        "\nExtracting events..."
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    events = []

    seen = set()

    containers = soup.find_all(
        [
            "article",
            "div",
            "li"
        ]
    )

    for container in containers:

        text = " ".join(
            container.stripped_strings
        )

        if not text:

            continue

        # ----------------------------------------------------
        # Only Bengaluru-related containers
        # ----------------------------------------------------

        if (
            "bengaluru"
            not in text.lower()
            and
            "bangalore"
            not in text.lower()
        ):

            continue

        # ----------------------------------------------------
        # Detect date
        # ----------------------------------------------------

        date_pattern = re.search(

            r"\d{1,2}\s*"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
            r"Sep|Sept|Oct|Nov|Dec)"
            r"(?:\s*[-–—]\s*"
            r"\d{1,2}\s*"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|"
            r"Sep|Sept|Oct|Nov|Dec))?",

            text,

            re.IGNORECASE

        )

        if not date_pattern:

            continue

        date_text = (
            date_pattern.group(0)
        )

        start_date, end_date = (
            parse_event_dates(
                date_text
            )
        )

        if start_date is None:

            continue

        # ----------------------------------------------------
        # Find heading
        # ----------------------------------------------------

        heading = container.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6"
            ]
        )

        if heading:

            event_name = (
                heading.get_text(
                    " ",
                    strip=True
                )
            )

        else:

            event_name = ""

        # ----------------------------------------------------
        # Validate event name
        # ----------------------------------------------------

        if not is_valid_event_name(
            event_name
        ):

            continue

        # ----------------------------------------------------
        # Create duplicate key
        # ----------------------------------------------------

        key = (

            event_name
            .strip()
            .lower(),

            start_date.date()

        )

        if key in seen:

            continue

        seen.add(key)

        # ----------------------------------------------------
        # Event classification
        # ----------------------------------------------------

        event_type = (
            determine_event_type(
                event_name
            )
        )

        event_intensity = (
            estimate_event_intensity(
                event_name
            )
        )

        # ----------------------------------------------------
        # Event ID
        # ----------------------------------------------------

        event_id = (
            "KT_"
            + str(
                len(events) + 1
            ).zfill(5)
        )

        # ----------------------------------------------------
        # Store event
        # ----------------------------------------------------

        events.append({

            "event_id":
                event_id,

            "event_name":
                event_name.strip(),

            "event_type":
                event_type,

            "description":
                text[:500],

            "start_datetime":
                start_date,

            "end_datetime":
                end_date,

            # Coordinates will be assigned
            # by the event-to-grid mapping
            # module.
            "latitude":
                None,

            "longitude":
                None,

            "location":
                CITY_NAME,

            "city":
                CITY_NAME,

            "expected_attendance":
                None,

            "event_intensity":
                event_intensity,

            "source":
                "Karnataka Tourism",

            "last_updated":
                datetime.now()

        })

    return events


# ============================================================
# CLEAN EVENTS
# ============================================================

def clean_events(
    events
):

    if not events:

        return pd.DataFrame(
            columns=EVENT_COLUMNS
        )

    df = pd.DataFrame(
        events
    )

    # --------------------------------------------------------
    # Convert dates
    # --------------------------------------------------------

    df["start_datetime"] = (
        pd.to_datetime(
            df["start_datetime"],
            errors="coerce"
        )
    )

    df["end_datetime"] = (
        pd.to_datetime(
            df["end_datetime"],
            errors="coerce"
        )
    )

    # --------------------------------------------------------
    # Remove invalid dates
    # --------------------------------------------------------

    df = df[
        df["start_datetime"].notna()
    ].copy()

    # --------------------------------------------------------
    # Future window
    # --------------------------------------------------------

    today = pd.Timestamp(
        datetime.now().date()
    )

    forecast_end = (
        today
        + pd.Timedelta(
            days=FORECAST_DAYS
        )
    )

    df = df[
        (
            df["end_datetime"]
            >= today
        )
        &
        (
            df["start_datetime"]
            <= forecast_end
        )
    ].copy()

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "event_name",
            "start_datetime"
        ],
        keep="first"
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        "start_datetime"
    )

    # --------------------------------------------------------
    # Reset IDs after filtering
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )

    for index in df.index:

        df.loc[
            index,
            "event_id"
        ] = (
            "KT_"
            + str(index + 1).zfill(5)
        )

    return df[
        EVENT_COLUMNS
    ]


# ============================================================
# SAVE DATASET
# ============================================================

def save_events(
    df
):

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "\nEvent dataset saved:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "BENGALURU KARNATAKA TOURISM "
        "EVENT INGESTION ENGINE"
    )

    print("=" * 60)

    print(
        "\nSource:"
    )

    print(
        SOURCE_URL
    )

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    html = download_page()

    if html is None:

        print(
            "\nEvent ingestion stopped."
        )

        return

    # --------------------------------------------------------
    # Extract
    # --------------------------------------------------------

    events = extract_events(
        html
    )

    print(
        "\nRaw Bengaluru events found: "
        f"{len(events)}"
    )

    # --------------------------------------------------------
    # Clean
    # --------------------------------------------------------

    df = clean_events(
        events
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_events(
        df
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT INGESTION SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        f"\nValid upcoming events: "
        f"{len(df)}"
    )

    if not df.empty:

        print(
            "\nEvents:"
        )

        print(
            df[
                [
                    "event_id",
                    "event_name",
                    "event_type",
                    "start_datetime",
                    "end_datetime",
                    "location",
                    "event_intensity",
                    "source"
                ]
            ].to_string(
                index=False
            )
        )

        print(
            "\nEvent type distribution:"
        )

        print(
            df[
                "event_type"
            ].value_counts()
        )

        print(
            "\nEvent intensity distribution:"
        )

        print(
            df[
                "event_intensity"
            ].value_counts()
            .sort_index()
        )

    else:

        print(
            "\nNo upcoming Bengaluru events "
            "were extracted."
        )

        print(
            "\nPossible reasons:"
        )

        print(
            "1. Website structure changed."
        )

        print(
            "2. Events are loaded dynamically."
        )

        print(
            "3. No events fall within "
            f"the next {FORECAST_DAYS} days."
        )

    print(
        "\n" + "=" * 60
    )

    print(
        "EVENT INGESTION COMPLETED"
    )

    print(
        "=" * 60
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()