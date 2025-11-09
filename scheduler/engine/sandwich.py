"""Sandwich scheduler - handles SANDWICH role assignments with early morning prep."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Set

import pandas as pd
from google.cloud import firestore

from scheduler.domain.models import Assignment, Employee, Shift
from scheduler.domain.repositories import EmployeeRepository, ShiftRepository
from scheduler.services.constraints import can_assign_employee
from scheduler.services.scoring import calculate_employee_score
from scheduler.services.timeplan import create_datetime_from_date_and_time, get_time_window_for_role

from .base import BaseScheduler


class SandwichScheduler(BaseScheduler):
    """
    Scheduler for SANDWICH role.
    
    Sandwich prep staff work early morning shifts (05:00-12:00 typically)
    to prepare sandwiches before café opens. Weekend shifts may extend to 13:30
    on busy days.
    """
    
    role = "SANDWICH"
    
    def make_schedule(
        self,
        client: firestore.Client,
        week_id: str,
        cfg,
    ) -> List[Assignment]:
        """
        Generate sandwich prep assignments for the week.
        
        Strategy:
        - Early morning shifts (05:00-12:00 weekdays, 05:00-13:30 weekends)
        - 1 sandwich person per day (configurable)
        - Balance hours across sandwich staff (target 16-32h)
        """
        # Get sandwich staff
        sandwich_staff = EmployeeRepository.get_by_role(client, "SANDWICH")
        if not sandwich_staff:
            raise RuntimeError(f"No sandwich staff available for scheduling")
        
        # Get shifts for this week
        shifts = ShiftRepository.get_by_week(client, week_id)
        if not shifts:
            raise RuntimeError(f"No shifts found for week {week_id}")
        
        # Track weekly hours and daily assignments
        weekly_hours: Dict[int, float] = defaultdict(float)
        assigned_today: Dict[date, Set[int]] = defaultdict(set)
        assignments: List[Assignment] = []
        
        # Get configuration
        hours_policy = getattr(cfg, 'hours_policy', {})
        hours_penalties = getattr(cfg, 'hours_penalties', {})
        weights = cfg.weights.__dict__ if hasattr(cfg.weights, '__dict__') else {}
        timezone = cfg.timezone
        
        # Build requirements per day
        from scheduler.services.requirements import build_requirements_for_day
        
        for shift in sorted(shifts, key=lambda s: s.date):
            shift_date = shift.date
            day_name = pd.Timestamp(shift_date).day_name()
            is_weekend = day_name in ["Saturday", "Sunday"]
            
            # Get requirements for this day
            date_str = pd.Timestamp(shift_date).strftime("%Y-%m-%d")
            requirements = build_requirements_for_day(date_str, cfg)
            needed = requirements.get("SANDWICH", 1)
            
            # Build cohort hours for fairness
            cohort_hours = {emp.employee_id: weekly_hours[emp.employee_id] for emp in sandwich_staff}
            
            # Assign sandwich staff for this day
            for slot_idx in range(needed):
                # Get time window (may vary for weekends or multiple slots)
                start_hm, end_hm = get_time_window_for_role("SANDWICH", shift_date, cfg, slot_idx)
                shift_hours = (pd.Timestamp(f"{shift_date} {end_hm}") - pd.Timestamp(f"{shift_date} {start_hm}")).total_seconds() / 3600
                
                # Build candidate pool
                candidates = []
                for emp in sandwich_staff:
                    if can_assign_employee(
                        emp,
                        "SANDWICH",
                        shift_date,
                        shift_hours,
                        assigned_today[shift_date],
                        weekly_hours,
                        hours_policy,
                        getattr(cfg, 'global_hard_cap', 50.0),
                    ):
                        candidates.append(emp)
                
                if not candidates:
                    raise RuntimeError(
                        f"Cannot assign SANDWICH for {shift_date}: insufficient eligible staff"
                    )
                
                # Score candidates
                scored = []
                for emp in candidates:
                    score = calculate_employee_score(
                        emp,
                        "SANDWICH",
                        weekly_hours[emp.employee_id],
                        cohort_hours,
                        weights,
                        hours_policy,
                        hours_penalties,
                    )
                    scored.append((score, emp))
                
                # Select best candidate
                scored.sort(key=lambda x: x[0], reverse=True)
                best_emp = scored[0][1]
                
                # Create assignment
                start_dt = create_datetime_from_date_and_time(shift_date, start_hm, timezone)
                end_dt = create_datetime_from_date_and_time(shift_date, end_hm, timezone)
                
                assign = Assignment(
                    shift_id=shift.shift_id,
                    emp_id=best_emp.employee_id,
                    start_time=start_dt,
                    end_time=end_dt,
                    role="SANDWICH",
                    shift_type="early_prep" if not is_weekend else "weekend_prep",
                    day_type="weekday" if not is_weekend else "weekend",
                )
                
                assignments.append(assign)
                
                # Update tracking
                weekly_hours[best_emp.employee_id] += shift_hours
                assigned_today[shift_date].add(best_emp.employee_id)
        
        print(f"[INFO] SandwichScheduler: Generated {len(assignments)} assignments")
        return assignments

