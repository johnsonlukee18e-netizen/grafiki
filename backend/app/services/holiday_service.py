"""Holiday import / lookup."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holiday
from app.services.holidays_pl import polish_holidays


def holidays_for_year(db: Session, year: int, country: str = "PL") -> list[Holiday]:
    return list(
        db.scalars(
            select(Holiday)
            .where(
                Holiday.country == country,
                Holiday.day >= date(year, 1, 1),
                Holiday.day <= date(year, 12, 31),
            )
            .order_by(Holiday.day)
        )
    )


def ensure_holidays_for_year(db: Session, year: int, country: str = "PL") -> int:
    """Import statutory holidays for ``year`` if they are not there yet.

    Custom entries added by the manager are never touched.
    """
    if country != "PL":
        return 0
    existing = {h.day for h in holidays_for_year(db, year, country)}
    added = 0
    for holiday in polish_holidays(year):
        if holiday.day in existing:
            continue
        db.add(Holiday(day=holiday.day, name=holiday.name, country=country, is_custom=False))
        added += 1
    if added:
        db.flush()
    return added
