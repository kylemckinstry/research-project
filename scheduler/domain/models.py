"""Firestore-compatible models for café scheduling system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Employee:
    """Employee model with skills and role information."""
    
    employee_id: int
    first_name: str
    last_name: str
    primary_role: str  # MANAGER, BARISTA, WAITER, SANDWICH
    
    # Skills (0-10 scale, nullable for roles that don't use them)
    skill_coffee: Optional[float] = None
    skill_sandwich: Optional[float] = None
    customer_service_rating: Optional[float] = None
    skill_speed: Optional[float] = None
    
    def __repr__(self) -> str:
        return f"<Employee(id={self.employee_id}, name='{self.first_name} {self.last_name}', role='{self.primary_role}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "employee_id": self.employee_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "primary_role": self.primary_role,
            "skill_coffee": self.skill_coffee,
            "skill_sandwich": self.skill_sandwich,
            "customer_service_rating": self.customer_service_rating,
            "skill_speed": self.skill_speed,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Employee:
        """Create Employee from Firestore document."""
        return cls(
            employee_id=data.get("employee_id"),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            primary_role=data.get("primary_role", ""),
            skill_coffee=data.get("skill_coffee"),
            skill_sandwich=data.get("skill_sandwich"),
            customer_service_rating=data.get("customer_service_rating"),
            skill_speed=data.get("skill_speed"),
        )


@dataclass
class Shift:
    """Shift model representing a single day's work period."""
    
    shift_id: int
    date: str  # ISO format: YYYY-MM-DD
    week_id: str  # ISO week format: 2025-W36
    role: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    def __repr__(self) -> str:
        return f"<Shift(id={self.shift_id}, date={self.date}, week={self.week_id})>"
    
    # Alias for compatibility
    @property
    def id(self):
        return self.shift_id
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "shift_id": self.shift_id,
            "date": self.date,
            "week_id": self.week_id,
            "role": self.role,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Shift:
        """Create Shift from Firestore document."""
        return cls(
            shift_id=data.get("shift_id") or data.get("shiftId"),
            date=data.get("date", ""),
            week_id=data.get("week_id", ""),
            role=data.get("role"),
            start_time=data.get("start_time") or data.get("start"),
            end_time=data.get("end_time") or data.get("end"),
        )


@dataclass
class Assignment:
    """Assignment linking an employee to a shift with specific times."""
    
    shift_id: int
    emp_id: int
    start_time: datetime
    end_time: datetime
    role: Optional[str] = None
    shift_type: Optional[str] = None
    day_type: Optional[str] = None
    id: Optional[str] = None  # Firestore document ID
    
    def __repr__(self) -> str:
        return f"<Assignment(id={self.id}, shift={self.shift_id}, emp={self.emp_id}, role={self.role})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "shift_id": self.shift_id,
            "emp_id": self.emp_id,
            "start_time": self.start_time.isoformat() if isinstance(self.start_time, datetime) else self.start_time,
            "end_time": self.end_time.isoformat() if isinstance(self.end_time, datetime) else self.end_time,
            "role": self.role,
            "shift_type": self.shift_type,
            "day_type": self.day_type,
        }
    
    @classmethod
    def from_dict(cls, data: dict, doc_id: Optional[str] = None) -> Assignment:
        """Create Assignment from Firestore document."""
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        
        # Parse datetime if string
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        
        return cls(
            id=doc_id,
            shift_id=data.get("shift_id") or data.get("shiftId"),
            emp_id=data.get("emp_id") or data.get("employeeId"),
            start_time=start_time,
            end_time=end_time,
            role=data.get("role"),
            shift_type=data.get("shift_type"),
            day_type=data.get("day_type"),
        )


@dataclass
class Feedback:
    """Manager feedback for post-shift performance evaluation."""
    
    week_id: str
    date: str  # ISO format: YYYY-MM-DD
    shift_id: int
    emp_id: int
    role: str
    present: bool
    overall_service_rating: int  # 1-5 scale
    traffic_level: str = "normal"  # quiet, normal, busy
    comment: Optional[str] = None
    tags: Optional[str] = None  # Semicolon-separated keywords
    submitted_at: Optional[datetime] = None
    id: Optional[str] = None  # Firestore document ID
    
    def __repr__(self) -> str:
        return f"<Feedback(id={self.id}, emp={self.emp_id}, rating={self.overall_service_rating}, traffic={self.traffic_level})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "week_id": self.week_id,
            "date": self.date,
            "shift_id": self.shift_id,
            "emp_id": self.emp_id,
            "role": self.role,
            "present": self.present,
            "overall_service_rating": self.overall_service_rating,
            "traffic_level": self.traffic_level,
            "comment": self.comment,
            "tags": self.tags,
            "submitted_at": self.submitted_at.isoformat() if isinstance(self.submitted_at, datetime) else self.submitted_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict, doc_id: Optional[str] = None) -> Feedback:
        """Create Feedback from Firestore document."""
        submitted_at = data.get("submitted_at")
        if isinstance(submitted_at, str):
            submitted_at = datetime.fromisoformat(submitted_at)
        
        return cls(
            id=doc_id,
            week_id=data.get("week_id", ""),
            date=data.get("date", ""),
            shift_id=data.get("shift_id"),
            emp_id=data.get("emp_id"),
            role=data.get("role", ""),
            present=data.get("present", True),
            overall_service_rating=data.get("overall_service_rating", 0),
            traffic_level=data.get("traffic_level", "normal"),
            comment=data.get("comment"),
            tags=data.get("tags"),
            submitted_at=submitted_at,
        )

