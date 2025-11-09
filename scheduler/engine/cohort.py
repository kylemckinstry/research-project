"""Cohort scheduler - handles BARISTA and WAITER roles with shared FOH logic."""

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


class CohortScheduler(BaseScheduler):
    """
    Scheduler for front-of-house (FOH) cohort roles: BARISTA and WAITER.
    
    Both roles share similar logic:
    - Single full shift on weekdays (07:00-15:00)
    - Two staggered shifts on weekends (07:00-12:00, 11:00-15:00)
    - Part-time hours (16-40h target)
    """
    
    def __init__(self, role: str):
        """
        Initialize cohort scheduler for a specific role.
        
        Args:
            role: Either "BARISTA" or "WAITER"
        """
        if role.upper() not in ["BARISTA", "WAITER"]:
            raise ValueError(f"CohortScheduler only handles BARISTA and WAITER, not {role}")
        
        self.role = role.upper()
    
    def make_schedule(
        self,
        client: firestore.Client,
        week_id: str,
        cfg,
    ) -> List[Assignment]:
        """
        Generate assignments for this cohort role.
        
        Strategy:
        - 1 person on weekdays (single 8h shift)
        - 1-2 people on weekends (staggered shifts or concurrent based on requirements)
        - Balance hours across cohort (target 16-40h)
        """
        # Get employees for this role
        employees_list = EmployeeRepository.get_by_role(client, self.role)
        if not employees_list:
            raise RuntimeError(f"No {self.role} staff available for scheduling")
        
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
            needed = requirements.get(self.role, 1)
            
            # Build cohort hours for fairness
            cohort_hours = {emp.employee_id: weekly_hours[emp.employee_id] for emp in employees_list}
            
            # Assign staff for this day
            for slot_idx in range(needed):
                # Get time window (may be staggered on weekends)
                start_hm, end_hm = get_time_window_for_role(self.role, shift_date, cfg, slot_idx)
                shift_hours = (pd.Timestamp(f"{shift_date} {end_hm}") - pd.Timestamp(f"{shift_date} {start_hm}")).total_seconds() / 3600
                
                # Build candidate pool
                candidates = []
                for emp in employees_list:
                    if can_assign_employee(
                        emp,
                        self.role,
                        shift_date,
                        shift_hours,
                        assigned_today[shift_date],
                        weekly_hours,
                        hours_policy,
                        getattr(cfg, 'global_hard_cap', 50.0),
                    ):
                        candidates.append(emp)
                
                if not candidates:
                    # Try weekend fallback if configured
                    if is_weekend and hasattr(cfg, 'weekend_fallback'):
                        fallback = cfg.weekend_fallback.get(self.role, {})
                        if fallback.get('enabled', False):
                            min_required = fallback.get('min_required', 1)
                            if slot_idx >= min_required:
                                # Can skip this slot
                                continue
                    
                    raise RuntimeError(
                        f"Cannot assign {self.role} for {shift_date}: insufficient eligible staff"
                    )
                
                # Score candidates
                scored = []
                for emp in candidates:
                    score = calculate_employee_score(
                        emp,
                        self.role,
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
                
                shift_type = "weekday" if not is_weekend else f"weekend_slot{slot_idx+1}"
                
                assign = Assignment(
                    shift_id=shift.shift_id,
                    emp_id=best_emp.employee_id,
                    start_time=start_dt,
                    end_time=end_dt,
                    role=self.role,
                    shift_type=shift_type,
                    day_type="weekday" if not is_weekend else "weekend",
                )
                
                assignments.append(assign)
                
                # Update tracking
                weekly_hours[best_emp.employee_id] += shift_hours
                assigned_today[shift_date].add(best_emp.employee_id)
        
        print(f"[INFO] {self.role}Scheduler: Generated {len(assignments)} assignments")
        return assignments

