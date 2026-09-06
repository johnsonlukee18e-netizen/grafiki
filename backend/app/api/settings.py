"""Department configuration and shift definitions (ADMIN only for writes)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_admin, require_manager
from app.models import AuditAction, Shift, User
from app.schemas import DepartmentConfigOut, DepartmentConfigUpdate, ShiftOut, ShiftUpdate
from app.services import audit_service
from app.services.config_service import get_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=DepartmentConfigOut)
def read_settings(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> DepartmentConfigOut:
    config = get_config(db)
    db.commit()
    return DepartmentConfigOut.model_validate(config)


@router.put("", response_model=DepartmentConfigOut)
def update_settings(
    payload: DepartmentConfigUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> DepartmentConfigOut:
    config = get_config(db)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(config, field, value)
    db.flush()
    audit_service.record(
        db,
        AuditAction.SETTINGS_UPDATED,
        user=user,
        entity_type="department_config",
        entity_id=config.id,
        metadata={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(config)
    return DepartmentConfigOut.model_validate(config)


@router.get("/shifts", response_model=list[ShiftOut])
def list_shifts(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[Shift]:
    return list(db.scalars(select(Shift).order_by(Shift.sort_order, Shift.id)))


@router.put("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zmiany.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(shift, field, value)
    if "start_time" in changes or "end_time" in changes or "duration_minutes" in changes:
        shift.crosses_midnight = shift.end_time <= shift.start_time
        if "duration_minutes" not in changes:
            shift.duration_minutes = _span_minutes(shift)
    db.flush()
    audit_service.record(
        db,
        AuditAction.SETTINGS_UPDATED,
        user=user,
        entity_type="shift",
        entity_id=shift.id,
        metadata={"code": shift.code, "changes": {k: str(v) for k, v in changes.items()}},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(shift)
    return shift


def _span_minutes(shift: Shift) -> int:
    """Wall-clock length of a shift, wrapping over midnight when needed."""
    reference = datetime(2000, 1, 1)
    start = datetime.combine(reference.date(), shift.start_time)
    end = datetime.combine(reference.date(), shift.end_time)
    if shift.crosses_midnight:
        end = datetime.combine(reference.date().replace(day=2), shift.end_time)
    return int((end - start).total_seconds() // 60)
