"""Polish public holidays - generated for any year, extendable by the manager."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db_session, require_admin, require_manager
from app.models import AuditAction, Holiday, User
from app.schemas import HolidayCreate, HolidayOut
from app.services import audit_service
from app.services.config_service import get_config
from app.services.holiday_service import ensure_holidays_for_year, holidays_for_year

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


def to_out(row: Holiday) -> HolidayOut:
    return HolidayOut(
        id=row.id, date=row.day, name=row.name, country=row.country, is_custom=row.is_custom
    )


@router.get("/{year}", response_model=list[HolidayOut])
def get_holidays(
    year: int = Path(ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_manager),
) -> list[HolidayOut]:
    country = get_config(db).country_code
    added = ensure_holidays_for_year(db, year, country)
    if added:
        db.commit()
    return [to_out(row) for row in holidays_for_year(db, year, country)]


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_custom_holiday(
    payload: HolidayCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> HolidayOut:
    existing = db.scalar(
        select(Holiday).where(Holiday.day == payload.date, Holiday.country == payload.country)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Ten dzien jest juz oznaczony jako swieto.")
    row = Holiday(day=payload.date, name=payload.name, country=payload.country, is_custom=True)
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        AuditAction.HOLIDAYS_IMPORTED,
        user=user,
        entity_type="holiday",
        entity_id=row.id,
        metadata={"date": payload.date.isoformat(), "name": payload.name, "custom": True},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(row)
    return to_out(row)


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_custom_holiday(
    holiday_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> None:
    row = db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono swieta.")
    if not row.is_custom:
        raise HTTPException(
            status_code=400,
            detail="Swiat ustawowych nie mozna usuwac - wynikaja z przepisow.",
        )
    db.delete(row)
    audit_service.record(
        db,
        AuditAction.HOLIDAYS_IMPORTED,
        user=user,
        entity_type="holiday",
        entity_id=holiday_id,
        metadata={"deleted": True},
        ip_address=client_ip(request),
    )
    db.commit()
