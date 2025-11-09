"""Command-line interface for the refactored scheduler (v2 architecture)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scheduler.domain.db import get_firestore, init_database
from scheduler.domain.repositories import AssignmentRepository
from scheduler.engine.orchestrator import build_week_schedule
from scheduler.io.config import load_config
from scheduler.io.export_csv import export_assignments_csv, export_employees_csv
from scheduler.io.import_csv import import_employees_csv, import_feedback_csv, import_shifts_csv


def _cmd_init_db(args: argparse.Namespace) -> None:
    """Initialize the database (Firestore)."""
    init_database()
    print(f"[OK] Firestore client initialized")


def _cmd_import_csv(args: argparse.Namespace) -> None:
    """Import CSV data into database."""
    client = get_firestore()
    
    try:
        if args.employees:
            count = import_employees_csv(client, args.employees)
            print(f"[OK] Imported {count} employees")
        
        if args.shifts:
            count = import_shifts_csv(client, args.shifts, week_id=args.week)
            print(f"[OK] Imported {count} shifts")
        
        if args.feedback:
            count = import_feedback_csv(client, args.feedback, week_id=args.week)
            print(f"[OK] Imported {count} feedback records")
        
        print("[OK] CSV import complete")
        
    except Exception as e:
        print(f"[ERROR] Import failed: {e}")
        raise


def _cmd_generate(args: argparse.Namespace) -> None:
    """Generate schedule for a week."""
    client = get_firestore()
    
    try:
        cfg = load_config(args.config)
        
        # Build schedule using orchestrator
        assignments = build_week_schedule(client, args.week, cfg, persist=True)
        
        # Export to CSV if requested
        if args.out:
            export_assignments_csv(client, args.out, week_id=args.week)
        
        print(f"[OK] Generated {len(assignments)} assignments for {args.week}")
        
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}")
        raise


def _cmd_export(args: argparse.Namespace) -> None:
    """Export data from database to CSV."""
    client = get_firestore()
    
    try:
        if args.assignments:
            count = export_assignments_csv(client, args.assignments, week_id=args.week)
            print(f"[OK] Exported {count} assignments to {args.assignments}")
        
        if args.employees:
            count = export_employees_csv(client, args.employees)
            print(f"[OK] Exported {count} employees to {args.employees}")
        
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")
        raise


def _cmd_validate(args: argparse.Namespace) -> None:
    """Validate assignments for a week."""
    client = get_firestore()
    
    try:
        cfg = load_config(args.config)
        
        # Get assignments and employees
        assignments = AssignmentRepository.get_by_week(client, args.week)
        from scheduler.domain.repositories import EmployeeRepository
        employees = EmployeeRepository.get_all(client)
        
        # Validate
        from scheduler.services.constraints import validate_assignment_constraints
        validate_assignment_constraints(assignments, employees, cfg)
        
        print(f"[OK] Validation passed for {args.week}")
        
    except Exception as e:
        print(f"[ERROR] Validation failed: {e}")
        raise


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="scheduler_v2",
        description="AI-Assisted Café Rostering System (v2 - Firestore Backend)"
    )
    
    sub = parser.add_subparsers(dest="command", required=True)
    
    # init-db command
    init = sub.add_parser("init-db", help="Initialize Firestore client")
    init.set_defaults(func=_cmd_init_db)
    
    # import-csv command
    imp = sub.add_parser("import-csv", help="Import CSV data into Firestore")
    imp.add_argument("--employees", help="Path to employees CSV")
    imp.add_argument("--shifts", help="Path to shifts CSV")
    imp.add_argument("--feedback", help="Path to feedback CSV")
    imp.add_argument("--week", help="Week ID to filter (optional)")
    imp.set_defaults(func=_cmd_import_csv)
    
    # generate command
    gen = sub.add_parser("generate", help="Generate schedule for a week")
    gen.add_argument("--week", required=True, help="Week ID (e.g., 2025-W48)")
    gen.add_argument("--config", required=True, help="Path to config YAML")
    gen.add_argument("--out", help="Optional: export assignments to CSV")
    gen.set_defaults(func=_cmd_generate)
    
    # export command
    exp = sub.add_parser("export", help="Export data from Firestore to CSV")
    exp.add_argument("--assignments", help="Path to export assignments CSV")
    exp.add_argument("--employees", help="Path to export employees CSV")
    exp.add_argument("--week", help="Week ID to filter assignments (optional)")
    exp.set_defaults(func=_cmd_export)
    
    # validate command
    val = sub.add_parser("validate", help="Validate schedule for a week")
    val.add_argument("--week", required=True, help="Week ID to validate")
    val.add_argument("--config", required=True, help="Path to config YAML")
    val.set_defaults(func=_cmd_validate)
    
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

