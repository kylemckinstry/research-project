"""Repository classes for Firestore data access."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from google.cloud import firestore

from .models import Assignment, Employee, Feedback, Shift


class EmployeeRepository:
    """Repository for employee data access using Firestore."""
    
    COLLECTION = "employees"
    
    @staticmethod
    def get_all(client: firestore.Client) -> List[Employee]:
        """Get all employees."""
        docs = client.collection(EmployeeRepository.COLLECTION).stream()
        return [Employee.from_dict({**doc.to_dict(), "employee_id": int(doc.id)}) 
                for doc in docs]
    
    @staticmethod
    def get_by_id(client: firestore.Client, employee_id: int) -> Optional[Employee]:
        """Get employee by ID."""
        doc = client.collection(EmployeeRepository.COLLECTION).document(str(employee_id)).get()
        if doc.exists:
            return Employee.from_dict({**doc.to_dict(), "employee_id": employee_id})
        return None
    
    @staticmethod
    def get_by_role(client: firestore.Client, role: str) -> List[Employee]:
        """Get all employees with a specific role."""
        docs = client.collection(EmployeeRepository.COLLECTION)\
            .where("primary_role", "==", role.upper())\
            .stream()
        return [Employee.from_dict({**doc.to_dict(), "employee_id": int(doc.id)}) 
                for doc in docs]
    
    @staticmethod
    def create(client: firestore.Client, employee: Employee) -> Employee:
        """Create a new employee."""
        doc_ref = client.collection(EmployeeRepository.COLLECTION)\
            .document(str(employee.employee_id))
        doc_ref.set(employee.to_dict())
        return employee
    
    @staticmethod
    def update(client: firestore.Client, employee: Employee) -> Employee:
        """Update an existing employee."""
        doc_ref = client.collection(EmployeeRepository.COLLECTION)\
            .document(str(employee.employee_id))
        doc_ref.set(employee.to_dict(), merge=True)
        return employee
    
    @staticmethod
    def bulk_create(client: firestore.Client, employees: List[Employee]) -> None:
        """Create multiple employees in batches."""
        batch = client.batch()
        count = 0
        
        for emp in employees:
            doc_ref = client.collection(EmployeeRepository.COLLECTION)\
                .document(str(emp.employee_id))
            batch.set(doc_ref, emp.to_dict())
            count += 1
            
            # Commit in batches of 500 (Firestore limit)
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        # Commit remaining
        if count % 500 != 0:
            batch.commit()


class ShiftRepository:
    """Repository for shift data access using Firestore."""
    
    COLLECTION = "shifts"
    
    @staticmethod
    def get_all(client: firestore.Client) -> List[Shift]:
        """Get all shifts."""
        docs = client.collection(ShiftRepository.COLLECTION).stream()
        return [Shift.from_dict(doc.to_dict()) for doc in docs]
    
    @staticmethod
    def get_by_week(client: firestore.Client, week_id: str) -> List[Shift]:
        """Get all shifts for a specific week."""
        docs = client.collection(ShiftRepository.COLLECTION)\
            .where("week_id", "==", week_id)\
            .stream()
        shifts = [Shift.from_dict(doc.to_dict()) for doc in docs]
        # Sort by date in Python to avoid needing a Firestore composite index
        return sorted(shifts, key=lambda s: s.date)
    
    @staticmethod
    def get_by_id(client: firestore.Client, shift_id: int) -> Optional[Shift]:
        """Get shift by ID."""
        # Try direct lookup first
        doc = client.collection(ShiftRepository.COLLECTION).document(str(shift_id)).get()
        if doc.exists:
            return Shift.from_dict(doc.to_dict())
        
        # Fallback: query by shift_id field
        docs = list(client.collection(ShiftRepository.COLLECTION)\
            .where("shift_id", "==", shift_id)\
            .limit(1)\
            .stream())
        
        if docs:
            return Shift.from_dict(docs[0].to_dict())
        return None
    
    @staticmethod
    def create(client: firestore.Client, shift: Shift) -> Shift:
        """Create a new shift."""
        doc_ref = client.collection(ShiftRepository.COLLECTION)\
            .document(str(shift.shift_id))
        doc_ref.set(shift.to_dict())
        return shift
    
    @staticmethod
    def bulk_create(client: firestore.Client, shifts: List[Shift]) -> None:
        """Create multiple shifts in batches."""
        batch = client.batch()
        count = 0
        
        for shift in shifts:
            doc_ref = client.collection(ShiftRepository.COLLECTION)\
                .document(str(shift.shift_id))
            batch.set(doc_ref, shift.to_dict())
            count += 1
            
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        if count % 500 != 0:
            batch.commit()


class AssignmentRepository:
    """Repository for assignment data access using Firestore."""
    
    @staticmethod
    def _get_week_assignments_collection(client: firestore.Client, week_id: str):
        """Get the assignments subcollection for a specific week."""
        return client.collection("weeks").document(week_id).collection("assignments")
    
    @staticmethod
    def get_all(client: firestore.Client) -> List[Assignment]:
        """
        Get all assignments across all weeks.
        Note: This requires querying all week documents.
        """
        assignments = []
        weeks_docs = client.collection("weeks").stream()
        
        for week_doc in weeks_docs:
            assign_docs = week_doc.reference.collection("assignments").stream()
            for doc in assign_docs:
                assignments.append(Assignment.from_dict(doc.to_dict(), doc.id))
        
        return assignments
    
    @staticmethod
    def get_by_week(client: firestore.Client, week_id: str) -> List[Assignment]:
        """Get all assignments for a specific week."""
        docs = AssignmentRepository._get_week_assignments_collection(client, week_id).stream()
        return [Assignment.from_dict(doc.to_dict(), doc.id) for doc in docs]
    
    @staticmethod
    def get_by_employee(client: firestore.Client, emp_id: int) -> List[Assignment]:
        """
        Get all assignments for a specific employee across all weeks.
        Note: This requires querying all week documents.
        """
        assignments = []
        weeks_docs = client.collection("weeks").stream()
        
        for week_doc in weeks_docs:
            assign_docs = week_doc.reference.collection("assignments")\
                .where("employeeId", "==", emp_id)\
                .stream()
            for doc in assign_docs:
                data = doc.to_dict()
                # Normalize field names
                data["emp_id"] = data.get("employeeId", data.get("emp_id"))
                data["shift_id"] = data.get("shiftId", data.get("shift_id"))
                assignments.append(Assignment.from_dict(data, doc.id))
        
        return assignments
    
    @staticmethod
    def create(client: firestore.Client, assignment: Assignment, week_id: str) -> Assignment:
        """Create a new assignment."""
        collection = AssignmentRepository._get_week_assignments_collection(client, week_id)
        doc_ref = collection.document()  # Auto-generate ID
        
        data = assignment.to_dict()
        # Add normalized fields for Firestore queries
        data["employeeId"] = assignment.emp_id
        data["shiftId"] = assignment.shift_id
        
        doc_ref.set(data)
        assignment.id = doc_ref.id
        return assignment
    
    @staticmethod
    def bulk_create(client: firestore.Client, assignments: List[Assignment], week_id: str) -> None:
        """Create multiple assignments in batches."""
        batch = client.batch()
        count = 0
        collection = AssignmentRepository._get_week_assignments_collection(client, week_id)
        
        for assignment in assignments:
            doc_ref = collection.document()  # Auto-generate ID
            data = assignment.to_dict()
            # Add normalized fields
            data["employeeId"] = assignment.emp_id
            data["shiftId"] = assignment.shift_id
            
            batch.set(doc_ref, data)
            count += 1
            
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        if count % 500 != 0:
            batch.commit()
    
    @staticmethod
    def delete_by_week(client: firestore.Client, week_id: str) -> int:
        """Delete all assignments for a specific week. Returns number of deleted documents."""
        collection = AssignmentRepository._get_week_assignments_collection(client, week_id)
        docs = list(collection.stream())
        
        batch = client.batch()
        count = 0
        
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        if count % 500 != 0:
            batch.commit()
        
        return count
    
    @staticmethod
    def list_by_week(client: firestore.Client, week_id: str) -> List[Assignment]:
        """Alias for get_by_week for backwards compatibility."""
        return AssignmentRepository.get_by_week(client, week_id)


class FeedbackRepository:
    """Repository for feedback data access using Firestore."""
    
    COLLECTION = "feedback"
    
    @staticmethod
    def get_all(client: firestore.Client) -> List[Feedback]:
        """Get all feedback."""
        docs = client.collection(FeedbackRepository.COLLECTION).stream()
        return [Feedback.from_dict(doc.to_dict(), doc.id) for doc in docs]
    
    @staticmethod
    def get_by_week(client: firestore.Client, week_id: str) -> List[Feedback]:
        """Get all feedback for a specific week."""
        docs = client.collection(FeedbackRepository.COLLECTION)\
            .where("week_id", "==", week_id)\
            .stream()
        return [Feedback.from_dict(doc.to_dict(), doc.id) for doc in docs]
    
    @staticmethod
    def get_by_employee(client: firestore.Client, emp_id: int) -> List[Feedback]:
        """Get all feedback for a specific employee."""
        docs = client.collection(FeedbackRepository.COLLECTION)\
            .where("emp_id", "==", emp_id)\
            .stream()
        feedbacks = [Feedback.from_dict(doc.to_dict(), doc.id) for doc in docs]
        # Sort by submitted_at in Python to avoid needing a Firestore composite index
        return sorted(feedbacks, key=lambda f: f.submitted_at or datetime.min)
    
    @staticmethod
    def create(client: firestore.Client, feedback: Feedback) -> Feedback:
        """Create a new feedback record."""
        doc_ref = client.collection(FeedbackRepository.COLLECTION).document()
        doc_ref.set(feedback.to_dict())
        feedback.id = doc_ref.id
        return feedback
    
    @staticmethod
    def bulk_create(client: firestore.Client, feedbacks: List[Feedback]) -> None:
        """Create multiple feedback records in batches."""
        batch = client.batch()
        count = 0
        
        for feedback in feedbacks:
            doc_ref = client.collection(FeedbackRepository.COLLECTION).document()
            batch.set(doc_ref, feedback.to_dict())
            count += 1
            
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        if count % 500 != 0:
            batch.commit()


# Backwards compatibility: DatabaseManager class
class DatabaseManager:
    """Manages Firestore client connection. This provides backwards compatibility."""
    
    def __init__(self, db_url: str = None):
        """
        Initialize database manager.
        The db_url parameter is ignored but kept for backwards compatibility.
        """
        from .db import get_firestore
        self.client = get_firestore()
    
    def create_tables(self):
        """No-op for Firestore. Collections are created automatically on first write."""
        print("[INFO] Firestore collections will be created on first write")
    
    def drop_tables(self):
        """Drop all collections. Use this with caution!"""
        from .db import reset_database
        reset_database()
    
    def get_session(self) -> firestore.Client:
        """Get Firestore client."""
        return self.client

