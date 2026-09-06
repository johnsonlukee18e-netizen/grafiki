"""Plain-data structures used by the solver, the validator and statistics.

Nothing here touches the database: the whole scheduling core is pure Python
so it can be unit-tested without Postgres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum

from app.models.enums import AvailabilityType, EmployeeRole

SHIFT_OFF = "W"


class SundayRuleMode(str, Enum):
    """How "every Nth Sunday off" is interpreted."""

    #: In every window of N consecutive Sundays at least one must be free.
    SLIDING = "SLIDING"
    #: Sundays are grouped into fixed blocks of N counted from the anchor date.
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class ShiftDef:
    id: int
    code: str
    name: str
    start_time: time
    end_time: time
    duration_minutes: int
    crosses_midnight: bool
    minimum_staff: int

    def start_on(self, day: date) -> datetime:
        return datetime.combine(day, self.start_time)

    def end_on(self, day: date) -> datetime:
        end_day = day + timedelta(days=1) if self.crosses_midnight else day
        return datetime.combine(end_day, self.end_time)

    def window(self, day: date) -> tuple[datetime, datetime]:
        return self.start_on(day), self.end_on(day)

    @property
    def is_night(self) -> bool:
        return self.crosses_midnight


@dataclass(frozen=True, slots=True)
class EmployeeCtx:
    id: int
    first_name: str
    last_name: str
    role: EmployeeRole
    employment_date: date
    active: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """Every tunable business rule in one immutable bundle."""

    weekly_minutes_limit: int = 2275  # 37 h 55 min
    min_rest_minutes: int = 660  # 11 h
    sunday_free_every_n: int = 4
    sunday_rule_mode: SundayRuleMode = SundayRuleMode.SLIDING
    sunday_cycle_anchor: date = date(2026, 1, 4)
    #: When true a Saturday night (running into Sunday morning) also
    #: counts as "working that Sunday".
    sunday_includes_saturday_night: bool = False
    solver_time_limit_seconds: int = 60
    solver_seed: int = 42
    #: 1 = fully reproducible run; more workers are faster but the search
    #: order (and therefore the chosen optimum among equals) may vary.
    solver_workers: int = 8
    allow_overstaffing: bool = True
    weight_night_fairness: int = 100
    weight_weekend_fairness: int = 80
    weight_holiday_fairness: int = 60
    weight_hours_fairness: int = 40
    weight_preferences: int = 20
    weight_preferred_off: int = 15
    weight_coverage_bonus: int = 0


@dataclass(frozen=True, slots=True)
class PlannedAssignment:
    """One employee working one shift on one calendar day."""

    employee_id: int
    day: date
    shift_code: str
    manually_modified: bool = False

    def start(self, shifts: dict[str, ShiftDef]) -> datetime:
        return shifts[self.shift_code].start_on(self.day)

    def end(self, shifts: dict[str, ShiftDef]) -> datetime:
        return shifts[self.shift_code].end_on(self.day)


@dataclass
class PlanningContext:
    """Everything the solver / validator needs for one month."""

    year: int
    month: int
    days: list[date]
    employees: list[EmployeeCtx]
    shifts: list[ShiftDef]
    config: RuleConfig
    #: (employee_id, day) -> declared availability
    availability: dict[tuple[int, date], AvailabilityType] = field(default_factory=dict)
    holidays: dict[date, str] = field(default_factory=dict)
    #: Assignments outside the planned month (previous / next month) that are
    #: fixed facts and must be honoured for rest, weekly hours and Sundays.
    boundary: list[PlannedAssignment] = field(default_factory=list)

    # -- lookups ---------------------------------------------------------
    @property
    def shift_by_code(self) -> dict[str, ShiftDef]:
        return {s.code: s for s in self.shifts}

    @property
    def employee_by_id(self) -> dict[int, EmployeeCtx]:
        return {e.id: e for e in self.employees}

    @property
    def first_day(self) -> date:
        return self.days[0]

    @property
    def last_day(self) -> date:
        return self.days[-1]

    def availability_of(self, employee_id: int, day: date) -> AvailabilityType:
        return self.availability.get((employee_id, day), AvailabilityType.AVAILABLE)

    def is_unavailable(self, employee_id: int, day: date) -> bool:
        return self.availability_of(employee_id, day) is AvailabilityType.UNAVAILABLE

    def is_employed(self, employee: EmployeeCtx, day: date) -> bool:
        return employee.employment_date <= day

    def can_work(self, employee: EmployeeCtx, day: date) -> bool:
        return (
            employee.active
            and self.is_employed(employee, day)
            and not self.is_unavailable(employee.id, day)
        )

    def is_holiday(self, day: date) -> bool:
        return day in self.holidays


@dataclass(frozen=True, slots=True)
class Violation:
    """A single rule breach reported by the validator."""

    code: str
    severity: str  # "error" | "warning"
    message: str
    employee_id: int | None = None
    employee_name: str | None = None
    day: date | None = None
    shift_code: str | None = None
    details: dict | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "date": self.day.isoformat() if self.day else None,
            "shift_code": self.shift_code,
            "details": self.details or {},
        }
