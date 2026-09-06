"""Scheduling core: pure Python, no database access.

``rules`` holds the single source of truth for every business rule;
``constraints``/``optimizer``/``solver`` build and run the CP-SAT model and
``validator``/``statistics`` verify and describe the result independently.
"""
from app.scheduler.models import (
    EmployeeCtx,
    PlannedAssignment,
    PlanningContext,
    RuleConfig,
    ShiftDef,
    SundayRuleMode,
    Violation,
)
from app.scheduler.solver import GenerationResult, generate
from app.scheduler.statistics import build_statistics
from app.scheduler.validator import ValidationResult, validate

__all__ = [
    "EmployeeCtx",
    "GenerationResult",
    "PlannedAssignment",
    "PlanningContext",
    "RuleConfig",
    "ShiftDef",
    "SundayRuleMode",
    "ValidationResult",
    "Violation",
    "build_statistics",
    "generate",
    "validate",
]
