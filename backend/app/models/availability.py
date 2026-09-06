from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import AvailabilityType


class Availability(Base, TimestampMixin):
    """One declaration per employee per day."""

    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column("date", Date, nullable=False, index=True)
    type: Mapped[AvailabilityType] = mapped_column(
        SAEnum(AvailabilityType, name="availability_type"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(500))

    employee = relationship("Employee", back_populates="availabilities")

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_availability_employee_date"),
        Index("ix_availability_date_type", "date", "type"),
    )
