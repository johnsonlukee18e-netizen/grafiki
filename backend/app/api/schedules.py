"""Schedule endpoints: read, generate, validate, approve, history, PDF."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_manager
from app.api.employees import to_out as employee_out
from app.models import (
    Assignment,
    AuditAction,
    Employee,
    Schedule,
    ScheduleVersion,
    Shift,
    User,
)
from app.schemas import (
    AssignmentOut,
    CellsResponse,
    CellsUpdate,
    DayInfo,
    GenerateRequest,
    GenerateResponse,
    ManualStartRequest,
    RestoreResponse,
    ScheduleDetail,
    ScheduleOut,
    ScheduleVersionDetail,
    ScheduleVersionOut,
    ShiftOut,
    ValidationResponse,
)
from app.services import audit_service, planning, schedule_service
from app.services.pdf_service import render_employee_pdf, render_schedule_pdf
from app.services.schedule_service import ScheduleError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _handle(error: ScheduleError) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail={"message": error.message, **error.details},
    )


def attachment_header(filename: str) -> str:
    """``Content-Disposition`` that survives non-ASCII names.

    HTTP headers are Latin-1, so ``kowalczyk_michał.pdf`` used to crash the
    response with a UnicodeEncodeError (500). Send an ASCII fallback plus the
    RFC 5987 UTF-8 form that every current browser prefers.
    """
    folded = unicodedata.normalize("NFKD", filename.replace("ł", "l").replace("Ł", "L"))
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("_") or "grafik.pdf"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def assignment_out(assignment: Assignment, code: str) -> AssignmentOut:
    return AssignmentOut(
        id=assignment.id,
        schedule_id=assignment.schedule_id,
        employee_id=assignment.employee_id,
        shift_id=assignment.shift_id,
        shift_code=code,
        work_date=assignment.work_date,
        start_datetime=assignment.start_datetime,
        end_datetime=assignment.end_datetime,
        manually_modified=assignment.manually_modified,
    )


def load_assignment_rows(db: Session, schedule_id: int) -> list[AssignmentOut]:
    rows = db.execute(
        select(Assignment, Shift.code)
        .join(Shift, Assignment.shift_id == Shift.id)
        .where(Assignment.schedule_id == schedule_id)
        .order_by(Assignment.work_date, Assignment.employee_id)
    ).all()
    return [assignment_out(assignment, code) for assignment, code in rows]


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    limit: int = Query(default=24, ge=1, le=200),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[Schedule]:
    return list(
        db.scalars(
            select(Schedule).order_by(Schedule.year.desc(), Schedule.month.desc()).limit(limit)
        )
    )


@router.post("/generate", response_model=GenerateResponse)
def generate_schedule(
    payload: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> GenerateResponse:
    """Run OR-Tools for the chosen month and validate the result."""
    try:
        schedule, result, validation = schedule_service.generate_schedule(
            db, payload.year, payload.month, user
        )
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return GenerateResponse(
        success=result.success,
        schedule=ScheduleOut.model_validate(schedule),
        solver=result.as_dict(),
        validation=validation.as_dict() if validation else None,
    )


@router.post("/manual", response_model=ScheduleOut)
def start_manual_building(
    payload: ManualStartRequest,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> Schedule:
    """RECZNE UKLADANIE: put a month into manual mode (no generation)."""
    try:
        schedule = schedule_service.start_manual(db, payload.year, payload.month, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return schedule


@router.put("/{schedule_id}/cells", response_model=CellsResponse)
def set_cells(
    schedule_id: int,
    payload: CellsUpdate,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> CellsResponse:
    """Set grid cells freely; the rules are checked on "send for checking"."""
    schedule = _require_schedule(db, schedule_id)
    cells = [
        schedule_service.CellChange(c.employee_id, c.date, c.shift_code) for c in payload.cells
    ]
    try:
        changed = schedule_service.set_cells(db, schedule, cells, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return CellsResponse(schedule=ScheduleOut.model_validate(schedule), changed=changed)


def _require_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono grafiku.")
    return schedule


@router.post("/{schedule_id}/validate", response_model=ValidationResponse)
def validate_schedule(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> ValidationResponse:
    schedule = _require_schedule(db, schedule_id)
    result = schedule_service.run_validation(db, schedule)
    audit_service.record(
        db,
        AuditAction.SCHEDULE_VALIDATED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={"valid": result.valid, "errors": len(result.errors)},
    )
    db.commit()
    db.refresh(schedule)
    return ValidationResponse(
        schedule=ScheduleOut.model_validate(schedule), validation=result.as_dict()
    )


@router.post("/{schedule_id}/approve", response_model=ValidationResponse)
def approve_schedule(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> ValidationResponse:
    schedule = _require_schedule(db, schedule_id)
    try:
        result = schedule_service.approve(db, schedule, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return ValidationResponse(
        schedule=ScheduleOut.model_validate(schedule), validation=result.as_dict()
    )


@router.post("/{schedule_id}/unapprove", response_model=ScheduleOut)
def unapprove_schedule(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> Schedule:
    schedule = _require_schedule(db, schedule_id)
    try:
        schedule_service.unapprove(db, schedule, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/{schedule_id}/history", response_model=list[ScheduleVersionOut])
def schedule_history(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[ScheduleVersion]:
    _require_schedule(db, schedule_id)
    return list(
        db.scalars(
            select(ScheduleVersion)
            .where(ScheduleVersion.schedule_id == schedule_id)
            .order_by(ScheduleVersion.version.desc())
        )
    )


@router.get("/{schedule_id}/history/{version}", response_model=ScheduleVersionDetail)
def schedule_version(
    schedule_id: int,
    version: int,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> ScheduleVersion:
    row = db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.schedule_id == schedule_id, ScheduleVersion.version == version
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono tej wersji grafiku.")
    return row


@router.post("/{schedule_id}/history/{version}/restore", response_model=RestoreResponse)
def restore_schedule_version(
    schedule_id: int,
    version: int,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> RestoreResponse:
    """Make an older version the current roster again (as a new version)."""
    schedule = _require_schedule(db, schedule_id)
    try:
        result, skipped = schedule_service.restore_version(db, schedule, version, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    db.refresh(schedule)
    return RestoreResponse(
        schedule=ScheduleOut.model_validate(schedule),
        validation=result.as_dict(),
        skipped=skipped,
    )


@router.get("/{schedule_id}/statistics")
def schedule_statistics(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> dict:
    schedule = _require_schedule(db, schedule_id)
    result = schedule_service.current_validation(db, schedule)
    db.commit()
    return result.statistics


@router.get("/{schedule_id}/pdf")
def schedule_pdf(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> Response:
    schedule = _require_schedule(db, schedule_id)
    pdf = render_schedule_pdf(db, schedule)
    audit_service.record(
        db,
        AuditAction.PDF_EXPORTED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={"scope": "department", "version": schedule.version},
        ip_address=client_ip(request),
    )
    db.commit()
    filename = f"grafik_{schedule.year}_{schedule.month:02d}_v{schedule.version}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": attachment_header(filename)},
    )


@router.get("/{schedule_id}/employee/{employee_id}/pdf")
def employee_pdf(
    schedule_id: int,
    employee_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> Response:
    schedule = _require_schedule(db, schedule_id)
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono pracownika.")
    pdf = render_employee_pdf(db, schedule, employee)
    audit_service.record(
        db,
        AuditAction.PDF_EXPORTED,
        user=user,
        entity_type="schedule",
        entity_id=schedule.id,
        metadata={"scope": "employee", "employee_id": employee_id},
        ip_address=client_ip(request),
    )
    db.commit()
    filename = (
        f"grafik_{schedule.year}_{schedule.month:02d}_"
        f"{employee.last_name.lower()}_{employee.first_name.lower()}.pdf"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": attachment_header(filename)},
    )


@router.get("/{year}/{month}", response_model=ScheduleDetail)
def get_month(
    year: int = Path(ge=2000, le=2100),
    month: int = Path(ge=1, le=12),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> ScheduleDetail:
    """The month grid: days, employees, shifts, assignments and validation."""
    schedule = schedule_service.get_schedule(db, year, month)
    ctx = planning.build_context(
        db,
        year,
        month,
        employees=(
            planning.employees_for_schedule(db, schedule)
            if schedule
            else planning.active_employees(db)
        ),
        exclude_schedule_id=schedule.id if schedule else None,
    )
    validation = schedule.validation if schedule else None
    if schedule is not None and schedule.validation is not None:
        # The cached report goes stale when availability, employees, settings
        # or the neighbouring months change - always show the current truth.
        validation = schedule_service.current_validation(db, schedule, ctx).as_dict()
    db.commit()

    employees = (
        planning.employees_for_schedule(db, schedule)
        if schedule
        else planning.active_employees(db)
    )
    days = [
        DayInfo(
            date=day,
            weekday=day.weekday(),
            is_weekend=day.weekday() >= 5,
            is_holiday=ctx.is_holiday(day),
            holiday_name=ctx.holidays.get(day),
        )
        for day in ctx.days
    ]
    return ScheduleDetail(
        schedule=ScheduleOut.model_validate(schedule) if schedule else None,
        year=year,
        month=month,
        days=days,
        employees=[employee_out(e, date(year, month, 1)) for e in employees],
        shifts=[ShiftOut.model_validate(s) for s in planning.active_shifts(db)],
        assignments=load_assignment_rows(db, schedule.id) if schedule else [],
        validation=validation,
    )
