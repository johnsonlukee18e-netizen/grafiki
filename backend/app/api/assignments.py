"""Manual roster edits. Every change is re-validated before it is kept."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_manager
from app.api.schedules import assignment_out
from app.models import Assignment, Shift, User
from app.schemas import AssignmentCreate, AssignmentUpdate, EditResponse, ScheduleOut
from app.services import schedule_service
from app.services.schedule_service import EditOutcome, ScheduleError

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _handle(error: ScheduleError) -> HTTPException:
    return HTTPException(
        status_code=error.status, detail={"message": error.message, **error.details}
    )


def _response(db: Session, outcome: EditOutcome) -> EditResponse:
    assignment = None
    if outcome.assignment_id is not None:
        row = db.execute(
            select(Assignment, Shift.code)
            .join(Shift, Assignment.shift_id == Shift.id)
            .where(Assignment.id == outcome.assignment_id)
        ).first()
        if row is not None:
            assignment = assignment_out(row[0], row[1])
    return EditResponse(
        assignment=assignment,
        schedule=ScheduleOut.model_validate(outcome.schedule),
        validation=outcome.validation.as_dict(),
        new_warnings=outcome.new_warnings,
    )


@router.post("", response_model=EditResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EditResponse:
    schedule = schedule_service.require_schedule(db, payload.schedule_id)
    try:
        outcome = schedule_service.create_assignment(
            db, schedule, payload.employee_id, payload.work_date, payload.shift_code, user
        )
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    return _response(db, outcome)


@router.put("/{assignment_id}", response_model=EditResponse)
def update_assignment(
    assignment_id: int,
    payload: AssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EditResponse:
    try:
        outcome = schedule_service.update_assignment(
            db,
            assignment_id,
            shift_code=payload.shift_code,
            work_date=payload.work_date,
            employee_id=payload.employee_id,
            user=user,
        )
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    return _response(db, outcome)


@router.delete("/{assignment_id}", response_model=EditResponse)
def delete_assignment(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> EditResponse:
    try:
        outcome = schedule_service.delete_assignment(db, assignment_id, user)
    except ScheduleError as exc:
        db.rollback()
        raise _handle(exc) from exc
    db.commit()
    return _response(db, outcome)
