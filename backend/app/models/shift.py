from __future__ import annotations

from datetime import time

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Shift(Base, TimestampMixin):
    """Working shift definition. Hours live in the DB, never hardcoded."""

    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimum_staff: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_shift_duration_positive"),
        CheckConstraint("minimum_staff >= 0", name="ck_shift_min_staff_nonneg"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Shift {self.code} {self.duration_minutes}min>"
