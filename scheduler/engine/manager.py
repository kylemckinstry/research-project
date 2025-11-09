"""Manager scheduler - handles MANAGER role assignments."""

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


class ManagerScheduler(BaseScheduler):
    """
    Scheduler for MANAGER role.
    
    Managers work full-time (38-40h target) and provide managerial coverage
    every day, with 2 managers on weekends for supervision.
    """
    
    role = "MANAGER"
    
    def make_schedule(
        self,
        client: firestore.Client,
        week_id: str,
        cfg,
    ) -> List[Assignment]:
        """
        Generate manager assignments for the week.
        
        Strategy:
        - Weekend-aware: Schedule busy days (Sat/Sun) first
        - Alternate managers on weekdays to reserve hours for weekend
        - 1 manager per weekday, 2 managers per weekend
        - Balance hours across managers (target 32-40h)
        - Use default shift times (07:00-15:00)
        """
        # Get managers
        managers = EmployeeRepository.get_by_role(client, "MANAGER")
        if not managers:
            raise RuntimeError(f"No managers available for scheduling")
        
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
        
        # Sort shifts: busy days (weekends) first to ensure managers reserve hours
        def sort_key(shift):
            day_name = pd.Timestamp(shift.date).day_name()
            is_weekend = day_name in ["Saturday", "Sunday"]
            # Weekend first (0), then weekdays (1)
            return (0 if is_weekend else 1, shift.date)
        
        sorted_shifts = sorted(shifts, key=sort_key)
        
        # Build requirements per day
        from scheduler.services.requirements import build_requirements_for_day
        
        for shift in sorted_shifts:
            shift_date = shift.date
            day_name = pd.Timestamp(shift_date).day_name()
            is_weekend = day_name in ["Saturday", "Sunday"]
            
            # Get requirements for this day
            date_str = pd.Timestamp(shift_date).strftime("%Y-%m-%d")
            requirements = build_requirements_for_day(date_str, cfg)
            needed = requirements.get("MANAGER", 2 if is_weekend else 1)
            
            # Get time window
            start_hm, end_hm = get_time_window_for_role("MANAGER", shift_date, cfg)
            shift_hours = (pd.Timestamp(f"{shift_date} {end_hm}") - pd.Timestamp(f"{shift_date} {start_hm}")).total_seconds() / 3600
            
            # Build cohort hours for fairness
            cohort_hours = {emp.employee_id: weekly_hours[emp.employee_id] for emp in managers}
            
            # Assign managers for this day
            for slot_idx in range(needed):
                # Build candidate pool
                candidates = []
                for mgr in managers:
                    if can_assign_employee(
                        mgr,
                        "MANAGER",
                        shift_date,
                        shift_hours,
                        assigned_today[shift_date],
                        weekly_hours,
                        hours_policy,
                        getattr(cfg, 'global_hard_cap', 50.0),
                    ):
                        candidates.append(mgr)
                
                if not candidates:
                    raise RuntimeError(
                        f"Cannot assign manager for {shift_date}: insufficient eligible staff"
                    )
                
                # Score candidates
                scored = []
                for mgr in candidates:
                    score = calculate_employee_score(
                        mgr,
                        "MANAGER",
                        weekly_hours[mgr.employee_id],
                        cohort_hours,
                        weights,
                        hours_policy,
                        hours_penalties,
                    )
                    scored.append((score, mgr))
                
                # Select best candidate
                scored.sort(key=lambda x: x[0], reverse=True)
                best_mgr = scored[0][1]
                
                # Create assignment
                start_dt = create_datetime_from_date_and_time(shift_date, start_hm, timezone)
                end_dt = create_datetime_from_date_and_time(shift_date, end_hm, timezone)
                
                assign = Assignment(
                    shift_id=shift.shift_id,
                    emp_id=best_mgr.employee_id,
                    start_time=start_dt,
                    end_time=end_dt,
                    role="MANAGER",
                    shift_type="weekday" if not is_weekend else "weekend",
                    day_type="weekday" if not is_weekend else "weekend",
                )
                
                assignments.append(assign)
                
                # Update tracking
                weekly_hours[best_mgr.employee_id] += shift_hours
                assigned_today[shift_date].add(best_mgr.employee_id)
        
        print(f"[INFO] ManagerScheduler: Generated {len(assignments)} assignments")
        return assignments

