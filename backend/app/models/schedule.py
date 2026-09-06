from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import ScheduleStatus


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(
        SAEnum(ScheduleStatus, name="schedule_status"),
        default=ScheduleStatus.DRAFT,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    #: Cached output of the last validator run (errors / warnings / statistics).
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    solver_status: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(String(1000))

    assignments = relationship(
        "Assignment",
        back_populates="schedule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    versions = relationship(
        "ScheduleVersion",
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleVersion.version",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_schedule_year_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_schedule_month_range"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_schedule_year_range"),
        Index("ix_schedules_year_month", "year", "month"),
    )

    @property
    def is_editable(self) -> bool:
        return self.status not in (ScheduleStatus.APPROVED, ScheduleStatus.ARCHIVED)


class Assignment(Base, TimestampMixin):
    """A single employee-on-shift-on-day allocation with real timestamps."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    manually_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    schedule = relationship("Schedule", back_populates="assignments")
    employee = relationship("Employee", back_populates="assignments")
    shift = relationship("Shift", lazy="joined")

    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_assignment_employee_day"),
        CheckConstraint("end_datetime > start_datetime", name="ck_assignment_time_order"),
        Index("ix_assignments_schedule_date", "schedule_id", "work_date"),
        Index("ix_assignments_employee_start", "employee_id", "start_datetime"),
    )


class ScheduleVersion(Base):
    """Immutable snapshot of a schedule taken before every mutation."""

    __tablename__ = "schedule_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(
        SAEnum(ScheduleStatus, name="schedule_status"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: [{employee_id, shift_code, work_date, manually_modified}, ...]
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    schedule = relationship("Schedule", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("schedule_id", "version", name="uq_schedule_version"),
    )
