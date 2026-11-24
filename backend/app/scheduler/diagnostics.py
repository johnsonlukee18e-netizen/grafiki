"""Explaining *why* a month cannot be scheduled.

The specification is explicit: never silently relax a rule and never answer
with a bare "generation failed". These checks run before the solver (cheap
arithmetic) and after an infeasible solve (CP-SAT assumption core).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.models.enums import AvailabilityType
from app.scheduler import rules
from app.scheduler.models import PlanningContext

#: Pre-solve findings that already prove the month cannot be scheduled.
BLOCKING_CODES = frozenset(
    {"NO_EMPLOYEES", "WEEK_CAPACITY", "DAY_UNDERSTAFFED", "DAY_NO_NURSES", "WEEK_NURSE_CAPACITY"}
)


@dataclass
class Diagnostic:
    code: str
    message: str
    day: date | None = None
    shift_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "date": self.day.isoformat() if self.day else None,
            "shift_code": self.shift_code,
            "details": self.details,
        }


def pre_solve_checks(ctx: PlanningContext) -> list[Diagnostic]:
    """Arithmetic that proves infeasibility before CP-SAT is even built."""
    return [
        *_no_staff_at_all(ctx),
        *_daily_availability(ctx),
        *_daily_nurses(ctx),
        *_weekly_capacity(ctx),
        *_weekly_capacity(ctx, nurses_only=True),
    ]


def _no_staff_at_all(ctx: PlanningContext) -> list[Diagnostic]:
    active = [e for e in ctx.employees if e.active]
    if active:
        return []
    return [
        Diagnostic(
            code="NO_EMPLOYEES",
            message="Brak aktywnych pracowników. Dodaj pracowników przed generowaniem grafiku.",
        )
    ]


def _daily_availability(ctx: PlanningContext) -> list[Diagnostic]:
    """A day where fewer people are available than the shifts require."""
    out: list[Diagnostic] = []
    for day in ctx.days:
        available = [e for e in ctx.employees if ctx.can_work(e, day)]
        needed = sum(s.minimum_staff for s in ctx.shifts_on(day))
        if len(available) < needed:
            unavailable = [
                e.full_name
                for e in ctx.employees
                if e.active and ctx.is_unavailable(e.id, day)
            ]
            out.append(
                Diagnostic(
                    code="DAY_UNDERSTAFFED",
                    message=(
                        f"{day.isoformat()}: wszystkie zmiany wymagają łącznie {needed} osób, "
                        f"a dostępnych jest {len(available)}."
                    ),
                    day=day,
                    details={
                        "required": needed,
                        "available": len(available),
                        "unavailable_employees": unavailable,
                    },
                )
            )
    return out


def _daily_nurses(ctx: PlanningContext) -> list[Diagnostic]:
    """A day where fewer nurses are available than the shifts require."""
    if not any(s.minimum_nurses > 0 for s in ctx.shifts):
        return []
    out: list[Diagnostic] = []
    for day in ctx.days:
        needed = sum(s.minimum_nurses for s in ctx.shifts_on(day))
        available = [e for e in ctx.employees if e.is_nurse and ctx.can_work(e, day)]
        if len(available) >= needed:
            continue
        out.append(
            Diagnostic(
                code="DAY_NO_NURSES",
                message=(
                    f"{day.isoformat()}: zmiany wymagają łącznie {needed} pielęgniarek, "
                    f"a dostępnych jest {len(available)}."
                ),
                day=day,
                details={"required": needed, "available": len(available)},
            )
        )
    return out


def _weekly_capacity(ctx: PlanningContext, *, nurses_only: bool = False) -> list[Diagnostic]:
    """Minutes demanded by the minimum staffing vs. minutes the team may work."""
    out: list[Diagnostic] = []
    limit = ctx.config.weekly_minutes_limit
    boundary_minutes = rules.worked_minutes_by_week(ctx.boundary, ctx.shift_by_code)

    weeks: dict[tuple[int, int], list[date]] = defaultdict(list)
    for day in ctx.days:
        weeks[rules.iso_week_key(day)].append(day)

    for week, days in sorted(weeks.items()):
        demand = sum(
            (shift.minimum_nurses if nurses_only else shift.minimum_staff)
            * shift.duration_minutes
            for day in days
            for shift in ctx.shifts_on(day)
        )
        if demand <= 0:
            continue
        longest_shift = max((s.duration_minutes for s in ctx.shifts), default=0)
        capacity = 0
        for employee in ctx.employees:
            if not employee.active or (nurses_only and not employee.is_nurse):
                continue
            usable_days = sum(1 for d in days if ctx.can_work(employee, d))
            if not usable_days:
                continue
            already = boundary_minutes.get((employee.id, week), 0)
            # An employee can never exceed the weekly limit, nor work more than
            # one (longest) shift on each day they are actually available.
            capacity += min(max(limit - already, 0), usable_days * longest_shift)
        if demand > capacity:
            out.append(
                Diagnostic(
                    code="WEEK_NURSE_CAPACITY" if nurses_only else "WEEK_CAPACITY",
                    message=(
                        f"Tydzień {rules.week_label(week)}: minimalna obsada "
                        f"{'pielęgniarska ' if nurses_only else ''}wymaga "
                        f"{rules.format_minutes_pl(demand)} pracy, a łączny limit zespołu "
                        f"{'pielęgniarek ' if nurses_only else ''}"
                        f"to {rules.format_minutes_pl(capacity)}."
                    ),
                    day=days[0],
                    details={
                        "week": rules.week_label(week),
                        "required_minutes": demand,
                        "available_minutes": capacity,
                        "missing_minutes": demand - capacity,
                        "employees_needed": _employees_needed(demand, limit),
                    },
                )
            )
    return out


def _employees_needed(demand_minutes: int, weekly_limit: int) -> int:
    if weekly_limit <= 0:
        return 0
    return -(-demand_minutes // weekly_limit)  # ceil


def suggestions_for(diagnostics: list[Diagnostic], ctx: PlanningContext) -> list[str]:
    """Actionable next steps in plain Polish."""
    out: list[str] = []
    codes = {d.code for d in diagnostics}

    if "NO_EMPLOYEES" in codes:
        out.append("Dodaj i aktywuj pracowników w panelu PRACOWNICY.")
    if "WEEK_CAPACITY" in codes:
        worst = max(
            (d for d in diagnostics if d.code == "WEEK_CAPACITY"),
            key=lambda d: d.details.get("missing_minutes", 0),
        )
        needed = worst.details.get("employees_needed", 0)
        out.append(
            f"Zwiększ liczbę aktywnych pracowników (przy obecnej obsadzie minimalnej "
            f"potrzeba co najmniej {needed} osób) albo zmniejsz minimalną obsadę w USTAWIENIACH."
        )
        out.append(
            "Sprawdź, czy limit tygodniowy "
            f"({rules.format_minutes_pl(ctx.config.weekly_minutes_limit)}) "
            "jest zgodny z umowami pracowników."
        )
    if "WEEK_NURSE_CAPACITY" in codes or "DAY_NO_NURSES" in codes:
        out.append(
            "Za mało pielęgniarek, aby spełnić minimalną liczbę pielęgniarek na zmianie. "
            "Dodaj pielęgniarki albo zmniejsz 'Min. pielęgniarek' w USTAWIENIACH."
        )
    if "DAY_UNDERSTAFFED" in codes:
        out.append(
            "Zweryfikuj zgłoszone niedostępności w tych dniach - "
            "każda niedostępność jest twardym ograniczeniem."
        )
    if "CORE_MIN_STAFF" in codes or "CORE_MIN_NURSES" in codes:
        out.append(
            "W wskazanych dniach nie da się obsadzić zmian bez złamania odpoczynku, "
            "reguły po nocce lub limitu godzin. Rozważ zwolnienie niedostępności "
            "albo dodanie osoby na te dni."
        )
    if not out:
        out.append(
            "Sprawdź dostępności, minimalną obsadę i limit tygodniowy - "
            "kombinacja tych ustawień uniemożliwia ułożenie grafiku."
        )
    return out


def unavailable_summary(ctx: PlanningContext, day: date) -> list[str]:
    """Who declared UNAVAILABLE on a given day (used in messages)."""
    return [
        e.full_name
        for e in ctx.employees
        if ctx.availability_of(e.id, day) is AvailabilityType.UNAVAILABLE
    ]
