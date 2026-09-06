"""SQLAlchemy models. Importing this package registers every table."""
from app.models.audit import AuditLog
from app.models.availability import Availability
from app.models.config import DepartmentConfig
from app.models.employee import Employee
from app.models.enums import (
    AuditAction,
    AvailabilityType,
    EmployeeColor,
    EmployeeRole,
    ScheduleStatus,
    UserRole,
)
from app.models.holiday import Holiday
from app.models.schedule import Assignment, Schedule, ScheduleVersion
from app.models.shift import Shift
from app.models.user import User

__all__ = [
    "AuditAction",
    "AuditLog",
    "Assignment",
    "Availability",
    "AvailabilityType",
    "DepartmentConfig",
    "Employee",
    "EmployeeColor",
    "EmployeeRole",
    "Holiday",
    "Schedule",
    "ScheduleStatus",
    "ScheduleVersion",
    "Shift",
    "User",
    "UserRole",
]
