"""Availability and preferences (UNAVAILABLE is a hard constraint)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_manager
from app.models import AuditAction, Availability, Employee, User
from app.schemas import (
    AvailabilityBulkCreate,
    AvailabilityCreate,
    AvailabilityOut,
    AvailabilityUpdate,
)
from app.services import audit_service

router = APIRouter(prefix="/api/availability", tags=["availability"])


def to_out(row: Availability) -> AvailabilityOut:
    return AvailabilityOut(
        id=row.id,
        employee_id=row.employee_id,
        date=row.day,
        type=row.type,
        note=row.note,
    )


@router.get("", response_model=list[AvailabilityOut])
def list_availability(
    employee_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[AvailabilityOut]:
    if year and month:
        import calendar

        date_from = date(year, month, 1)
        date_to = date(year, month, calendar.monthrange(year, month)[1])

    query = select(Availability).order_by(Availability.day, Availability.employee_id)
    if employee_id is not None:
        query = query.where(Availability.employee_id == employee_id)
    if date_from is not None:
        query = query.where(Availability.day >= date_from)
    if date_to is not None:
        query = query.where(Availability.day <= date_to)
    return [to_out(row) for row in db.scalars(query)]


def _require_employee(db: Session, employee_id: int) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono pracownika.")
    return employee


def _upsert(db: Session, employee_id: int, day: date, type_, note: str | None) -> Availability:
    row = db.scalar(
        select(Availability).where(
            Availability.employee_id == employee_id, Availability.day == day
        )
    )
    if row is None:
        row = Availability(employee_id=employee_id, day=day, type=type_, note=note)
        db.add(row)
    else:
        row.type = type_
        row.note = note
    db.flush()
    return row


@router.post("", response_model=AvailabilityOut, status_code=status.HTTP_201_CREATED)
def set_availability(
    payload: AvailabilityCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> AvailabilityOut:
    _require_employee(db, payload.employee_id)
    row = _upsert(db, payload.employee_id, payload.date, payload.type, payload.note)
    audit_service.record(
        db,
        AuditAction.AVAILABILITY_CHANGED,
        user=user,
        entity_type="availability",
        entity_id=row.id,
        metadata={
            "employee_id": payload.employee_id,
            "date": payload.date.isoformat(),
            "type": payload.type.value,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(row)
    return to_out(row)


@router.post("/bulk", response_model=list[AvailabilityOut])
def set_availability_bulk(
    payload: AvailabilityBulkCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> list[AvailabilityOut]:
    """Mark many days at once - the availability calendar uses this."""
    _require_employee(db, payload.employee_id)
    rows = [
        _upsert(db, payload.employee_id, day, payload.type, payload.note)
        for day in sorted(set(payload.dates))
    ]
    audit_service.record(
        db,
        AuditAction.AVAILABILITY_CHANGED,
        user=user,
        entity_type="availability",
        entity_id=payload.employee_id,
        metadata={
            "employee_id": payload.employee_id,
            "type": payload.type.value,
            "days": len(rows),
            "from": min(payload.dates).isoformat(),
            "to": max(payload.dates).isoformat(),
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return [to_out(row) for row in rows]


@router.put("/{availability_id}", response_model=AvailabilityOut)
def update_availability(
    availability_id: int,
    payload: AvailabilityUpdate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> AvailabilityOut:
    row = db.get(Availability, availability_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono wpisu dostępności.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()
    audit_service.record(
        db,
        AuditAction.AVAILABILITY_CHANGED,
        user=user,
        entity_type="availability",
        entity_id=row.id,
        metadata={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(row)
    return to_out(row)


@router.delete(
    "/{availability_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_availability(
    availability_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_manager),
) -> None:
    row = db.get(Availability, availability_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono wpisu dostępności.")
    metadata = {"employee_id": row.employee_id, "date": row.day.isoformat()}
    db.delete(row)
    audit_service.record(
        db,
        AuditAction.AVAILABILITY_CHANGED,
        user=user,
        entity_type="availability",
        entity_id=availability_id,
        metadata={**metadata, "deleted": True},
        ip_address=client_ip(request),
    )
    db.commit()
