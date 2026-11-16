"""Department configuration: one row, created on demand."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DepartmentConfig
from app.scheduler.models import RuleConfig

CONFIG_ID = 1


def get_config(db: Session) -> DepartmentConfig:
    config = db.get(DepartmentConfig, CONFIG_ID)
    if config is None:
        config = DepartmentConfig(
            id=CONFIG_ID,
            solver_time_limit_seconds=settings.solver_time_limit_seconds,
            solver_seed=settings.solver_seed,
            solver_workers=settings.solver_workers,
        )
        db.add(config)
        db.flush()
    return config


def to_rule_config(config: DepartmentConfig) -> RuleConfig:
    """Database row -> immutable bundle used by the scheduling core."""
    return RuleConfig(
        weekly_minutes_limit=config.weekly_minutes_limit,
        min_rest_minutes=config.min_rest_minutes,
        sunday_free_every_n=config.sunday_free_every_n,
        sunday_rule_mode=config.sunday_rule_mode,
        sunday_cycle_anchor=config.sunday_cycle_anchor,
        sunday_includes_saturday_night=config.sunday_includes_saturday_night,
        solver_time_limit_seconds=min(
            config.solver_time_limit_seconds, settings.solver_max_seconds
        ),
        solver_seed=config.solver_seed,
        solver_workers=config.solver_workers,
        allow_overstaffing=config.allow_overstaffing,
        weight_night_fairness=config.weight_night_fairness,
        weight_weekend_fairness=config.weight_weekend_fairness,
        weight_holiday_fairness=config.weight_holiday_fairness,
        weight_hours_fairness=config.weight_hours_fairness,
        weight_preferences=config.weight_preferences,
        weight_preferred_off=config.weight_preferred_off,
        weight_coverage_bonus=config.weight_coverage_bonus,
    )


def shifts_exist(db: Session) -> bool:
    from app.models import Shift

    return db.scalar(select(Shift.id).limit(1)) is not None
