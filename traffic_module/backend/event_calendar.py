"""
Event Calendar for Bengaluru Traffic Prediction
Handles major events and holidays that affect traffic
"""

from datetime import datetime, date, time
from typing import List, Dict, Optional

# Major Bengaluru events with traffic impact
BENGALURU_EVENTS = [
    {
        "name": "IPL Match",
        "location": "Chinnaswamy Stadium",
        "ward": 74,
        "affected_wards": [74, 75, 76, 80, 81],
        "impact_multiplier": 2.1,
        "type": "sports",
        "seasonal": True,  # During IPL season
    },
    {
        "name": "Dasara",
        "type": "festival",
        "citywide": True,
        "impact_multiplier": 1.6,
        "date": None,  # Dynamic based on Hindu calendar
    },
    {
        "name": "Ugadi",
        "type": "festival",
        "citywide": True,
        "impact_multiplier": 1.4,
        "date": None,  # Dynamic based on Hindu calendar
    },
    {
        "name": "Marathon",
        "location": "MG Road",
        "ward": 76,
        "affected_wards": [74, 75, 76, 77],
        "impact_multiplier": 1.9,
        "type": "sports",
        "seasonal": True,  # Usually in specific months
    },
    {
        "name": "Tech Summit",
        "location": "Whitefield",
        "ward": 84,
        "affected_wards": [84, 85, 175],
        "impact_multiplier": 1.5,
        "type": "conference",
        "seasonal": True,
    },
    {
        "name": "Music Concert",
        "location": "Palace Grounds",
        "ward": 74,
        "affected_wards": [74, 75, 76],
        "impact_multiplier": 1.7,
        "type": "entertainment",
    },
]

# Karnataka public holidays (major ones affecting traffic)
KARNATAKA_HOLIDAYS = [
    # Fixed dates
    {"name": "New Year", "date": "2025-01-01", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Republic Day", "date": "2025-01-26", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Independence Day", "date": "2025-08-15", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Gandhi Jayanti", "date": "2025-10-02", "citywide": True, "impact_multiplier": 0.4},
    
    # Religious festivals (approximate dates for 2025)
    {"name": "Ugadi", "date": "2025-03-30", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Ramadan", "date": "2025-03-01", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Eid", "date": "2025-03-31", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Dasara", "date": "2025-10-03", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Diwali", "date": "2025-10-21", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Christmas", "date": "2025-12-25", "citywide": True, "impact_multiplier": 0.4},
    
    # State-specific holidays
    {"name": "Karnataka Rajyotsava", "date": "2025-11-01", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Mahaveer Jayanti", "date": "2025-04-13", "citywide": True, "impact_multiplier": 0.4},
    {"name": "Buddha Purnima", "date": "2025-05-12", "citywide": True, "impact_multiplier": 0.4},
]

def get_event_multiplier(ward_id: int, target_date: date) -> float:
    """
    Get event multiplier for a specific ward and date
    Returns multiplier if event is active on that date
    """
    multiplier = 1.0
    
    # Check citywide events first
    for event in BENGALURU_EVENTS:
        if event.get("citywide", False):
            # For citywide events, check if it's the right date
            if event.get("date"):
                event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                if event_date == target_date:
                    multiplier = max(multiplier, event["impact_multiplier"])
            elif event.get("seasonal", False):
                # For seasonal events, check if it's a weekend (simplified)
                if target_date.weekday() >= 5:  # Saturday or Sunday
                    multiplier = max(multiplier, event["impact_multiplier"])
    
    # Check location-specific events
    for event in BENGALURU_EVENTS:
        if not event.get("citywide", False) and ward_id in event.get("affected_wards", []):
            if event.get("date"):
                event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                if event_date == target_date:
                    multiplier = max(multiplier, event["impact_multiplier"])
            elif event.get("seasonal", False):
                # Check if it's a weekend for seasonal events
                if target_date.weekday() >= 5:
                    multiplier = max(multiplier, event["impact_multiplier"])
    
    return multiplier

def is_holiday(target_date: date) -> bool:
    """
    Check if a given date is a public holiday
    """
    for holiday in KARNATAKA_HOLIDAYS:
        holiday_date = datetime.strptime(holiday["date"], "%Y-%m-%d").date()
        if holiday_date == target_date:
            return True
    return False

def get_holiday_multiplier(target_date: date) -> float:
    """
    Get holiday multiplier for traffic prediction
    """
    for holiday in KARNATAKA_HOLIDAYS:
        holiday_date = datetime.strptime(holiday["date"], "%Y-%m-%d").date()
        if holiday_date == target_date:
            return holiday["impact_multiplier"]
    return 1.0

def get_active_events(target_date: date, ward_id: Optional[int] = None) -> List[Dict]:
    """
    Get all active events for a given date and optional ward
    """
    active_events = []
    
    for event in BENGALURU_EVENTS:
        event_active = False
        
        if event.get("citywide", False):
            if event.get("date"):
                event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                event_active = event_date == target_date
            elif event.get("seasonal", False):
                event_active = target_date.weekday() >= 5  # Weekend
        else:
            # Location-specific event
            if ward_id and ward_id in event.get("affected_wards", []):
                if event.get("date"):
                    event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                    event_active = event_date == target_date
                elif event.get("seasonal", False):
                    event_active = target_date.weekday() >= 5
        
        if event_active:
            active_events.append(event.copy())
    
    return active_events

def get_upcoming_events(days_ahead: int = 7) -> List[Dict]:
    """
    Get upcoming events in the next N days
    """
    today = date.today()
    upcoming_events = []
    
    for i in range(1, days_ahead + 1):
        target_date = today.replace(day=today.day + i)
        events = get_active_events(target_date)
        
        for event in events:
            event["date"] = target_date.strftime("%Y-%m-%d")
            upcoming_events.append(event)
    
    return upcoming_events

def get_event_alerts(ward_id: int, target_date: date) -> List[str]:
    """
    Get event alerts for a specific ward and date
    Returns list of alert messages
    """
    alerts = []
    active_events = get_active_events(target_date, ward_id)
    
    for event in active_events:
        if event.get("impact_multiplier", 1.0) >= 1.5:
            alerts.append(f"🚨 {event['name']} affecting Ward {ward_id} - Expect heavy traffic")
        elif event.get("impact_multiplier", 1.0) >= 1.2:
            alerts.append(f"⚠️ {event['name']} nearby - Moderate traffic expected")
    
    return alerts

def is_weekend(target_date: date) -> bool:
    """
    Check if a given date is a weekend
    """
    return target_date.weekday() >= 5  # Saturday = 5, Sunday = 6

def get_special_day_multiplier(target_date: date) -> float:
    """
    Get special day multiplier (weekend, holiday, etc.)
    """
    if is_holiday(target_date):
        return 0.4  # Public holiday
    elif is_weekend(target_date):
        return 0.7 if target_date.weekday() == 5 else 0.5  # Saturday vs Sunday
    else:
        return 1.0  # Regular weekday
