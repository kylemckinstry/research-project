"""CSV export utilities to export data from Firestore."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
from google.cloud import firestore

from scheduler.domain.models import Assignment, Employee
from scheduler.domain.repositories import AssignmentRepository, EmployeeRepository


def export_assignments_csv(client: firestore.Client, csv_path: str | Path, week_id: str | None = None) -> int:
    """
    Export assignments from Firestore to CSV.
    
    Args:
        client: Firestore client
        csv_path: Path to output CSV
        week_id: Optional week_id to filter
    
    Returns:
        Number of assignments exported
    """
    # Get assignments
    if week_id:
        assignments = AssignmentRepository.get_by_week(client, week_id)
    else:
        assignments = AssignmentRepository.get_all(client)
    
    # Convert to DataFrame
    records = []
    for assign in assignments:
        records.append({
            'shift_id': assign.shift_id,
            'emp_id': assign.emp_id,
            'start_time': assign.start_time.isoformat(),
            'end_time': assign.end_time.isoformat(),
        })
    
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    
    print(f"[INFO] Exported {len(records)} assignments to {csv_path}")
    return len(records)


def export_employees_csv(client: firestore.Client, csv_path: str | Path) -> int:
    """
    Export employees from Firestore to CSV.
    
    Args:
        client: Firestore client
        csv_path: Path to output CSV
    
    Returns:
        Number of employees exported
    """
    # Get all employees
    employees = EmployeeRepository.get_all(client)
    
    # Convert to DataFrame
    records = []
    for emp in employees:
        records.append({
            'employee_id': emp.employee_id,
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'primary_role': emp.primary_role,
            'skill_coffee': emp.skill_coffee,
            'skill_sandwich': emp.skill_sandwich,
            'customer_service_rating': emp.customer_service_rating,
            'skill_speed': emp.skill_speed,
        })
    
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    
    print(f"[INFO] Exported {len(records)} employees to {csv_path}")
    return len(records)

