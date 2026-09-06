"""SOFT constraints - the objective function.

Only reached once every HARD constraint is satisfiable: soft goals may never
buy their way out of a hard rule. Priorities follow the specification:

1. equal share of night shifts
2. equal share of weekends
3. equal share of holidays
4. equal share of total hours
5. employee preferences
6. preferred days off
"""
from __future__ import annotations

from datetime import date

from ortools.sat.python import cp_model

from app.models.enums import AvailabilityType
from app.scheduler.constraints import ModelVars
from app.scheduler.models import PlanningContext

#: Preference type -> shift code it asks for.
PREFERENCE_TO_SHIFT: dict[AvailabilityType, str] = {
    AvailabilityType.PREFERRED_DAY: "D",
    AvailabilityType.PREFERRED_MORNING: "R",
    AvailabilityType.PREFERRED_NIGHT: "N",
}

MINUTES_PER_UNIT = 60


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def _employee_sum(v: ModelVars, ctx: PlanningContext, employee_id: int, predicate) -> list:
    return [
        var
        for (emp, day, code), var in v.x.items()
        if emp == employee_id and predicate(day, code)
    ]


def build_counters(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """Per-employee counters used by the fairness objectives."""
    shift_by_code = ctx.shift_by_code
    max_shifts = len(ctx.days)
    max_minutes = max_shifts * max((s.duration_minutes for s in ctx.shifts), default=0)

    for employee in ctx.employees:
        eid = employee.id
        nights = _employee_sum(v, ctx, eid, lambda d, c: shift_by_code[c].is_night)
        weekends = _employee_sum(v, ctx, eid, lambda d, c: is_weekend(d))
        holidays = _employee_sum(v, ctx, eid, lambda d, c: ctx.is_holiday(d))

        for label, target, terms in (
            ("nights", v.nights, nights),
            ("weekends", v.weekends, weekends),
            ("holidays", v.holidays, holidays),
        ):
            counter = model.NewIntVar(0, max_shifts, f"{label}_{eid}")
            model.Add(counter == (sum(terms) if terms else 0))
            target[eid] = counter

        minutes_terms = [
            shift_by_code[code].duration_minutes * var
            for (emp, _day, code), var in v.x.items()
            if emp == eid
        ]
        v.minutes[eid] = model.NewIntVar(0, max(max_minutes, 1), f"minutes_{eid}")
        if minutes_terms:
            model.Add(v.minutes[eid] == sum(minutes_terms))
        else:
            model.Add(v.minutes[eid] == 0)


def _spread(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    upper: int,
    name: str,
) -> cp_model.IntVar:
    """max(values) - min(values) as a fresh variable."""
    spread = model.NewIntVar(0, max(upper, 1), f"spread_{name}")
    if len(values) < 2:
        model.Add(spread == 0)
        return spread
    high = model.NewIntVar(0, max(upper, 1), f"max_{name}")
    low = model.NewIntVar(0, max(upper, 1), f"min_{name}")
    model.AddMaxEquality(high, values)
    model.AddMinEquality(low, values)
    model.Add(spread == high - low)
    return spread


def add_objective(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """Weighted sum of soft penalties; lower is better."""
    config = ctx.config
    build_counters(model, v, ctx)

    employee_ids = [e.id for e in ctx.employees]
    n_days = len(ctx.days)
    max_minutes = n_days * max((s.duration_minutes for s in ctx.shifts), default=1)

    terms: list = []

    night_spread = _spread(model, [v.nights[i] for i in employee_ids], n_days, "nights")
    terms.append(config.weight_night_fairness * night_spread)

    weekend_spread = _spread(model, [v.weekends[i] for i in employee_ids], n_days, "weekends")
    terms.append(config.weight_weekend_fairness * weekend_spread)

    holiday_spread = _spread(model, [v.holidays[i] for i in employee_ids], n_days, "holidays")
    terms.append(config.weight_holiday_fairness * holiday_spread)

    minutes_spread = _spread(model, [v.minutes[i] for i in employee_ids], max_minutes, "minutes")
    # Expressed in whole hours so it is comparable with the shift counters.
    hours_spread = model.NewIntVar(0, max(max_minutes // MINUTES_PER_UNIT, 1), "spread_hours")
    model.AddDivisionEquality(hours_spread, minutes_spread, MINUTES_PER_UNIT)
    terms.append(config.weight_hours_fairness * hours_spread)

    terms.extend(_preference_terms(v, ctx))

    if config.weight_coverage_bonus:
        coverage = sum(v.x.values()) if v.x else 0
        terms.append(-config.weight_coverage_bonus * coverage)

    model.Minimize(sum(terms))


def _preference_terms(v: ModelVars, ctx: PlanningContext) -> list:
    """Reward honoured preferences, penalise ignored days off."""
    config = ctx.config
    terms: list = []
    for (employee_id, day), declared in ctx.availability.items():
        if declared is AvailabilityType.PREFERRED_OFF:
            terms.extend(
                config.weight_preferred_off * v.x[(employee_id, day, s.code)]
                for s in ctx.shifts
                if (employee_id, day, s.code) in v.x
            )
            continue
        wanted = PREFERENCE_TO_SHIFT.get(declared)
        if wanted is None:
            continue
        key = (employee_id, day, wanted)
        if key in v.x:
            terms.append(-config.weight_preferences * v.x[key])
    return terms
