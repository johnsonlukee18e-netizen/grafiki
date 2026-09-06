"""Schedule lifecycle: generate -> validate -> edit -> validate -> approve.

Manual edits are applied optimistically and rolled back when they introduce a
HARD constraint violation, exactly as the workflow in the specification
requires. Pre-existing problems never block an unrelated edit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AuditAction,
    Employee,
    Schedule,
    ScheduleStatus,
    ScheduleVersion,
    Shift,
    User,
)
from app.scheduler.models import PlannedAssignment, PlanningContext
from app.scheduler.solver import GenerationResult, generate
from app.scheduler.validator import ValidationResult, validate
from app.services import audit_service, planning

logger = logging.getLogger(__name__)


class ScheduleError(Exception):
    """Business rule violation that must be surfaced to the manager."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None, status: int = 409):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.status = status


@dataclass
class EditOutcome:
    """Result of a manual edit that passed the hard-constraint gate."""

    schedule: Schedule
    validation: ValidationResult
    new_warnings: list[dict[str, Any]]
    assignment_id: int | None = None


# --- lookups --------------------------------------------------------------
def get_schedule(db: Session, year: int, month: int) -> Schedule | None:
    return db.scalar(select(Schedule).where(Schedule.year == year, Schedule.month == month))


def get_or_create(db: Session, year: int, month: int, user: User | None = None) -> Schedule:
    schedule = get_schedule(db, year, month)
    if schedule is None:
        schedule = Schedule(
            year=year,
            month=month,
            status=ScheduleStatus.DRAFT,
            version=1,
            created_by=user.id if user else None,
        )
        db.add(schedule)
        db.flush()
    return schedule


def require_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise ScheduleError("Nie znaleziono grafiku.", status=404)
    return schedule


def shift_by_code(db: Session) -> dict[str, Shift]:
    return {s.code: s for s in planning.active_shifts(db)}


# --- versioning -----------------------------------------------------------
def snapshot(db: Session, schedule: Schedule, reason: str, user: User | None = None) -> ScheduleVersion:
    """Store the current state before it is replaced. History is never deleted."""
    rows = db.execute(
        select(Assignment, Shift.code)
        .join(Shift, Assignment.shift_id == Shift.id)
        .where(Assignment.schedule_id == schedule.id)
        .order_by(Assignment.work_date, Assignment.employee_id)
    ).all()
    payload = {
        "assignments": [
            {
                "employee_id": assignment.employee_id,
                "date": assignment.work_date.isoformat(),
                "shift_code": code,
                "manually_modified": assignment.manually_modified,
            }
            for assignment, code in rows
        ]
    }
    version = ScheduleVersion(
        schedule_id=schedule.id,
        version=schedule.version,
        status=schedule.status,
        reason=reason,
        created_by=user.id if user else None,
        snapshot=payload,
        validation=schedule.validation,
    )
    db.add(version)
    db.flush()
    return version


def _bump_version(db: Session, schedule: Schedule, reason: str, user: User | None) -> None:
    snapshot(db, schedule, reason, user)
    schedule.version += 1


# --- validation -----------------------------------------------------------
def build_context_for(db: Session, schedule: Schedule) -> PlanningContext:
    return planning.build_context(
        db,
        schedule.year,
        schedule.month,
        employees=planning.employees_for_schedule(db, schedule),
        exclude_schedule_id=schedule.id,
    )


def run_validation(
    db: Session, schedule: Schedule, ctx: PlanningContext | None = None
) -> ValidationResult:
    """Validate and persist the outcome, updating the schedule status."""
    context = ctx or build_context_for(db, schedule)
    assignments = planning.load_assignments(db, schedule.id)
    result = validate(context, assignments)
    schedule.validation = result.as_dict()
    if schedule.status not in (ScheduleStatus.APPROVED, ScheduleStatus.ARCHIVED):
        schedule.status = ScheduleStatus.VALID if result.valid else ScheduleStatus.INVALID
    elif schedule.status is ScheduleStatus.APPROVED and not result.valid:
        # An approved schedule that becomes invalid (e.g. an employee was
        # deactivated) must not keep pretending it is fine.
        schedule.status = ScheduleStatus.INVALID
        schedule.approved_at = None
    db.flush()
    return result


# --- generation -----------------------------------------------------------
def generate_schedule(
    db: Session,
    year: int,
    month: int,
    user: User | None = None,
) -> tuple[Schedule, GenerationResult, ValidationResult | None]:
    """Run OR-Tools, store the roster and validate it independently."""
    schedule = get_or_create(db, year, month, user)
    if schedule.status is ScheduleStatus.APPROVED:
        raise ScheduleError(
            "Grafik jest juz zatwierdzony. Cofnij zatwierdzenie, aby wygenerowac go ponownie."
        )

    ctx = build_context_for(db, schedule)
    if not ctx.shifts:
        raise ScheduleError(
            "Nie zdefiniowano zadnych aktywnych zmian. Uzupelnij USTAWIENIA.", status=400
        )

    schedule.status = ScheduleStatus.GENERATING
    db.flush()

    result = generate(ctx)
    if not result.success:
        schedule.status = ScheduleStatus.INVALID
        schedule.solver_status = result.status
        db.flush()
        audit_service.record(
            db,
            AuditAction.SCHEDULE_GENERATED,
            user=user,
            entity_type="schedule",
            entity_id=schedule.id,
            metadata={"success": False, "status": result.status},
        )
        return schedule, result, None

    if db.scalar(select(Assignment.id).where(Assignment.schedule_id == schedule.id).limit(1)):
        _bump_version(db, schedule, "Ponowne wygenerowanie grafiku", user)

    replace_assignments(db, schedule, result.assignments)
    schedule.status = ScheduleStatus.GENERATED
    schedule.generated_at = datetime.now(UTC)
    schedule.solver_status = result.status
    db.flush()

    validation = run_validation(db, schedule, ctx)
    audit_service.record(
        db,
        AuditAction.SCHEDULE_GENERATED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={
            "success": True,
            "status": result.status,
            "objective": result.objective,
            "assignments": len(result.assignments),
            "valid": validation.valid,
            "version": schedule.version,
        },
    )
    return schedule, result, validation


def replace_assignments(
    db: Session, schedule: Schedule, assignments: list[PlannedAssignment]
) -> None:
    """Swap the whole roster of a schedule (history lives in versions)."""
    shifts = shift_by_code(db)
    db.execute(delete(Assignment).where(Assignment.schedule_id == schedule.id))
    db.flush()
    for item in assignments:
        shift = shifts.get(item.shift_code)
        if shift is None:
            continue
        db.add(_build_assignment(schedule, item.employee_id, shift, item.day, manual=False))
    db.flush()


def _build_assignment(
    schedule: Schedule, employee_id: int, shift: Shift, work_date: date, *, manual: bool
) -> Assignment:
    from app.services.planning import to_shift_def

    definition = to_shift_def(shift)
    start, end = definition.window(work_date)
    return Assignment(
        schedule_id=schedule.id,
        employee_id=employee_id,
        shift_id=shift.id,
        work_date=work_date,
        start_datetime=start,
        end_datetime=end,
        manually_modified=manual,
    )


# --- manual editing -------------------------------------------------------
def _violation_key(item: dict[str, Any]) -> tuple:
    return (item["code"], item.get("employee_id"), item.get("date"), item.get("shift_code"))


def apply_manual_change(
    db: Session,
    schedule: Schedule,
    mutate,
    *,
    reason: str,
    user: User | None,
    audit_action: AuditAction,
    audit_metadata: dict[str, Any],
) -> EditOutcome:
    """Apply ``mutate`` and keep it only if no new HARD violation appears.

    ``mutate(db, schedule, shifts) -> int | None`` performs the change and may
    return the id of the affected assignment.
    """
    if schedule.status is ScheduleStatus.APPROVED:
        raise ScheduleError(
            "Grafik jest zatwierdzony i nie mozna go edytowac. Cofnij zatwierdzenie."
        )
    if schedule.status is ScheduleStatus.ARCHIVED:
        raise ScheduleError("Grafik jest zarchiwizowany i tylko do odczytu.")

    ctx = build_context_for(db, schedule)
    before = validate(ctx, planning.load_assignments(db, schedule.id))
    before_errors = {_violation_key(e) for e in before.as_dict()["errors"]}
    before_warnings = {_violation_key(w) for w in before.as_dict()["warnings"]}

    savepoint = db.begin_nested()
    try:
        assignment_id = mutate(db, schedule, shift_by_code(db))
        db.flush()
    except ScheduleError:
        savepoint.rollback()
        raise
    except Exception:
        savepoint.rollback()
        raise

    after = validate(ctx, planning.load_assignments(db, schedule.id))
    after_dict = after.as_dict()
    new_errors = [e for e in after_dict["errors"] if _violation_key(e) not in before_errors]
    if new_errors:
        savepoint.rollback()
        raise ScheduleError(
            "Nie mozna wykonac operacji - zlamalaby twarde ograniczenie grafiku.",
            details={"errors": new_errors},
        )
    savepoint.commit()

    new_warnings = [w for w in after_dict["warnings"] if _violation_key(w) not in before_warnings]
    _bump_version(db, schedule, reason, user)
    schedule.validation = after_dict
    if schedule.status not in (ScheduleStatus.APPROVED, ScheduleStatus.ARCHIVED):
        schedule.status = ScheduleStatus.VALID if after.valid else ScheduleStatus.INVALID
    db.flush()

    audit_service.record(
        db,
        audit_action,
        user=user,
        entity_type="assignment",
        entity_id=assignment_id,
        metadata={**audit_metadata, "schedule_id": schedule.id, "version": schedule.version},
    )
    return EditOutcome(
        schedule=schedule,
        validation=after,
        new_warnings=new_warnings,
        assignment_id=assignment_id,
    )


def _require_employee(db: Session, employee_id: int) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise ScheduleError("Nie znaleziono pracownika.", status=404)
    return employee


def create_assignment(
    db: Session,
    schedule: Schedule,
    employee_id: int,
    work_date: date,
    shift_code: str,
    user: User | None,
) -> EditOutcome:
    _require_employee(db, employee_id)
    _require_in_month(schedule, work_date)

    def mutate(session: Session, sched: Schedule, shifts: dict[str, Shift]) -> int:
        shift = shifts.get(shift_code)
        if shift is None:
            raise ScheduleError(f"Nieznana zmiana '{shift_code}'.", status=400)
        existing = session.scalar(
            select(Assignment).where(
                Assignment.employee_id == employee_id,
                Assignment.work_date == work_date,
            )
        )
        if existing is not None:
            raise ScheduleError(
                "Pracownik ma juz zmiane tego dnia. Zmien istniejaca zmiane zamiast dodawac nowa."
            )
        assignment = _build_assignment(sched, employee_id, shift, work_date, manual=True)
        session.add(assignment)
        session.flush()
        return assignment.id

    return apply_manual_change(
        db,
        schedule,
        mutate,
        reason=f"Dodanie zmiany {shift_code} ({work_date.isoformat()})",
        user=user,
        audit_action=AuditAction.ASSIGNMENT_CREATED,
        audit_metadata={
            "employee_id": employee_id,
            "date": work_date.isoformat(),
            "shift_code": shift_code,
        },
    )


def update_assignment(
    db: Session,
    assignment_id: int,
    *,
    shift_code: str | None,
    work_date: date | None,
    employee_id: int | None,
    user: User | None,
) -> EditOutcome:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise ScheduleError("Nie znaleziono przypisania.", status=404)
    schedule = require_schedule(db, assignment.schedule_id)
    target_date = work_date or assignment.work_date
    _require_in_month(schedule, target_date)
    previous = {
        "employee_id": assignment.employee_id,
        "date": assignment.work_date.isoformat(),
        "shift_id": assignment.shift_id,
    }
    moved = work_date is not None and work_date != assignment.work_date

    def mutate(session: Session, sched: Schedule, shifts: dict[str, Shift]) -> int:
        row = session.get(Assignment, assignment_id)
        if row is None:  # pragma: no cover - defensive
            raise ScheduleError("Nie znaleziono przypisania.", status=404)
        if employee_id is not None:
            _require_employee(session, employee_id)
            row.employee_id = employee_id
        if shift_code is not None:
            shift = shifts.get(shift_code)
            if shift is None:
                raise ScheduleError(f"Nieznana zmiana '{shift_code}'.", status=400)
            row.shift_id = shift.id
        if work_date is not None:
            row.work_date = work_date
        clash = session.scalar(
            select(Assignment).where(
                Assignment.employee_id == row.employee_id,
                Assignment.work_date == row.work_date,
                Assignment.id != row.id,
            )
        )
        if clash is not None:
            raise ScheduleError(
                "Pracownik ma juz inna zmiane tego dnia - najpierw zwolnij ten dzien."
            )
        shift = session.get(Shift, row.shift_id)
        from app.services.planning import to_shift_def

        row.start_datetime, row.end_datetime = to_shift_def(shift).window(row.work_date)
        row.manually_modified = True
        session.flush()
        return row.id

    return apply_manual_change(
        db,
        schedule,
        mutate,
        reason=f"Reczna zmiana przypisania #{assignment_id}",
        user=user,
        audit_action=AuditAction.ASSIGNMENT_MOVED if moved else AuditAction.ASSIGNMENT_UPDATED,
        audit_metadata={
            "assignment_id": assignment_id,
            "previous": previous,
            "new": {
                "employee_id": employee_id,
                "date": target_date.isoformat(),
                "shift_code": shift_code,
            },
        },
    )


def delete_assignment(db: Session, assignment_id: int, user: User | None) -> EditOutcome:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise ScheduleError("Nie znaleziono przypisania.", status=404)
    schedule = require_schedule(db, assignment.schedule_id)
    details = {
        "employee_id": assignment.employee_id,
        "date": assignment.work_date.isoformat(),
        "shift_id": assignment.shift_id,
    }

    def mutate(session: Session, sched: Schedule, shifts: dict[str, Shift]) -> None:
        row = session.get(Assignment, assignment_id)
        if row is not None:
            session.delete(row)
            session.flush()
        return None

    return apply_manual_change(
        db,
        schedule,
        mutate,
        reason=f"Usuniecie zmiany ({details['date']})",
        user=user,
        audit_action=AuditAction.ASSIGNMENT_DELETED,
        audit_metadata=details,
    )


def _require_in_month(schedule: Schedule, work_date: date) -> None:
    if work_date.year != schedule.year or work_date.month != schedule.month:
        raise ScheduleError(
            "Data spoza miesiaca grafiku. Edytuj grafik wlasciwego miesiaca.", status=400
        )


# --- approval -------------------------------------------------------------
def approve(db: Session, schedule: Schedule, user: User | None) -> ValidationResult:
    """Approve, but never an invalid schedule."""
    if schedule.status is ScheduleStatus.APPROVED:
        raise ScheduleError("Grafik jest juz zatwierdzony.")
    if schedule.status is ScheduleStatus.ARCHIVED:
        raise ScheduleError("Grafik jest zarchiwizowany.")
    result = run_validation(db, schedule)
    if not result.valid:
        raise ScheduleError(
            "Nie mozna zatwierdzic grafiku z bledami twardych ograniczen. "
            "Popraw bledy wskazane w panelu walidacji.",
            details={"errors": result.as_dict()["errors"]},
        )
    if db.scalar(select(Assignment.id).where(Assignment.schedule_id == schedule.id).limit(1)) is None:
        raise ScheduleError("Grafik jest pusty - nie ma czego zatwierdzac.")

    _bump_version(db, schedule, "Zatwierdzenie grafiku", user)
    schedule.status = ScheduleStatus.APPROVED
    schedule.approved_at = datetime.now(UTC)
    schedule.approved_by = user.id if user else None
    db.flush()
    audit_service.record(
        db,
        AuditAction.SCHEDULE_APPROVED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={"version": schedule.version},
    )
    return result


def unapprove(db: Session, schedule: Schedule, user: User | None) -> Schedule:
    if schedule.status is not ScheduleStatus.APPROVED:
        raise ScheduleError("Grafik nie jest zatwierdzony.")
    _bump_version(db, schedule, "Cofniecie zatwierdzenia", user)
    schedule.status = ScheduleStatus.VALID
    schedule.approved_at = None
    schedule.approved_by = None
    db.flush()
    audit_service.record(
        db,
        AuditAction.SCHEDULE_APPROVED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={"unapproved": True, "version": schedule.version},
    )
    return schedule
