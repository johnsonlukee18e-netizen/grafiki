"""Dashboard summary shown right after login."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_manager
from app.models import Assignment, Employee, Schedule, Shift, User
from app.schemas import DashboardOut, ScheduleOut, ShiftOut
from app.services import schedule_service
from app.services.config_service import get_config

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> DashboardOut:
    config = get_config(db)
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    schedule = schedule_service.get_schedule(db, target_year, target_month)
    current: dict | None = None
    if schedule is not None:
        validation = schedule.validation or {}
        assignments = db.scalar(
            select(func.count(Assignment.id)).where(Assignment.schedule_id == schedule.id)
        )
        current = {
            "schedule": ScheduleOut.model_validate(schedule).model_dump(mode="json"),
            "assignments": assignments or 0,
            "errors": len(validation.get("errors", [])),
            "warnings": len(validation.get("warnings", [])),
            "checks": validation.get("checks", []),
        }

    active = db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))) or 0
    total = db.scalar(select(func.count(Employee.id))) or 0
    recent = list(
        db.scalars(
            select(Schedule).order_by(Schedule.year.desc(), Schedule.month.desc()).limit(6)
        )
    )
    shifts = list(db.scalars(select(Shift).where(Shift.active.is_(True)).order_by(Shift.sort_order)))
    db.commit()

    return DashboardOut(
        facility_name=config.facility_name,
        department_name=config.department_name,
        current=current,
        employees_active=active,
        employees_total=total,
        shifts=[ShiftOut.model_validate(s) for s in shifts],
        recent_schedules=[ScheduleOut.model_validate(s) for s in recent],
    )
