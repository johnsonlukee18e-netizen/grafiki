"""Bridge between the database and the pure scheduling core.

Builds a :class:`PlanningContext` for one month, pulling in everything the
specification demands: employees, availability, shifts, holidays, department
configuration and - crucially - the assignments of the neighbouring months so
that weeks, rest periods and the Sunday cycle never restart at a month border.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    Availability,
    DepartmentConfig,
    Employee,
    Holiday,
    Schedule,
    Shift,
)
from app.scheduler.models import (
    EmployeeCtx,
    PlannedAssignment,
    PlanningContext,
    RuleConfig,
    ShiftDef,
)
from app.services.config_service import get_config, to_rule_config
from app.services.holiday_service import ensure_holidays_for_year


#: How far outside the month we must look. The Sunday cycle needs N-1 weeks,
#: rest/night rules need a couple of days; we take the widest of the two.
def lookaround_days(config: RuleConfig) -> int:
    return max(7 * config.sunday_free_every_n, 7)


def month_days(year: int, month: int) -> list[date]:
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, last + 1)]


def to_shift_def(shift: Shift) -> ShiftDef:
    return ShiftDef(
        id=shift.id,
        code=shift.code,
        name=shift.name,
        start_time=shift.start_time,
        end_time=shift.end_time,
        duration_minutes=shift.duration_minutes,
        crosses_midnight=shift.crosses_midnight,
        minimum_staff=shift.minimum_staff,
    )


def to_employee_ctx(employee: Employee) -> EmployeeCtx:
    return EmployeeCtx(
        id=employee.id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        role=employee.role,
        employment_date=employee.employment_date,
        active=employee.active,
    )


def active_shifts(db: Session) -> list[Shift]:
    return list(
        db.scalars(select(Shift).where(Shift.active.is_(True)).order_by(Shift.sort_order, Shift.id))
    )


def active_employees(db: Session) -> list[Employee]:
    return list(
        db.scalars(
            select(Employee)
            .where(Employee.active.is_(True))
            .order_by(Employee.last_name, Employee.first_name)
        )
    )


def build_context(
    db: Session,
    year: int,
    month: int,
    *,
    employees: list[Employee] | None = None,
    exclude_schedule_id: int | None = None,
    config: DepartmentConfig | None = None,
) -> PlanningContext:
    """Assemble everything needed to generate or validate ``year``-``month``."""
    department = config or get_config(db)
    rule_config = to_rule_config(department)
    days = month_days(year, month)
    shifts = [to_shift_def(s) for s in active_shifts(db)]
    people = employees if employees is not None else active_employees(db)
    employee_ctx = [to_employee_ctx(e) for e in people]
    employee_ids = [e.id for e in employee_ctx]

    span = timedelta(days=lookaround_days(rule_config))
    window_start, window_end = days[0] - span, days[-1] + span

    availability = {
        (row.employee_id, row.day): row.type
        for row in db.scalars(
            select(Availability).where(
                Availability.employee_id.in_(employee_ids or [0]),
                Availability.day >= days[0],
                Availability.day <= days[-1],
            )
        )
    }

    ensure_holidays_for_year(db, days[0].year, country=department.country_code)
    if days[-1].year != days[0].year:  # pragma: no cover - defensive
        ensure_holidays_for_year(db, days[-1].year, country=department.country_code)
    holidays = {
        row.day: row.name
        for row in db.scalars(
            select(Holiday).where(
                Holiday.country == department.country_code,
                Holiday.day >= days[0],
                Holiday.day <= days[-1],
            )
        )
    }

    boundary = load_boundary_assignments(
        db,
        window_start=window_start,
        window_end=window_end,
        month_start=days[0],
        month_end=days[-1],
        employee_ids=employee_ids,
        exclude_schedule_id=exclude_schedule_id,
    )

    return PlanningContext(
        year=year,
        month=month,
        days=days,
        employees=employee_ctx,
        shifts=shifts,
        config=rule_config,
        availability=availability,
        holidays=holidays,
        boundary=boundary,
    )


def load_boundary_assignments(
    db: Session,
    *,
    window_start: date,
    window_end: date,
    month_start: date,
    month_end: date,
    employee_ids: list[int],
    exclude_schedule_id: int | None = None,
) -> list[PlannedAssignment]:
    """Assignments from the neighbouring months - immutable facts for this run."""
    if not employee_ids:
        return []
    query = (
        select(Assignment, Shift.code)
        .join(Shift, Assignment.shift_id == Shift.id)
        .where(
            Assignment.employee_id.in_(employee_ids),
            Assignment.work_date >= window_start,
            Assignment.work_date <= window_end,
            (Assignment.work_date < month_start) | (Assignment.work_date > month_end),
        )
    )
    if exclude_schedule_id is not None:
        query = query.where(Assignment.schedule_id != exclude_schedule_id)
    return [
        PlannedAssignment(
            employee_id=assignment.employee_id,
            day=assignment.work_date,
            shift_code=code,
            manually_modified=assignment.manually_modified,
        )
        for assignment, code in db.execute(query).all()
    ]


def load_assignments(db: Session, schedule_id: int) -> list[PlannedAssignment]:
    """Current in-month assignments of a schedule as planning objects."""
    rows = db.execute(
        select(Assignment, Shift.code)
        .join(Shift, Assignment.shift_id == Shift.id)
        .where(Assignment.schedule_id == schedule_id)
        .order_by(Assignment.work_date, Assignment.employee_id)
    ).all()
    return [
        PlannedAssignment(
            employee_id=assignment.employee_id,
            day=assignment.work_date,
            shift_code=code,
            manually_modified=assignment.manually_modified,
        )
        for assignment, code in rows
    ]


def employees_for_schedule(db: Session, schedule: Schedule) -> list[Employee]:
    """Active employees plus anyone already rostered (even if deactivated later).

    Without this an employee deactivated mid-month would silently vanish from
    the validation of an existing schedule.
    """
    active = {e.id: e for e in active_employees(db)}
    rostered = db.scalars(
        select(Employee)
        .join(Assignment, Assignment.employee_id == Employee.id)
        .where(Assignment.schedule_id == schedule.id)
    )
    for employee in rostered:
        active.setdefault(employee.id, employee)
    return sorted(active.values(), key=lambda e: (e.last_name, e.first_name))
