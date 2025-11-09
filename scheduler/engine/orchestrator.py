"""Orchestrator - coordinates all role-specific schedulers to build a complete week schedule."""

from __future__ import annotations

from typing import List

from google.cloud import firestore

from scheduler.domain.models import Assignment, Employee
from scheduler.domain.repositories import AssignmentRepository, EmployeeRepository, ShiftRepository
from scheduler.services.constraints import validate_assignment_constraints

from .base import BaseScheduler
from .cohort import CohortScheduler
from .manager import ManagerScheduler
from .sandwich import SandwichScheduler


class Orchestrator:
    """
    Orchestrator coordinates multiple role-specific schedulers.
    
    Each scheduler generates assignments for its role(s) independently,
    then the orchestrator merges and validates the complete schedule.
    """
    
    def __init__(self, scheduler_order: List[str] | None = None):
        """
        Initialize orchestrator with scheduler execution order.
        
        Args:
            scheduler_order: Order to execute schedulers (default: MANAGER, SANDWICH, BARISTA, WAITER)
        """
        self.scheduler_order = scheduler_order or ["MANAGER", "SANDWICH", "BARISTA", "WAITER"]
    
    def build_schedule(
        self,
        client: firestore.Client,
        week_id: str,
        cfg,
        existing_assignments: List[Assignment] | None = None,
    ) -> List[Assignment]:
        """
        Build complete schedule for a week using all role schedulers.
        
        Simple logic:
        1. Run all role schedulers to generate assignments
        2. Deduplicate: ensure each employee is assigned to each shift only once
        3. Return final assignments
        
        Args:
            client: Firestore client
            week_id: ISO week identifier
            cfg: SchedulerConfig
            existing_assignments: Ignored (for backwards compatibility)
        
        Returns:
            List of deduplicated assignments
        """
        print(f"[INFO] Orchestrator: Building schedule for {week_id}")
        print(f"[INFO] Scheduler order: {self.scheduler_order}")
        
        # Create and run schedulers
        schedulers: List[BaseScheduler] = []
        for role in self.scheduler_order:
            if role == "MANAGER":
                schedulers.append(ManagerScheduler())
            elif role == "SANDWICH":
                schedulers.append(SandwichScheduler())
            elif role in ["BARISTA", "WAITER"]:
                schedulers.append(CohortScheduler(role))
        
        all_auto_assignments: List[Assignment] = []
        for scheduler in schedulers:
            role_name = scheduler.get_role_name()
            print(f"\n[INFO] Running {role_name} scheduler...")
            try:
                assignments = scheduler.make_schedule(client, week_id, cfg)
                all_auto_assignments.extend(assignments)
                print(f"[OK] {role_name}: generated {len(assignments)} assignments")
            except RuntimeError as e:
                print(f"[ERROR] {role_name} failed: {e}")
                raise
        
        print(f"[INFO] Total assignments before deduplication: {len(all_auto_assignments)}")
        
        # DEBUG: Shows what assignments were created
        from collections import Counter
        assignment_counts = Counter((a.shift_id, a.emp_id) for a in all_auto_assignments)
        duplicates_found = {k: v for k, v in assignment_counts.items() if v > 1}
        if duplicates_found:
            print(f"[WARN] Found {len(duplicates_found)} (shift, employee) pairs with duplicates BEFORE deduplication:")
            for (shift_id, emp_id), count in list(duplicates_found.items())[:5]:  # Show first 5
                print(f"[WARN]   Shift {shift_id}, Employee {emp_id}: {count} times")
        
        # Deduplicate: Keep only first assignment for each (shift_id, employee_id) pair
        seen: set[tuple[int, int]] = set()
        deduplicated: List[Assignment] = []
        skipped = 0
        
        for a in all_auto_assignments:
            key = (a.shift_id, a.emp_id)
            if key in seen:
                skipped += 1
                print(f"[DEBUG] Skipping duplicate: Employee {a.emp_id} (role={a.role}) already assigned to shift {a.shift_id}")
                continue
            
            seen.add(key)
            deduplicated.append(a)
        
        if skipped > 0:
            print(f"[INFO] Removed {skipped} duplicate assignments")
        
        # Validation
        print(f"\n[INFO] Validating complete schedule...")
        employees = EmployeeRepository.get_all(client)
        validate_assignment_constraints(deduplicated, employees, cfg)
        
        print(f"[OK] Generated {len(deduplicated)} unique assignments")
        return deduplicated


def build_week_schedule(
    client: firestore.Client,
    week_id: str,
    cfg,
    scheduler_order: List[str] | None = None,
    persist: bool = True,
) -> List[Assignment]:
    """
    Convenience function to build a week schedule using the orchestrator.
    
    Args:
        client: Firestore client
        week_id: ISO week identifier
        cfg: SchedulerConfig
        scheduler_order: Optional custom scheduler execution order
        persist: If True, save assignments to database
    
    Returns:
        List of assignments
    """
    orchestrator = Orchestrator(scheduler_order)
    assignments = orchestrator.build_schedule(client, week_id, cfg)
    
    if persist:
        # Delete existing assignments for this week
        deleted = AssignmentRepository.delete_by_week(client, week_id)
        if deleted > 0:
            print(f"[INFO] Deleted {deleted} existing assignments for {week_id}")
        
        # Persist new assignments
        AssignmentRepository.bulk_create(client, assignments, week_id)
        print(f"[INFO] Persisted {len(assignments)} assignments to database")
    
    return assignments
