from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin
from app.scheduler.models import SundayRuleMode


class DepartmentConfig(Base, TimestampMixin):
    """Singleton row (id == 1) holding every tunable business rule."""

    __tablename__ = "department_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    facility_name: Mapped[str] = mapped_column(String(200), default="Szpital", nullable=False)
    department_name: Mapped[str] = mapped_column(String(200), default="Oddzial", nullable=False)

    #: 37 h 55 min == 2275 minutes. Always minutes, never floats.
    weekly_minutes_limit: Mapped[int] = mapped_column(Integer, default=2275, nullable=False)
    min_rest_minutes: Mapped[int] = mapped_column(Integer, default=660, nullable=False)
    sunday_free_every_n: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    #: First Sunday of the rolling "every Nth Sunday off" cycle.
    sunday_cycle_anchor: Mapped[date] = mapped_column(
        Date, default=date(2026, 1, 4), nullable=False
    )
    sunday_rule_mode: Mapped[SundayRuleMode] = mapped_column(
        SAEnum(SundayRuleMode, name="sunday_rule_mode"),
        default=SundayRuleMode.SLIDING,
        nullable=False,
    )
    #: Does a Saturday night count as working the following Sunday?
    sunday_includes_saturday_night: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    country_code: Mapped[str] = mapped_column(String(2), default="PL", nullable=False)

    solver_time_limit_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    solver_seed: Mapped[int] = mapped_column(Integer, default=42, nullable=False)
    solver_workers: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    #: Soft-constraint objective weights.
    weight_night_fairness: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    weight_weekend_fairness: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    weight_holiday_fairness: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    weight_hours_fairness: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    weight_preferences: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    weight_preferred_off: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    #: Reward for staffing a shift above the bare minimum. With a positive
    #: value the solver fills the roster up to the weekly hour limit (a normal
    #: full-time ward); set it to 0 to plan the minimum staffing only.
    weight_coverage_bonus: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    allow_overstaffing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_department_config_singleton"),
        CheckConstraint("weekly_minutes_limit > 0", name="ck_config_weekly_limit"),
        CheckConstraint("min_rest_minutes >= 0", name="ck_config_min_rest"),
        CheckConstraint("sunday_free_every_n >= 1", name="ck_config_sunday_n"),
        CheckConstraint(
            "solver_time_limit_seconds BETWEEN 1 AND 3600", name="ck_config_solver_limit"
        ),
    )
