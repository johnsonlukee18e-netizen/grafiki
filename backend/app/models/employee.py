from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import EmployeeColor, EmployeeRole


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[EmployeeRole] = mapped_column(
        SAEnum(EmployeeRole, name="employee_role"), nullable=False
    )
    employment_date: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    availabilities = relationship(
        "Availability", back_populates="employee", cascade="all, delete-orphan"
    )
    assignments = relationship(
        "Assignment", back_populates="employee", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("length(trim(first_name)) > 0", name="ck_employee_first_name"),
        CheckConstraint("length(trim(last_name)) > 0", name="ck_employee_last_name"),
        Index("ix_employees_active_last_name", "active", "last_name"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def color(self, on_date: date | None = None) -> EmployeeColor:
        from app.services.seniority import employee_color

        return employee_color(self.role, self.employment_date, on_date)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee {self.full_name}>"
