from __future__ import annotations
from pathlib import Path
from typing import List
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from scheduler.config import load_config, resolve_day_profile
from scheduler.domain.db import get_session
from scheduler.domain.models import Assignment
from scheduler.domain.repositories import (
    AssignmentRepository, EmployeeRepository, ShiftRepository,
)
from scheduler.engine.orchestrator import Orchestrator
from scheduler.services.scoring import calculate_role_fitness
from .firestore_client import get_firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from datetime import datetime

DB_URL = "sqlite:///scheduler_v2.1.db"
CONFIG_PATH = Path("scheduler_config.yaml")

app = FastAPI(title="Rostretto Scheduler API", redirect_slashes=False)

ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    resp = await call_next(request)
    if "access-control-allow-origin" not in (k.lower() for k in resp.headers.keys()):
        origin = request.headers.get("origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = "*"
            vary = resp.headers.get("Vary", "")
            resp.headers["Vary"] = "Origin" if not vary else (vary + ", Origin" if "Origin" not in vary else vary)
    return resp

@app.options("/health")
def options_health(): return Response(status_code=204)
@app.options("/employees")
def options_employees(): return Response(status_code=204)
@app.options("/schedule/run")
def options_schedule_run(): return Response(status_code=204)
@app.options("/schedule/{week}")
def options_schedule_week(week: str): return Response(status_code=204)
@app.options("/config")
def options_config(): return Response(status_code=204)
@app.options("/shifts/{week}")
def options_shifts(week: str): return Response(status_code=204)
@app.options("/schedule/run-day")
def options_schedule_run_day(): return Response(status_code=204)
@app.options("/assignments/manual")
def options_assignments_manual(): return Response(status_code=204)
@app.options("/assignments/manual/{week}/{doc_id}")
def options_assignments_manual_delete(week: str, doc_id: str): return Response(status_code=204)

@app.get("/health")
def health(): return {"ok": True}

@app.get("/config")
def get_config():
    cfg = load_config(CONFIG_PATH)
    weights = getattr(cfg, "weights", None)
    return {
        "weights": (weights.__dict__ if weights else {}),
        "schedulerOrder": ["MANAGER", "BARISTA", "SANDWICH", "WAITER"],
    }

@app.get("/employees")
def list_employees():
    from decimal import Decimal
    def f(x, default=0.0):
        try:
            if x is None: return float(default)
            if isinstance(x, Decimal): return float(x)
            return float(x)
        except Exception:
            return float(default)
    session = get_session(DB_URL)
    try:
        emps = EmployeeRepository.get_all(session)
        return [{
            "employeeId": int(getattr(e, "employee_id")),
            "firstName": getattr(e, "first_name", "") or "",
            "lastName": getattr(e, "last_name", "") or "",
            "primaryRole": (getattr(e, "primary_role", "") or "").upper(),
            "hoursWorkedThisWeek": f(getattr(e, "hours_worked_this_week", 0.0)),
            "preferredHoursPerWeek": f(getattr(e, "preferred_hours_per_week", 0.0)),
            "skillCoffee": f(getattr(e, "skill_coffee", 0.0)),
            "skillSandwich": f(getattr(e, "skill_sandwich", 0.0)),
            "customerService": f(getattr(e, "customer_service_rating", 0.0)),
            "speed": f(getattr(e, "skill_speed", getattr(e, "speed", 0.0))),
        } for e in emps]
    finally:
        session.close()

@app.post("/assignments/manual")
def create_manual_assignment(payload: dict):
    """
    Create a manual assignment that persists through Auto Shift.
    Expected payload:
    {
        "week": "2025-W50",
        "shiftId": 123,
        "employeeId": 456,
        "role": "BARISTA"
    }
    """
    week = payload.get("week")
    shift_id = payload.get("shiftId")
    employee_id = payload.get("employeeId")
    role = payload.get("role", "").upper()
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    
    if not week or shift_id is None or employee_id is None:
        raise HTTPException(status_code=400, detail="Missing required fields: week, shiftId, employeeId")
    
    session = get_session(DB_URL)
    try:
        # Verify employee exists
        emp = EmployeeRepository.get_all(session)
        employees = {e.employee_id: e for e in emp}
        if employee_id not in employees:
            raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found")
        
        # Calculate fitness for this assignment
        cfg = load_config(CONFIG_PATH)
        weights = getattr(cfg, "weights", None)
        weights_dict = weights.__dict__ if weights else {}
        
        employee = employees[employee_id]
        try:
            raw = float(calculate_role_fitness(employee, role, weights_dict))
        except Exception:
            raw = 0.0
        
        denom = _fitness_denom(weights_dict, role)
        norm = max(0.0, min(1.0, raw / denom))
        
        # Save to Firestore with isManual flag
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        
        # Generate unique doc_id including time to prevent duplicates
        # Use sanitized time strings (remove spaces and colons)
        time_key = f"{start_time}-{end_time}".replace(" ", "").replace(":", "") if start_time and end_time else ""
        doc_id = f"manual-{shift_id}-{employee_id}-{time_key}" if time_key else f"manual-{shift_id}-{employee_id}"
        doc_ref = week_ref.collection("assignments").document(doc_id)
        
        doc_ref.set({
            "shiftId": shift_id,
            "employeeId": employee_id,
            "role": role,
            "fitness": raw,
            "fitnessNorm": norm,
            "isManual": True,
            "startTime": start_time,
            "endTime": end_time,
            "createdAt": SERVER_TIMESTAMP,
        })
        
        return {
            "week": week,
            "assignment": {
                "id": doc_id,
                "shiftId": shift_id,
                "employeeId": employee_id,
                "role": role,
                "fitness": raw,
                "fitnessNorm": norm,
                "isManual": True,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating manual assignment: {e}")
    finally:
        session.close()

@app.delete("/assignments/manual/{week}/{doc_id}")
def delete_manual_assignment(week: str, doc_id: str):
    """Delete a specific manual assignment."""
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        doc_ref = week_ref.collection("assignments").document(doc_id)
        
        # Verify it exists and is manual
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"Assignment {doc_id} not found")
        
        data = doc.to_dict() or {}
        if not data.get("isManual", False):
            raise HTTPException(status_code=400, detail="Cannot delete auto-generated assignment via this endpoint")
        
        doc_ref.delete()
        
        return {"week": week, "deleted": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting manual assignment: {e}")

@app.post("/assignments/cleanup/{week}")
def cleanup_duplicate_assignments(week: str):
    """
    Remove ALL assignments for the week to ensure clean state.
    This is useful after simplification changes to clear old data.
    """
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        docs = list(week_ref.collection("assignments").stream())
        
        deleted_count = 0
        for d in docs:
            d.reference.delete()
            deleted_count += 1
        
        message = f"Deleted all {deleted_count} assignments for week {week}"
        print(f"[CLEANUP] {message}")
        
        return {
            "week": week,
            "deleted": deleted_count,
            "message": message
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Cleanup error: {e}")

@app.delete("/assignments/day/{week}/{date}")
def delete_day_assignments(week: str, date: str):
    """
    Delete ALL assignments for a specific day.
    Used when converting auto-scheduled day to manual editing.
    
    Args:
        week: ISO week (e.g., "2025-W45")
        date: Date string (e.g., "2025-11-05")
    
    Returns:
        Number of assignments deleted
    """
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        
        # Get all shifts for this week
        shift_docs = list(week_ref.collection("shifts").stream())
        shift_ids_for_date = set()
        
        for shift_doc in shift_docs:
            shift_data = shift_doc.to_dict()
            if shift_data and shift_data.get("date") == date:
                shift_ids_for_date.add(shift_data.get("shiftId"))
        
        # Get all assignments and delete those matching the date's shift IDs
        assignment_docs = list(week_ref.collection("assignments").stream())
        deleted_count = 0
        
        for assign_doc in assignment_docs:
            assign_data = assign_doc.to_dict()
            if assign_data and assign_data.get("shiftId") in shift_ids_for_date:
                assign_doc.reference.delete()
                deleted_count += 1
        
        print(f"[DELETE] Deleted {deleted_count} assignments for {week}/{date}")
        
        return {
            "week": week,
            "date": date,
            "deleted": deleted_count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Delete error: {e}")

def _first(obj, names, default=""):
    if obj is None:
        return default
    for n in names:
        v = getattr(obj, n, None)
        if v not in (None, ""):
            return v
    return default

def _fitness_denom(weights: dict, role: str) -> float:
    ru = (role or "").upper()
    denom = (weights.get("coffee", 0) + weights.get("sandwich", 0)
             + weights.get("speed", 0) + weights.get("customer_service", 0))
    if ru == "MANAGER":
        denom += weights.get("manager_weight", 0)
    return float(denom or 1.0)

def _role_to_demand(role: str) -> str:
    r = (role or "").upper()
    if r == "BARISTA":
        return "Coffee"
    if r == "SANDWICH":
        return "Sandwiches"
    return "Mixed"

def _bucket_traffic(values: list[float]) -> tuple[float, float]:
    """Return (q33, q66). Handles small N safely."""
    if not values:
        return (0.0, 0.0)
    vs = sorted(values)
    n = len(vs)
    
    # Use proper percentile calculation
    # For 33rd percentile: index at 33% of the way through the sorted list
    idx_33 = int((n - 1) * 0.33)
    idx_66 = int((n - 1) * 0.66)
    
    q33 = vs[idx_33]
    q66 = vs[idx_66]
    
    # If q33 and q66 are the same, spread them out based on min/max
    if q33 == q66 and n > 2:
        min_val = vs[0]
        max_val = vs[-1]
        if min_val < max_val:
            # Create thresholds between min and max
            range_val = max_val - min_val
            q33 = min_val + range_val * 0.33
            q66 = min_val + range_val * 0.66
    
    return (q33, q66)

def _traffic_label(v: float, q33: float, q66: float) -> str:
    # Handle edge case where all values are the same
    if q33 == q66:
        return "medium"
    if v < q33:
        return "low"
    if v <= q66:
        return "medium"
    return "high"

def _load_manual_assignments_from_firestore(session, manual_assignments_data):
    """
    Load manual assignments from Firestore data, deduplicating any duplicates.
    Returns a list of Assignment objects.
    """
    def _load_shift_by_id(sess, sid):
        try:
            if hasattr(ShiftRepository, "get_by_id"): return ShiftRepository.get_by_id(sess, sid)
            if hasattr(ShiftRepository, "get"): return ShiftRepository.get(sess, sid)
        except Exception: pass
        try:
            from scheduler.domain.models import Shift
            return sess.get(Shift, sid)
        except Exception:
            return None
    
    existing_assignments: List[Assignment] = []
    seen_assignments = set()  # Track (emp_id, shift_id, start_time, end_time) to prevent duplicates
    
    for data in manual_assignments_data:
        shift_id = data.get("shiftId")
        employee_id = data.get("employeeId")
        role = data.get("role", "MIXED")
        start_time_str = data.get("startTime", "")
        end_time_str = data.get("endTime", "")
        
        if shift_id and employee_id and start_time_str and end_time_str:
            try:
                # Load the shift to get the date
                shift = _load_shift_by_id(session, shift_id)
                if not shift:
                    print(f"[WARN] Could not load shift {shift_id} for manual assignment")
                    continue
                
                shift_date = _first(shift, ["date", "day", "shift_date", "date_str"], "")
                if not shift_date:
                    print(f"[WARN] Shift {shift_id} has no date")
                    continue
                
                # Parse date (YYYY-MM-DD)
                date_obj = datetime.strptime(str(shift_date), "%Y-%m-%d")
                
                # Parse times (e.g., "7:00 am")
                start_time = datetime.strptime(start_time_str, "%I:%M %p")
                end_time = datetime.strptime(end_time_str, "%I:%M %p")
                
                # Combine date with time
                start_dt = datetime.combine(date_obj.date(), start_time.time())
                end_dt = datetime.combine(date_obj.date(), end_time.time())
                
                # Check for duplicates using a unique key (emp_id, shift_id, start_time, end_time)
                assignment_key = (employee_id, shift_id, start_dt, end_dt)
                if assignment_key in seen_assignments:
                    print(f"[WARN] Skipping duplicate manual assignment in Firestore: emp_id={employee_id}, shift_id={shift_id}, time={start_time_str}-{end_time_str}, role={role}")
                    continue
                seen_assignments.add(assignment_key)
                
                # Create Assignment object with proper datetime
                assignment = Assignment(
                    shift_id=shift_id,
                    emp_id=employee_id,
                    role=role,
                    start_time=start_dt,
                    end_time=end_dt
                )
                existing_assignments.append(assignment)
                print(f"[DEBUG] Loading manual assignment: emp_id={employee_id}, shift_id={shift_id}, role={role}, time={start_time_str}-{end_time_str}, date={shift_date}")
            except Exception as e:
                print(f"[ERROR] Failed to parse manual assignment: {e}")
                continue
    
    return existing_assignments

from datetime import datetime as _dt
def _norm_time_str(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = _dt.strptime(s, fmt).time()
            return _dt.strptime(t.strftime("%I:%M %p"), "%I:%M %p").strftime("%I:%M %p").lstrip("0").lower()
        except Exception:
            continue
    return s.lower().lstrip("0")

@app.post("/schedule/run")
def run_schedule(payload: dict):
    """
    Run Auto Shift for entire week.
    
    Simplified: No manual assignments, just auto-generate schedule.
    """
    week = payload.get("week")
    if not week:
        raise HTTPException(status_code=400, detail="Missing 'week' in body")
    
    session = get_session(DB_URL)
    try:
        cfg = load_config(CONFIG_PATH)
        scheduler_order = ["MANAGER", "BARISTA", "SANDWICH", "WAITER"]
        orchestrator = Orchestrator(scheduler_order)
        
        # Build schedule (orchestrator deduplicates automatically)
        assignments: List[Assignment] = orchestrator.build_schedule(session, week, cfg, None)
        
        # Save to SQLite
        AssignmentRepository.delete_by_week(session, week)
        AssignmentRepository.bulk_create(session, assignments)
        
        # Prepare for Firestore save
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        weights = getattr(cfg, "weights", None)
        weights_dict = weights.__dict__ if weights else {}
        employees = {e.employee_id: e for e in EmployeeRepository.get_all(session)}
        
        # Helper to load shift
        def _load_shift_by_id(sess, sid):
            try:
                if hasattr(ShiftRepository, "get_by_id"):
                    return ShiftRepository.get_by_id(sess, sid)
                if hasattr(ShiftRepository, "get"):
                    return ShiftRepository.get(sess, sid)
            except:
                pass
            try:
                from scheduler.domain.models import Shift
                return sess.get(Shift, sid)
            except:
                return None
        
        # Clear Firestore
        for col in ("shifts", "assignments"):
            for doc in week_ref.collection(col).stream():
                doc.reference.delete()
        
        # Save shifts to Firestore
        shift_ids = sorted({a.shift_id for a in assignments})
        date_by_shift: dict[int, str] = {}
        roles_by_date: dict[str, dict[str, int]] = {}
        
        s_batch = db.batch()
        for sid in shift_ids:
            s = _load_shift_by_id(session, sid)
            if not s:
                continue
            
            role_val = str(_first(s, ["role", "position", "kind", "role_name", "name"], "")).upper()
            date_val = str(_first(s, ["date", "day", "shift_date", "date_str"], ""))
            start_val = str(_first(s, ["start_time", "start", "starts_at", "start_str"], ""))
            end_val = str(_first(s, ["end_time", "end", "ends_at", "end_str"], ""))
            
            if not start_val or not end_val:
                start_val = start_val or cfg.default_shift.start
                end_val = end_val or cfg.default_shift.end
            
            if not role_val:
                role_val = "MIXED"
            
            s_ref = week_ref.collection("shifts").document(str(getattr(s, "id", sid)))
            s_batch.set(s_ref, {
                "shiftId": getattr(s, "id", sid),
                "role": role_val,
                "date": date_val,
                "start": start_val,
                "end": end_val,
            })
            
            date_by_shift[int(getattr(s, "id", sid))] = date_val
            if date_val and role_val:
                roles_by_date.setdefault(date_val, {})
                roles_by_date[date_val][role_val] = roles_by_date[date_val].get(role_val, 0) + 1
        
        s_batch.commit()
        
        # Save assignments to Firestore (simplified - no manual logic)
        batch = db.batch()
        day_stats: dict[str, dict[str, int]] = {}
        
        for a in assignments:
            emp = employees.get(a.emp_id)
            role = (a.role or "").upper()
            
            # Calculate fitness
            try:
                raw = float(calculate_role_fitness(emp, role, weights_dict)) if emp else 0.0
            except:
                raw = 0.0
            denom = _fitness_denom(weights_dict, role)
            norm = max(0.0, min(1.0, raw / denom))
            
            # Simple doc_id: shift-employee
            doc_id = f"{a.shift_id}-{a.emp_id}"
            doc_ref = week_ref.collection("assignments").document(doc_id)
            
            doc_data = {
                "shiftId": a.shift_id,
                "employeeId": a.emp_id,
                "role": role,
                "fitness": raw,
                "fitnessNorm": norm,
                "createdAt": SERVER_TIMESTAMP,
            }
            
            batch.set(doc_ref, doc_data)
            
            # Stats
            date_val = date_by_shift.get(int(a.shift_id))
            if date_val:
                st = day_stats.setdefault(date_val, {"assigned": 0, "mismatch": 0})
                st["assigned"] += 1
                if norm < 0.7:
                    st["mismatch"] += 1
        
        batch.commit()
        
        print(f"[INFO] Saved {len(assignments)} assignments to Firestore")
        
        # Save indicators
        signals = [v["assigned"] for v in day_stats.values()] if day_stats else []
        q33, q66 = _bucket_traffic(signals)
        ind_batch = db.batch()
        
        for date_val in sorted(set(list(roles_by_date.keys()) + list(day_stats.keys()))):
            role_counts = roles_by_date.get(date_val, {})
            top_role = max(role_counts.items(), key=lambda kv: kv[1])[0] if role_counts else "MIXED"
            demand = _role_to_demand(top_role)
            assigned = day_stats.get(date_val, {}).get("assigned", 0)
            mismatches = day_stats.get(date_val, {}).get("mismatch", 0)
            traffic = _traffic_label(assigned, q33, q66) if signals else "medium"
            
            ind_ref = week_ref.collection("indicators").document(date_val)
            ind_batch.set(ind_ref, {
                "demand": demand,
                "traffic": traffic,
                "mismatches": mismatches,
            }, merge=True)
        
        ind_batch.commit()
        
        return {"week": week, "created": len(assignments)}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheduler error: {e}")
    finally:
        session.close()

@app.post("/schedule/run-day")
def run_day(payload: dict):
    """Run Auto Shift for a single day. Simplified - no manual assignments."""
    week = payload.get("week_id") or payload.get("week")
    date_str = payload.get("date")
    if not week or not date_str:
        raise HTTPException(status_code=400, detail="Missing 'week_id' (or 'week') or 'date' in body")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid 'date' format, expected YYYY-MM-DD")
    session = get_session(DB_URL)
    try:
        cfg = load_config(CONFIG_PATH)
        scheduler_order = ["MANAGER", "BARISTA", "SANDWICH", "WAITER"]
        orchestrator = Orchestrator(scheduler_order)
        
        # Build schedule for entire week first (orchestrator needs full context)
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        
        # Generate schedule for entire week
        all_assignments: List[Assignment] = orchestrator.build_schedule(session, week, cfg, None)
        
        # Filter to only the requested day's assignments
        employees = {e.employee_id: e for e in EmployeeRepository.get_all(session)}
        def _load_shift_by_id(sess, sid):
            try:
                if hasattr(ShiftRepository, "get_by_id"): return ShiftRepository.get_by_id(sess, sid)
                if hasattr(ShiftRepository, "get"): return ShiftRepository.get(sess, sid)
            except Exception: pass
            try:
                from scheduler.domain.models import Shift
                return sess.get(Shift, sid)
            except Exception:
                return None
        
        # Identify shifts for the requested day
        shifts_for_week = {}
        for a in all_assignments:
            if a.shift_id not in shifts_for_week:
                s = _load_shift_by_id(session, a.shift_id)
                if s: shifts_for_week[a.shift_id] = s
        
        # Find which shift IDs belong to the requested date
        day_shift_ids = set()
        for sid, s in shifts_for_week.items():
            s_date = str(_first(s, ["date", "day", "shift_date", "date_str"], ""))
            if s_date == date_str:
                day_shift_ids.add(sid)
        
        if not day_shift_ids:
            return {"week": week, "date": date_str, "created": 0, "message": "No shifts for date"}
        
        # Filter to only assignments for this day
        day_assignments = [a for a in all_assignments if a.shift_id in day_shift_ids]
        
        # Get day profile for the requested day
        demand_override = None
        try:
            ov_doc = week_ref.collection("demand").document(date_str).get()
            if ov_doc.exists:
                demand_override = ov_doc.to_dict() or None
        except Exception:
            demand_override = None
        day_profile = resolve_day_profile(cfg, dt, demand_override)
        weights = getattr(cfg, "weights", None)
        weights_dict = weights.__dict__ if weights else {}
        eff = dict(weights_dict)
        eff["coffee"] = float(eff.get("coffee", 1.0)) * float(day_profile.coffee)
        eff["sandwich"] = float(eff.get("sandwich", 1.0)) * float(day_profile.sandwich)
        eff["speed"] = float(eff.get("speed", 1.0)) * float(day_profile.speed)
        eff["customer_service"] = float(eff.get("customer_service", 1.0)) * float(day_profile.customer_service)
        for d in week_ref.collection("shifts").stream():
            data = d.to_dict() or {}
            if str(data.get("date", "")) == date_str:
                d.reference.delete()
        s_batch = db.batch()
        role_counts_today: dict[str, int] = {}
        for sid in sorted(day_shift_ids):
            s = shifts_for_week.get(sid)
            if not s: continue
            role_val = str(_first(s, ["role", "position", "kind", "role_name", "name"], "")).upper()
            date_val = str(_first(s, ["date", "day", "shift_date", "date_str"], ""))
            start_val = str(_first(s, ["start_time", "start", "starts_at", "start_str", "start_dt", "starttime"], ""))
            end_val   = str(_first(s, ["end_time", "end", "ends_at", "end_str", "end_dt", "endtime"], ""))
            if not start_val or not end_val:
                start_val = start_val or cfg.default_shift.start
                end_val = end_val or cfg.default_shift.end
            if not role_val:
                counts = {}
                for a in day_assignments:
                    if a.shift_id != sid:
                        continue
                    r = (getattr(a, "role", "") or "").upper()
                    if not r:
                        continue
                    counts[r] = counts.get(r, 0) + 1
                dominance_ratio = 0.60
                if counts:
                    total = sum(counts.values())
                    top_role, top_count = max(counts.items(), key=lambda kv: kv[1])
                    role_val = top_role if (top_count / max(1, total)) >= dominance_ratio else "MIXED"
                else:
                    role_val = ""
                if not role_val or role_val == "MIXED":
                    try:
                        dt_for_day = datetime.strptime(date_val, "%Y-%m-%d")
                        dp = resolve_day_profile(cfg, dt_for_day, None)
                        prim = (getattr(dp, "primary", "") or "").upper()
                        prim_map = {"COFFEE": "BARISTA", "SANDWICH": "SANDWICH", "MIXED": "MIXED"}
                        role_val = prim_map.get(prim, role_val or "MIXED")
                    except Exception:
                        role_val = role_val or "MIXED"
            s_ref = week_ref.collection("shifts").document(str(getattr(s, "id", sid)))
            s_batch.set(s_ref, {
                "shiftId": getattr(s, "id", sid),
                "role": role_val,
                "date": date_val,
                "start": start_val,
                "end": end_val,
            })
            if date_val == date_str and role_val:
                role_counts_today[role_val] = role_counts_today.get(role_val, 0) + 1
        s_batch.commit()
        
        # Delete only this day's existing assignments (leave other days untouched)
        existing_assign_docs = list(week_ref.collection("assignments").stream())
        to_delete = [d for d in existing_assign_docs if (d.to_dict() or {}).get("shiftId") in day_shift_ids]
        for d in to_delete:
            d.reference.delete()
        
        # Save only this day's assignments
        batch = db.batch()
        assigned_today = 0
        mismatches_today = 0
        
        # Process assignments for this day only
        for a in day_assignments:
            emp = employees.get(a.emp_id)
            role = (a.role or "").upper()
            
            try:
                raw = float(calculate_role_fitness(emp, role, eff)) if emp else 0.0
            except Exception:
                raw = 0.0
            denom = _fitness_denom(eff, role)
            norm = max(0.0, min(1.0, raw / denom))
            doc_id = str(a.id) if getattr(a, "id", None) is not None else f"{a.shift_id}-{a.emp_id}"
            doc_ref = week_ref.collection("assignments").document(doc_id)
            batch.set(doc_ref, {
                "shiftId": a.shift_id,
                "employeeId": a.emp_id,
                "role": role,
                "fitness": raw,
                "fitnessNorm": norm,
                "isManual": False,
                "createdAt": SERVER_TIMESTAMP,
            })
            assigned_today += 1
            if norm < 0.7:
                mismatches_today += 1
        
        batch.commit()
        
        # Calculate traffic based on week's assignment distribution
        # Get all assignments for the week to calculate percentiles
        all_week_docs = list(week_ref.collection("assignments").stream())
        day_counts = {}
        for doc in all_week_docs:
            doc_data = doc.to_dict()
            shift_id = doc_data.get("shiftId")
            if shift_id in shifts_for_week:
                shift = shifts_for_week[shift_id]
                shift_date = str(_first(shift, ["date", "day", "shift_date", "date_str"], ""))
                if shift_date:
                    day_counts[shift_date] = day_counts.get(shift_date, 0) + 1
        
        # Calculate traffic using percentiles
        if len(day_counts) > 1:
            signals = list(day_counts.values())
            q33, q66 = _bucket_traffic(signals)
            traffic = _traffic_label(assigned_today, q33, q66)
        else:
            # Fallback for single-day weeks
            if assigned_today <= 3:
                traffic = "low"
            elif assigned_today <= 6:
                traffic = "medium"
            else:
                traffic = "high"
        
        top_role = max(role_counts_today.items(), key=lambda kv: kv[1])[0] if role_counts_today else "MIXED"
        demand = _role_to_demand(top_role)
        ind_ref = week_ref.collection("indicators").document(date_str)
        ind_batch = db.batch()
        ind_batch.set(ind_ref, {
            "demand": demand,
            "traffic": traffic,
            "mismatches": mismatches_today,
        }, merge=True)
        ind_batch.commit()
        return {"week": week, "date": date_str, "created": assigned_today}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheduler error: {e}")
    finally:
        session.close()

@app.get("/schedule/{week}")
def get_schedule(week: str):
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        docs = list(week_ref.collection("assignments").stream())
        return [{
            "id": d.id,  # Keep as string (Firestore doc_id) for delete operations
            "shiftId": (data := d.to_dict()).get("shiftId"),
            "employeeId": data.get("employeeId"),
            "role": (data.get("role") or "").upper(),
            "fitness": data.get("fitness"),
            "fitnessNorm": data.get("fitnessNorm"),
            "isManual": data.get("isManual", False),
            "startTime": data.get("startTime"),
            "endTime": data.get("endTime"),
        } for d in docs]
    except Exception:
        session = get_session(DB_URL)
        try:
            assigns = AssignmentRepository.list_by_week(session, week)
            return [{
                "id": a.id,
                "shiftId": a.shift_id,
                "employeeId": a.emp_id,
                "role": (a.role or "").upper(),
                "isManual": False,
            } for a in assigns]
        finally:
            session.close()

@app.get("/shifts/{week}")
def get_shifts(week: str):
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        docs = list(week_ref.collection("shifts").stream())
        if docs:
            return [{
                "id": int(d.id) if str(d.id).isdigit() else d.id,
                "shiftId": (data := d.to_dict()).get("shiftId"),
                "role": (str(data.get("role", "")) or "").upper(),
                "date": str(data.get("date", "")),
                "start": str(data.get("start", "")),
                "end": str(data.get("end", "")),
            } for d in docs]
    except Exception:
        pass
    session = get_session(DB_URL)
    try:
        assigns = AssignmentRepository.list_by_week(session, week)
        shift_ids = sorted({a.shift_id for a in assigns})
        def _load_shift_by_id(sess, sid):
            try:
                if hasattr(ShiftRepository, "get_by_id"): return ShiftRepository.get_by_id(sess, sid)
                if hasattr(ShiftRepository, "get"): return ShiftRepository.get(sess, sid)
            except Exception: pass
            try:
                from scheduler.domain.models import Shift
                return sess.get(Shift, sid)
            except Exception:
                return None
        out = []
        for sid in shift_ids:
            s = _load_shift_by_id(session, sid)
            if not s: continue
            out.append({
                "id": getattr(s, "id", sid),
                "shiftId": getattr(s, "id", sid),
                "role": str(_first(s, ["role", "position", "kind", "role_name", "name"], "")).upper(),
                "date": str(_first(s, ["date", "day", "shift_date", "date_str"], "")),
                "start": str(_first(s, ["start_time", "start", "starts_at", "start_str", "start_dt", "starttime"], "")),
                "end": str(_first(s, ["end_time", "end", "ends_at", "end_str", "end_dt", "endtime"], "")),
            })
        return out
    finally:
        session.close()

@app.get("/indicators/{week}")
def get_indicators(week: str):
    try:
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        docs = list(week_ref.collection("indicators").stream())
        return {
            "week": week,
            "days": [{
                "date": d.id,
                **(d.to_dict() or {})
            } for d in docs]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indicators error: {e}")

@app.options("/shifts/create")
def options_shifts_create(): return Response(status_code=204)

@app.post("/shifts/create")
def create_shifts(payload: dict):
    """
    Create shifts for a specific week.
    Expected payload:
    {
        "week": "2025-W50",
        "shifts": [
            {
                "date": "2025-12-08",
                "start": "07:00",
                "end": "15:00",
                "role": "MIXED"  # optional
            },
            ...
        ]
    }
    """
    week = payload.get("week")
    shifts_data = payload.get("shifts", [])
    
    if not week:
        raise HTTPException(status_code=400, detail="Missing 'week' in body")
    if not shifts_data:
        raise HTTPException(status_code=400, detail="Missing 'shifts' array in body")
    
    session = get_session(DB_URL)
    try:
        from scheduler.domain.models import Shift
        created_shifts = []
        
        for shift_info in shifts_data:
            date_str = shift_info.get("date")
            start_time = shift_info.get("start")
            end_time = shift_info.get("end")
            role = shift_info.get("role", "MIXED")
            
            if not date_str or not start_time or not end_time:
                continue
            
            # Create shift in database
            shift = Shift(
                date=date_str,
                start_time=start_time,
                end_time=end_time,
                role=role.upper()
            )
            session.add(shift)
            session.flush()  # Get the real shift.id before commit
            
            created_shifts.append({
                "id": shift.id,  # Store real SQLite ID
                "date": date_str,
                "start": start_time,
                "end": end_time,
                "role": role.upper()
            })
        
        session.commit()
        
        # Also save to Firestore for frontend access with REAL shift IDs
        db = get_firestore()
        week_ref = db.collection("weeks").document(week)
        s_batch = db.batch()
        
        for shift_info in created_shifts:
            real_shift_id = shift_info["id"]
            s_ref = week_ref.collection("shifts").document(str(real_shift_id))
            s_batch.set(s_ref, {
                "shiftId": real_shift_id,  # Use REAL SQLite shift ID
                "role": shift_info["role"],
                "date": shift_info["date"],
                "start": shift_info["start"],
                "end": shift_info["end"],
            })
        
        s_batch.commit()
        
        return {"week": week, "created": len(created_shifts), "shifts": created_shifts}
    
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating shifts: {e}")
    finally:
        session.close()
