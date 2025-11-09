"""CP-SAT scheduler."""

from pathlib import Path

import pandas as pd

from scheduler.ai import CPSatScheduler
from scheduler.config import load_config
from scheduler.domain.db import get_session
from scheduler.domain.repositories import EmployeeRepository


def calculate_shift_ids_from_reference(assignments, reference_csv_path: str):
    """
    Исправляет shift_id в assignments на основе дат, используя reference CSV файл.
    
    Args:
        assignments: List of Assignment objects
        reference_csv_path: Path to shiftDetails CSV with correct shift_id mapping
    
    Returns:
        List of Assignment objects with corrected shift_id
    """
    # Загружаем reference файл для маппинга дат к shift_id
    ref_df = pd.read_csv(reference_csv_path)
    ref_df.columns = ref_df.columns.str.lower().str.strip()
    
    # Создаем маппинг: дата -> shift_id
    # Группируем по shift_id и берем первую дату (они должны быть одинаковые для одного shift_id)
    date_to_shift_id = {}
    for shift_id, group in ref_df.groupby('shift_id'):
        # Берем первую дату из группы
        date_str = pd.to_datetime(group['start_time'].iloc[0]).strftime('%Y-%m-%d')
        date_to_shift_id[date_str] = int(shift_id)
    
    # Находим базовую дату и shift_id для вычисления (последняя дата в reference файле)
    # Используем для дат, которых нет в reference файле
    if date_to_shift_id:
        base_date_str = max(date_to_shift_id.keys())
        base_date = pd.to_datetime(base_date_str).date()
        base_shift_id = date_to_shift_id[base_date_str]
        print(f"[INFO] Base date for calculation: {base_date_str} -> shift_id {base_shift_id}")
    else:
        # Fallback: если reference файл пустой, используем стандартную начальную точку
        base_date = pd.to_datetime('2025-09-01').date()
        base_shift_id = 1000
        print(f"[WARN] Reference file appears empty, using fallback: {base_date} -> shift_id {base_shift_id}")
    
    # Обновляем shift_id в assignments на основе дат
    corrected_assignments = []
    for assign in assignments:
        # Извлекаем дату из start_time (убираем timezone для сравнения)
        assign_date = assign.start_time.date()
        date_str = assign_date.strftime('%Y-%m-%d')
        
        # Сначала пробуем найти в reference файле
        if date_str in date_to_shift_id:
            correct_shift_id = date_to_shift_id[date_str]
        else:
            # Вычисляем на основе базовой даты
            days_diff = (assign_date - base_date).days
            correct_shift_id = base_shift_id + days_diff
            print(f"[INFO] Calculated shift_id for {date_str}: {base_shift_id} + {days_diff} = {correct_shift_id}")
        
        # Fixed shift_id
        from scheduler.domain.models import Assignment
        corrected_assign = Assignment(
            shift_id=correct_shift_id,
            emp_id=assign.emp_id,
            start_time=assign.start_time,
            end_time=assign.end_time,
            role=assign.role,
            shift_type=assign.shift_type,
            day_type=assign.day_type,
        )
        corrected_assignments.append(corrected_assign)
    
    return corrected_assignments


def main():
    """Test CP-SAT scheduler for one week."""
    
    # Configuration
    config_path = "scheduler_config.yaml"
    db_path = "scheduler_v2.1.db"
    historical_skills_path = "data/shiftDetails_24w.csv"
    week_id = "2025-W48"
    output_csv = "schedule_cp_sat_test.csv"
    
    print("=" * 70)
    print("TEST")
    print("=" * 70)
    print(f"WEEK: {week_id}")
    print(f"DATABASES: {db_path}")
    print(f"HISTORICAL SKILLS: {historical_skills_path}")
    print(f"Output FILE: {output_csv}")
    print()
    
    # Loading configuration
    print("[1/6] CONFIG LOADING...")
    cfg = load_config(config_path)
    print(f"  ✓ CONFIG LOADED")
    
    # Creating scheduler
    print(f"\n[2/6] INITIALIZATION CP-SAT scheduler...")
    scheduler = CPSatScheduler(
        historical_skills_path=historical_skills_path,
        skill_match_weight=1.0,
        fairness_weight=0.3,
    )
    print(f"  ✓ Scheduler created")
    
    # Schedule generation
    print(f"\n[3/6] GENERATION SCHEDULE...")
    db_url = f"sqlite:///{db_path}"
    session = get_session(db_url)
    try:
        assignments = scheduler.make_schedule(session, week_id, cfg)
        print(f"  ✓ Schedule is generated: {len(assignments)} assingments")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        raise
    finally:
        session.close()
    
    # Validation (before fixing shift_id)
    print(f"\n[4/6] VALIDATION...")
    from scheduler.domain.repositories import ShiftRepository
    from scheduler.ai.validator import validate_cp_sat_schedule, print_validation_report
    
    session = get_session(db_url)
    try:
        employees_list = EmployeeRepository.get_all(session)
        shifts_list = ShiftRepository.get_by_week(session, week_id)
        
        validation_results = validate_cp_sat_schedule(
            assignments, employees_list, shifts_list, cfg
        )
        print_validation_report(validation_results)
        
        if not validation_results['valid']:
            print("\n✗ Error in validation. Fix the errors above.")
            exit(1)
        else:
            print("\n✓ Validation passed!")
            
    finally:
        session.close()
    
    # Fix shift_id to match reference CSV (only for export)
    print(f"\n[5/6] FIXING SHIFT_IDs FOR EXPORT...")
    assignments_for_export = calculate_shift_ids_from_reference(assignments, historical_skills_path)
    print(f"  ✓ Shift IDs corrected for export")
    
    # Export
    print(f"\n[6/6] EXPORT CSV...")
    records = []
    for assign in assignments_for_export:
        records.append({
            'shift_id': assign.shift_id,
            'emp_id': assign.emp_id,
            'start_time': assign.start_time.isoformat(),
            'end_time': assign.end_time.isoformat(),
            'role': assign.role,
            'shift_type': assign.shift_type,
            'day_type': assign.day_type,
        })
    df = pd.DataFrame(records)
    df.to_csv(output_csv, index=False)
    print(f"  ✓ Exported to {output_csv}")
    
    print(f"\n{'=' * 70}")
    print("Done!")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
