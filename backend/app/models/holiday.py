from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Holiday(Base, TimestampMixin):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column("date", Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="PL", nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "country", name="uq_holiday_date_country"),
        Index("ix_holidays_country_date", "country", "date"),
    )
