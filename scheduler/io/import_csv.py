"""CSV import utilities to load data into Firestore."""

from __future__ import annotations

from pathlib import Path
import random

import pandas as pd
from google.cloud import firestore

from scheduler.domain.models import Employee, Feedback, Shift
from scheduler.domain.repositories import EmployeeRepository, ShiftRepository, FeedbackRepository


def generate_role_based_skills(role: str, csv_values: dict) -> dict:
    """
    Generate realistic skill values based on role.
    Uses CSV values if provided, otherwise generates role-appropriate defaults.
    
    Args:
        role: Employee role (MANAGER, BARISTA, WAITER, SANDWICH)
        csv_values: Dict with skill_coffee, skill_sandwich, customer_service_rating, skill_speed from CSV
    
    Returns:
        Dict with all four skills populated
    """
    role = role.upper()
    
    # Define role-based skill ranges (min, max)
    role_profiles = {
        "MANAGER": {
            "skill_coffee": (70, 85),      # Managers know coffee well but not specialists
            "skill_sandwich": (65, 80),    # Good sandwich knowledge
            "customer_service_rating": (85, 95),  # Excellent customer service
            "skill_speed": (70, 85),       # Good efficiency
        },
        "BARISTA": {
            "skill_coffee": (80, 95),      # Expert coffee makers
            "skill_sandwich": (40, 60),    # Basic sandwich knowledge
            "customer_service_rating": (70, 90),  # Good with customers
            "skill_speed": (75, 90),       # Fast workers
        },
        "SANDWICH": {
            "skill_coffee": (40, 60),      # Basic coffee knowledge
            "skill_sandwich": (80, 95),    # Expert sandwich makers
            "customer_service_rating": (65, 85),  # Decent customer service
            "skill_speed": (70, 85),       # Efficient
        },
        "WAITER": {
            "skill_coffee": (50, 70),      # Some coffee knowledge
            "skill_sandwich": (50, 70),    # Some sandwich knowledge
            "customer_service_rating": (80, 95),  # Excellent customer service
            "skill_speed": (75, 90),       # Fast on their feet
        },
    }
    
    profile = role_profiles.get(role, role_profiles["WAITER"])  # Default to WAITER if unknown
    
    result = {}
    for skill_name, (min_val, max_val) in profile.items():
        csv_value = csv_values.get(skill_name)
        if csv_value is not None and not pd.isna(csv_value):
            # Use CSV value if provided and valid
            result[skill_name] = float(csv_value)
        else:
            # Generate role-appropriate value with some randomness
            result[skill_name] = round(random.uniform(min_val, max_val), 1)
    
    return result


def import_employees_csv(client: firestore.Client, csv_path: str | Path) -> int:
    """
    Import employees from CSV into Firestore.
    
    Args:
        client: Firestore client
        csv_path: Path to employees CSV
    
    Returns:
        Number of employees imported
    """
    df = pd.read_csv(csv_path)
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    
    # Map CSV column names to model field names
    column_mapping = {
        'coffee_rating': 'skill_coffee',
        'sandwich_rating': 'skill_sandwich',
        'speed_rating': 'skill_speed',
    }
    df.rename(columns=column_mapping, inplace=True)
    
    # Normalize role to uppercase
    if 'primary_role' in df.columns:
        df['primary_role'] = df['primary_role'].str.upper()
    
    # Create Employee objects with role-appropriate skills
    employees = []
    for _, row in df.iterrows():
        role = str(row['primary_role'])
        
        # Get CSV values (may be NaN/None)
        csv_skills = {
            'skill_coffee': row.get('skill_coffee'),
            'skill_sandwich': row.get('skill_sandwich'),
            'customer_service_rating': row.get('customer_service_rating'),
            'skill_speed': row.get('skill_speed'),
        }
        
        # Generate role-appropriate skills (uses CSV values if present, otherwise generates)
        skills = generate_role_based_skills(role, csv_skills)
        
        emp = Employee(
            employee_id=int(row['employee_id']),
            first_name=str(row['first_name']),
            last_name=str(row['last_name']),
            primary_role=role,
            skill_coffee=skills['skill_coffee'],
            skill_sandwich=skills['skill_sandwich'],
            customer_service_rating=skills['customer_service_rating'],
            skill_speed=skills['skill_speed'],
        )
        employees.append(emp)
    
    # Bulk insert to Firestore
    EmployeeRepository.bulk_create(client, employees)
    
    print(f"[INFO] Imported {len(employees)} employees from {csv_path}")
    return len(employees)


def import_shifts_csv(client: firestore.Client, csv_path: str | Path, week_id: str | None = None) -> int:
    """
    Import shifts from CSV into Firestore.
    
    Args:
        client: Firestore client
        csv_path: Path to shifts CSV
        week_id: Optional week_id to filter (e.g., "2025-W36")
    
    Returns:
        Number of shifts imported
    """
    df = pd.read_csv(csv_path)
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    df.rename(columns={'id': 'shift_id'}, inplace=True)
    
    # Filter by week if specified
    if week_id is not None and 'week_id' in df.columns:
        df = df[df['week_id'] == week_id].copy()
    
    # Convert date to string format (YYYY-MM-DD)
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    
    # Create Shift objects
    shifts = []
    for _, row in df.iterrows():
        shift = Shift(
            shift_id=int(row['shift_id']),
            date=row['date'],
            week_id=str(row['week_id']),
        )
        shifts.append(shift)
    
    # Bulk insert to Firestore
    ShiftRepository.bulk_create(client, shifts)
    
    print(f"[INFO] Imported {len(shifts)} shifts from {csv_path}")
    return len(shifts)


def import_feedback_csv(client: firestore.Client, csv_path: str | Path, week_id: str | None = None) -> int:
    """
    Import feedback from CSV into Firestore.
    
    Args:
        client: Firestore client
        csv_path: Path to feedback CSV
        week_id: Optional week_id to filter
    
    Returns:
        Number of feedback records imported
    """
    df = pd.read_csv(csv_path)
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    
    # Filter by week if specified
    if week_id is not None and 'week_id' in df.columns:
        df = df[df['week_id'] == week_id].copy()
    
    # Convert dates to string format
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    if 'submitted_at' in df.columns:
        df['submitted_at'] = pd.to_datetime(df['submitted_at'])
    
    # Normalize role
    if 'role' in df.columns:
        df['role'] = df['role'].str.upper()
    
    # Deduplicate: keep latest by submitted_at
    if 'submitted_at' in df.columns:
        df = df.sort_values('submitted_at')
    df = df.drop_duplicates(subset=['shift_id', 'emp_id'], keep='last')
    
    # Create Feedback objects
    feedbacks = []
    for _, row in df.iterrows():
        feedback = Feedback(
            week_id=str(row['week_id']),
            date=row['date'],
            shift_id=int(row['shift_id']),
            emp_id=int(row['emp_id']),
            role=str(row['role']),
            present=bool(str(row.get('present', 'TRUE')).upper() in ['TRUE', 'T', '1', 'YES']),
            overall_service_rating=int(row['overall_service_rating']),
            traffic_level=str(row.get('traffic_level', 'normal')).lower(),
            comment=str(row.get('comment', '')) if pd.notna(row.get('comment')) else None,
            tags=str(row.get('tags', '')) if pd.notna(row.get('tags')) else None,
            submitted_at=row.get('submitted_at', pd.Timestamp.now()) if pd.notna(row.get('submitted_at')) else None,
        )
        feedbacks.append(feedback)
    
    # Bulk insert to Firestore
    FeedbackRepository.bulk_create(client, feedbacks)
    
    print(f"[INFO] Imported {len(feedbacks)} feedback records from {csv_path}")
    return len(feedbacks)

