"""Pydantic v2 request / response models."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AvailabilityType,
    EmployeeColor,
    EmployeeRole,
    ScheduleStatus,
    UserRole,
)
from app.scheduler.models import SundayRuleMode


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users ---------------------------------------------------------
class UserOut(ORMModel):
    id: int
    email: str
    name: str | None = None
    avatar_url: str | None = None
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class AuthStatus(BaseModel):
    authenticated: bool
    user: UserOut | None = None
    login_url: str = "/api/auth/google"
    oauth_configured: bool = True
    dev_auth_enabled: bool = False


# --- employees ------------------------------------------------------------
class EmployeeBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: EmployeeRole
    employment_date: date
    active: bool = True

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Pole nie moze byc puste")
        return cleaned


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: EmployeeRole | None = None
    employment_date: date | None = None
    active: bool | None = None


class EmployeeOut(ORMModel):
    id: int
    first_name: str
    last_name: str
    full_name: str
    role: EmployeeRole
    employment_date: date
    active: bool
    color: EmployeeColor
    seniority_label: str
    created_at: datetime
    updated_at: datetime


# --- shifts ---------------------------------------------------------------
class ShiftOut(ORMModel):
    id: int
    code: str
    name: str
    start_time: time
    end_time: time
    duration_minutes: int
    crosses_midnight: bool
    minimum_staff: int
    active: bool
    sort_order: int


class ShiftUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=24 * 60)
    minimum_staff: int | None = Field(default=None, ge=0, le=50)
    active: bool | None = None


# --- availability ---------------------------------------------------------
class AvailabilityBase(BaseModel):
    employee_id: int
    date: date
    type: AvailabilityType
    note: str | None = Field(default=None, max_length=500)


class AvailabilityCreate(AvailabilityBase):
    pass


class AvailabilityBulkCreate(BaseModel):
    employee_id: int
    dates: list[date] = Field(min_length=1, max_length=400)
    type: AvailabilityType
    note: str | None = Field(default=None, max_length=500)


class AvailabilityUpdate(BaseModel):
    type: AvailabilityType | None = None
    note: str | None = Field(default=None, max_length=500)


class AvailabilityOut(ORMModel):
    id: int
    employee_id: int
    date: date
    type: AvailabilityType
    note: str | None = None


# --- holidays -------------------------------------------------------------
class HolidayOut(ORMModel):
    id: int
    date: date
    name: str
    country: str
    is_custom: bool


class HolidayCreate(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="PL", min_length=2, max_length=2)


# --- schedules ------------------------------------------------------------
class AssignmentOut(ORMModel):
    id: int
    schedule_id: int
    employee_id: int
    shift_id: int
    shift_code: str
    work_date: date
    start_datetime: datetime
    end_datetime: datetime
    manually_modified: bool


class ScheduleOut(ORMModel):
    id: int
    year: int
    month: int
    status: ScheduleStatus
    version: int
    generated_at: datetime | None = None
    approved_at: datetime | None = None
    solver_status: str | None = None
    created_at: datetime
    updated_at: datetime


class DayInfo(BaseModel):
    date: date
    weekday: int
    is_weekend: bool
    is_holiday: bool
    holiday_name: str | None = None


class ScheduleDetail(BaseModel):
    schedule: ScheduleOut | None = None
    year: int
    month: int
    days: list[DayInfo]
    employees: list[EmployeeOut]
    shifts: list[ShiftOut]
    assignments: list[AssignmentOut]
    validation: dict[str, Any] | None = None


class GenerateRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class GenerateResponse(BaseModel):
    success: bool
    schedule: ScheduleOut | None = None
    solver: dict[str, Any]
    validation: dict[str, Any] | None = None


class ValidationResponse(BaseModel):
    schedule: ScheduleOut
    validation: dict[str, Any]


class AssignmentCreate(BaseModel):
    schedule_id: int
    employee_id: int
    work_date: date
    shift_code: str = Field(min_length=1, max_length=4)


class AssignmentUpdate(BaseModel):
    employee_id: int | None = None
    work_date: date | None = None
    shift_code: str | None = Field(default=None, min_length=1, max_length=4)


class EditResponse(BaseModel):
    assignment: AssignmentOut | None = None
    schedule: ScheduleOut
    validation: dict[str, Any]
    new_warnings: list[dict[str, Any]] = Field(default_factory=list)


class ScheduleVersionOut(ORMModel):
    id: int
    schedule_id: int
    version: int
    status: ScheduleStatus
    reason: str
    created_at: datetime
    created_by: int | None = None


class ScheduleVersionDetail(ScheduleVersionOut):
    snapshot: dict[str, Any]
    validation: dict[str, Any] | None = None


# --- settings -------------------------------------------------------------
class DepartmentConfigOut(ORMModel):
    id: int
    facility_name: str
    department_name: str
    weekly_minutes_limit: int
    min_rest_minutes: int
    sunday_free_every_n: int
    sunday_rule_mode: SundayRuleMode
    sunday_cycle_anchor: date
    sunday_includes_saturday_night: bool
    country_code: str
    solver_time_limit_seconds: int
    solver_seed: int
    solver_workers: int
    allow_overstaffing: bool
    weight_night_fairness: int
    weight_weekend_fairness: int
    weight_holiday_fairness: int
    weight_hours_fairness: int
    weight_preferences: int
    weight_preferred_off: int
    weight_coverage_bonus: int


class DepartmentConfigUpdate(BaseModel):
    facility_name: str | None = Field(default=None, min_length=1, max_length=200)
    department_name: str | None = Field(default=None, min_length=1, max_length=200)
    weekly_minutes_limit: int | None = Field(default=None, ge=60, le=7 * 24 * 60)
    min_rest_minutes: int | None = Field(default=None, ge=0, le=48 * 60)
    sunday_free_every_n: int | None = Field(default=None, ge=1, le=52)
    sunday_rule_mode: SundayRuleMode | None = None
    sunday_cycle_anchor: date | None = None
    sunday_includes_saturday_night: bool | None = None
    solver_time_limit_seconds: int | None = Field(default=None, ge=1, le=3600)
    solver_seed: int | None = Field(default=None, ge=0)
    solver_workers: int | None = Field(default=None, ge=1, le=64)
    allow_overstaffing: bool | None = None
    weight_night_fairness: int | None = Field(default=None, ge=0, le=10_000)
    weight_weekend_fairness: int | None = Field(default=None, ge=0, le=10_000)
    weight_holiday_fairness: int | None = Field(default=None, ge=0, le=10_000)
    weight_hours_fairness: int | None = Field(default=None, ge=0, le=10_000)
    weight_preferences: int | None = Field(default=None, ge=0, le=10_000)
    weight_preferred_off: int | None = Field(default=None, ge=0, le=10_000)
    weight_coverage_bonus: int | None = Field(default=None, ge=0, le=10_000)


# --- audit / dashboard ----------------------------------------------------
class AuditLogOut(BaseModel):
    id: int
    user_id: int | None = None
    user_email: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    timestamp: datetime
    metadata: dict[str, Any] | None = None


class DashboardOut(BaseModel):
    facility_name: str
    department_name: str
    current: dict[str, Any] | None = None
    employees_active: int
    employees_total: int
    shifts: list[ShiftOut]
    recent_schedules: list[ScheduleOut]
