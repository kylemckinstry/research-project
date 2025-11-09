"""Time window planning for different roles and day types."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Tuple

import pandas as pd


def get_time_window_for_role(
    role: str,
    shift_date: date,
    cfg,
    slot_index: int = 0,
) -> Tuple[str, str]:
    """
    Get the appropriate time window (start_hm, end_hm) for a role on a specific date.
    
    Args:
        role: Employee role (MANAGER, BARISTA, WAITER, SANDWICH)
        shift_date: Date of the shift
        cfg: SchedulerConfig with role_time_windows
        slot_index: For roles with multiple slots per day (e.g., weekend staggered)
    
    Returns:
        (start_hm, end_hm) tuple like ("07:00", "15:00")
    """
    day_name = pd.Timestamp(shift_date).day_name()
    is_weekend = day_name in ["Saturday", "Sunday"]
    
    # Get role time windows from config
    role_windows = getattr(cfg, 'role_time_windows', {}).get(role, {})
    
    if not role_windows:
        # No specific windows, use default
        return cfg.default_shift.start, cfg.default_shift.end
    
    # Determine which window to use based on day type
    if is_weekend:
        # Check for weekend staggered shifts
        if 'weekend_staggered' in role_windows:
            staggered_windows = role_windows['weekend_staggered']
            if isinstance(staggered_windows, list) and slot_index < len(staggered_windows):
                window = staggered_windows[slot_index]
                return window['start'], window['end']
        
        # Check for regular weekend window
        if 'weekend' in role_windows:
            weekend_windows = role_windows['weekend']
            if isinstance(weekend_windows, list) and slot_index < len(weekend_windows):
                window = weekend_windows[slot_index]
                return window['start'], window['end']
            elif isinstance(weekend_windows, dict):
                return weekend_windows['start'], weekend_windows['end']
    
    # Weekday window
    if 'weekday' in role_windows:
        weekday_window = role_windows['weekday']
        if isinstance(weekday_window, list) and slot_index < len(weekday_window):
            window = weekday_window[slot_index]
            return window['start'], window['end']
        elif isinstance(weekday_window, dict):
            return weekday_window['start'], weekday_window['end']
    
    # Fallback to default
    return cfg.default_shift.start, cfg.default_shift.end


def parse_time_string(time_str: str) -> time:
    """Parse time string like '07:00' into time object."""
    hour, minute = map(int, time_str.split(':'))
    return time(hour, minute)


def calculate_shift_hours(start_hm: str, end_hm: str) -> float:
    """Calculate shift duration in hours from time strings."""
    start = parse_time_string(start_hm)
    end = parse_time_string(end_hm)
    
    # Simple calculation (assumes same day)
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    
    duration_minutes = end_minutes - start_minutes
    return duration_minutes / 60.0


def create_datetime_from_date_and_time(
    shift_date,
    time_hm: str,
    timezone: str = "Australia/Sydney",
) -> datetime:
    """
    Create timezone-aware datetime from date and time string.
    
    Args:
        shift_date: Date of the shift (date object or string in YYYY-MM-DD format)
        time_hm: Time string like "07:00"
        timezone: Timezone name
    
    Returns:
        Timezone-aware datetime
    """
    # Handle both date objects and string dates
    if isinstance(shift_date, str):
        shift_date = datetime.strptime(shift_date, "%Y-%m-%d").date()
    
    time_obj = parse_time_string(time_hm)
    naive_dt = datetime.combine(shift_date, time_obj)
    aware_dt = pd.Timestamp(naive_dt).tz_localize(timezone).to_pydatetime()
    return aware_dt

