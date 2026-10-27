"""
IT Park Shift Logic for Bengaluru Traffic Prediction
Handles shift change multipliers for major IT parks
"""

from datetime import datetime, time, timedelta

# IT park shift schedules
IT_PARK_SHIFTS = {
    "Manyata Tech Park": {
        "morning_start": time(8, 0),
        "morning_end": time(9, 0),
        "evening_start": time(17, 0),
        "evening_end": time(19, 0),
        "ward": 7
    },
    "Electronic City": {
        "morning_start": time(8, 0),
        "morning_end": time(9, 0),
        "evening_start": time(18, 0),
        "evening_end": time(20, 0),
        "ward": 195
    },
    "Whitefield": {
        "morning_start": time(9, 0),
        "morning_end": time(10, 0),
        "evening_start": time(18, 0),
        "evening_end": time(20, 0),
        "ward": 84
    }
}

def get_it_shift_multiplier(hour, location):
    """
    Get IT shift multiplier based on time and location
    Returns multiplier for traffic congestion
    """
    current_time = time(hour, 0)
    
    # Check if location is near an IT park
    it_park = None
    for park_name, park_info in IT_PARK_SHIFTS.items():
        if location.lower() in park_name.lower() or park_name.lower() in location.lower():
            it_park = park_name
            break
    
    if not it_park:
        return 1.0  # No IT park nearby
    
    shift_info = IT_PARK_SHIFTS[it_park]
    
    # Check if it's shift change time
    if (shift_info["morning_start"] <= current_time <= shift_info["morning_end"]) or \
       (shift_info["evening_start"] <= current_time <= shift_info["evening_end"]):
        return 1.8  # Shift change multiplier
    
    # Check if it's 30 minutes before shift change
    today = datetime.now().date()
    morning_before_dt = datetime.combine(today, shift_info["morning_start"]) - timedelta(hours=1)
    evening_before_dt = datetime.combine(today, shift_info["evening_start"]) - timedelta(hours=1)
    morning_before = morning_before_dt.time()
    evening_before = evening_before_dt.time()
    
    if (morning_before <= current_time < shift_info["morning_start"]) or \
       (evening_before <= current_time < shift_info["evening_start"]):
        return 1.4  # Pre-shift multiplier
    
    return 1.0  # Normal multiplier

def get_next_shift_change():
    """
    Get the next shift change time and countdown
    Returns (park_name, time_until_minutes, is_approaching)
    """
    now = datetime.now()
    current_time = now.time()
    
    next_change = None
    next_park = None
    min_diff = float('inf')
    
    for park_name, shift_info in IT_PARK_SHIFTS.items():
        # Check morning shift
        morning_start = now.replace(hour=shift_info["morning_start"].hour, 
                                   minute=shift_info["morning_start"].minute,
                                   second=0, microsecond=0)
        if morning_start < now:
            morning_start = morning_start + timedelta(days=1)
        
        morning_diff = (morning_start - now).total_seconds() / 60
        if morning_diff < min_diff:
            min_diff = morning_diff
            next_change = morning_start
            next_park = f"{park_name} (Morning)"
        
        # Check evening shift
        evening_start = now.replace(hour=shift_info["evening_start"].hour,
                                   minute=shift_info["evening_start"].minute,
                                   second=0, microsecond=0)
        if evening_start < now:
            evening_start = evening_start + timedelta(days=1)
        
        evening_diff = (evening_start - now).total_seconds() / 60
        if evening_diff < min_diff:
            min_diff = evening_diff
            next_change = evening_start
            next_park = f"{park_name} (Evening)"
    
    if next_change:
        is_approaching = min_diff <= 30  # Within 30 minutes
        return next_park, int(min_diff), is_approaching
    
    return None, None, False

def get_all_shift_timers():
    """
    Get countdown timers for all IT parks
    Returns list of (park_name, time_until_minutes, status)
    """
    now = datetime.now()
    timers = []
    
    for park_name, shift_info in IT_PARK_SHIFTS.items():
        # Morning shift
        morning_start = now.replace(hour=shift_info["morning_start"].hour,
                                   minute=shift_info["morning_start"].minute,
                                   second=0, microsecond=0)
        if morning_start < now:
            morning_start = morning_start + timedelta(days=1)
        
        morning_diff = (morning_start - now).total_seconds() / 60
        if morning_diff <= 120:  # Within 2 hours
            status = "APPROACHING" if morning_diff <= 30 else "UPCOMING"
            timers.append((f"{park_name} Morning", int(morning_diff), status))
        
        # Evening shift
        evening_start = now.replace(hour=shift_info["evening_start"].hour,
                                   minute=shift_info["evening_start"].minute,
                                   second=0, microsecond=0)
        if evening_start < now:
            evening_start = evening_start + timedelta(days=1)
        
        evening_diff = (evening_start - now).total_seconds() / 60
        if evening_diff <= 120:  # Within 2 hours
            status = "APPROACHING" if evening_diff <= 30 else "UPCOMING"
            timers.append((f"{park_name} Evening", int(evening_diff), status))
    
    return sorted(timers, key=lambda x: x[1])

def is_shift_change_active(location, current_time):
    """
    Check if shift change is currently active for a location
    """
    hour = current_time.hour
    return get_it_shift_multiplier(hour, location) > 1.0
