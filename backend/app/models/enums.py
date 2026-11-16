"""Domain enumerations shared by models, schemas and the scheduler."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"


class EmployeeRole(str, enum.Enum):
    NURSE = "NURSE"
    CARE_WORKER = "CARE_WORKER"


class EmployeeColor(str, enum.Enum):
    """Seniority colour - always derived, never set by hand."""

    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    PURPLE = "PURPLE"


class AvailabilityType(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PREFERRED_DAY = "PREFERRED_DAY"
    PREFERRED_MORNING = "PREFERRED_MORNING"
    PREFERRED_NIGHT = "PREFERRED_NIGHT"
    PREFERRED_OFF = "PREFERRED_OFF"

    @property
    def is_hard(self) -> bool:
        return self is AvailabilityType.UNAVAILABLE


class ScheduleStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    VALID = "VALID"
    INVALID = "INVALID"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED"
    EMPLOYEE_UPDATED = "EMPLOYEE_UPDATED"
    EMPLOYEE_DEACTIVATED = "EMPLOYEE_DEACTIVATED"
    AVAILABILITY_CHANGED = "AVAILABILITY_CHANGED"
    SCHEDULE_GENERATED = "SCHEDULE_GENERATED"
    SCHEDULE_VALIDATED = "SCHEDULE_VALIDATED"
    SCHEDULE_APPROVED = "SCHEDULE_APPROVED"
    SCHEDULE_RESTORED = "SCHEDULE_RESTORED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_MOVED = "ASSIGNMENT_MOVED"
    ASSIGNMENT_UPDATED = "ASSIGNMENT_UPDATED"
    ASSIGNMENT_DELETED = "ASSIGNMENT_DELETED"
    PDF_EXPORTED = "PDF_EXPORTED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_ACTIVATION_CHANGED = "USER_ACTIVATION_CHANGED"
    HOLIDAYS_IMPORTED = "HOLIDAYS_IMPORTED"


#: Canonical shift codes. "W" (day off) is the absence of an assignment and is
#: therefore never stored as a row - it only exists in presentation layers.
SHIFT_CODE_DAY = "D"
SHIFT_CODE_MORNING = "R"
SHIFT_CODE_NIGHT = "N"
SHIFT_CODE_OFF = "W"
