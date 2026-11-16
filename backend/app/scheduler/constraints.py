"""HARD constraints translated into the CP-SAT model.

Every predicate comes from ``rules.py`` so the solver and the validator can
never drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ortools.sat.python import cp_model

from app.scheduler import rules
from app.scheduler.models import PlannedAssignment, PlanningContext, ShiftDef

#: Key of a decision variable: employee, calendar day, shift code.
VarKey = tuple[int, date, str]


@dataclass
class ModelVars:
    """Decision variables plus the derived per-employee counters."""

    x: dict[VarKey, cp_model.IntVar] = field(default_factory=dict)
    minutes: dict[int, cp_model.IntVar] = field(default_factory=dict)
    nights: dict[int, cp_model.IntVar] = field(default_factory=dict)
    weekends: dict[int, cp_model.IntVar] = field(default_factory=dict)
    holidays: dict[int, cp_model.IntVar] = field(default_factory=dict)

    def for_employee_day(self, employee_id: int, day: date, ctx: PlanningContext):
        return [
            self.x[(employee_id, day, s.code)]
            for s in ctx.shifts
            if (employee_id, day, s.code) in self.x
        ]


def boundary_map(ctx: PlanningContext) -> dict[tuple[int, date], str]:
    return {(a.employee_id, a.day): a.shift_code for a in ctx.boundary}


def create_variables(model: cp_model.CpModel, ctx: PlanningContext) -> ModelVars:
    """One boolean per (employee, day, shift) that is at all possible.

    HARD 6 (unavailability), the employment date and inactive employees are
    handled by simply not creating the variable.
    """
    variables = ModelVars()
    for employee in ctx.employees:
        for day in ctx.days:
            if not ctx.can_work(employee, day):
                continue
            for shift in ctx.shifts:
                key = (employee.id, day, shift.code)
                name = f"x_{employee.id}_{day.isoformat()}_{shift.code}"
                variables.x[key] = model.NewBoolVar(name)
    return variables


def add_one_shift_per_day(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    for employee in ctx.employees:
        for day in ctx.days:
            day_vars = v.for_employee_day(employee.id, day, ctx)
            if day_vars:
                model.AddAtMostOne(day_vars)


def add_minimum_staffing(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """HARD 1 - at least ``minimum_staff`` people on every open shift."""
    for day in ctx.days:
        for shift in ctx.shifts:
            if shift.minimum_staff <= 0:
                continue
            candidates = [
                v.x[(e.id, day, shift.code)]
                for e in ctx.employees
                if (e.id, day, shift.code) in v.x
            ]
            if ctx.config.allow_overstaffing:
                model.Add(sum(candidates) >= shift.minimum_staff)
            else:
                model.Add(sum(candidates) == shift.minimum_staff)


def nurse_candidates(v: ModelVars, ctx: PlanningContext, day: date, shift: ShiftDef) -> list:
    return [
        v.x[(e.id, day, shift.code)]
        for e in ctx.employees
        if e.is_nurse and (e.id, day, shift.code) in v.x
    ]


def add_minimum_nurses(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """HARD 1b - at least ``minimum_nurses`` of the crew must be nurses."""
    for day in ctx.days:
        for shift in ctx.shifts:
            if shift.minimum_nurses <= 0:
                continue
            model.Add(sum(nurse_candidates(v, ctx, day, shift)) >= shift.minimum_nurses)


def add_weekly_limit(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """HARD 2 - 37:55 per Monday-Sunday week, carried across month borders."""
    shift_by_code = ctx.shift_by_code
    fixed = rules.worked_minutes_by_week(ctx.boundary, shift_by_code)
    weeks: dict[tuple[int, int], list[date]] = {}
    for day in ctx.days:
        weeks.setdefault(rules.iso_week_key(day), []).append(day)

    for employee in ctx.employees:
        for week, days in weeks.items():
            terms = [
                shift_by_code[code].duration_minutes * v.x[(employee.id, day, code)]
                for day in days
                for code in shift_by_code
                if (employee.id, day, code) in v.x
            ]
            if not terms:
                continue
            already = fixed.get((employee.id, week), 0)
            model.Add(sum(terms) <= ctx.config.weekly_minutes_limit - already)


def add_rest_and_night_rules(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """HARD 3 (11 h rest) and HARD 4 (only night or free after a night).

    Both in-month pairs and pairs crossing into the neighbouring months are
    covered; boundary assignments are facts, so conflicting variables are
    pinned to zero.
    """
    shift_by_code = ctx.shift_by_code
    boundary = boundary_map(ctx)
    day_set = set(ctx.days)

    for employee in ctx.employees:
        for day in ctx.days:
            for gap in range(1, rules.MAX_INTERACTION_DAYS + 1):
                later = day + timedelta(days=gap)
                for first in ctx.shifts:
                    for second in ctx.shifts:
                        legal, _ = rules.shift_pair_is_legal(first, day, second, later, ctx.config)
                        if legal:
                            continue
                        _forbid_pair(
                            model, v, employee.id, day, first, later, second, day_set, boundary
                        )
                earlier = day - timedelta(days=gap)
                if earlier in day_set:
                    continue  # handled by the forward pass above
                previous_code = boundary.get((employee.id, earlier))
                if previous_code is None or previous_code not in shift_by_code:
                    continue
                previous = shift_by_code[previous_code]
                for second in ctx.shifts:
                    legal, _ = rules.shift_pair_is_legal(previous, earlier, second, day, ctx.config)
                    key = (employee.id, day, second.code)
                    if not legal and key in v.x:
                        model.Add(v.x[key] == 0)


def _forbid_pair(
    model: cp_model.CpModel,
    v: ModelVars,
    employee_id: int,
    first_day: date,
    first: ShiftDef,
    second_day: date,
    second: ShiftDef,
    day_set: set[date],
    boundary: dict[tuple[int, date], str],
) -> None:
    """Forbid an illegal (day, shift) -> (day, shift) succession."""
    first_key = (employee_id, first_day, first.code)
    second_key = (employee_id, second_day, second.code)

    if second_day in day_set:
        if first_key in v.x and second_key in v.x:
            model.AddAtMostOne([v.x[first_key], v.x[second_key]])
        return
    # The later day belongs to the next month: it is already a fixed fact.
    if boundary.get((employee_id, second_day)) == second.code and first_key in v.x:
        model.Add(v.x[first_key] == 0)


def add_sunday_rule(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    """HARD 5 - at least one free Sunday in every cycle of N Sundays."""
    config = ctx.config
    n = config.sunday_free_every_n
    if n < 1:
        return
    lookaround = timedelta(days=7 * (n - 1))
    all_sundays = rules.sundays_between(ctx.first_day - lookaround, ctx.last_day + lookaround)
    windows = rules.sunday_windows(all_sundays, config)
    day_set = set(ctx.days)
    boundary = boundary_map(ctx)

    for employee in ctx.employees:
        for window in windows:
            if not any(sunday in day_set for sunday in window):
                continue  # nothing in this window is ours to decide
            terms: list[cp_model.IntVar] = []
            fixed_worked = 0
            for sunday in window:
                if sunday in day_set:
                    terms.extend(_sunday_terms(v, ctx, employee.id, sunday))
                elif _boundary_works_sunday(ctx, boundary, employee.id, sunday):
                    fixed_worked += 1
            if not terms:
                continue
            # Previous months may already have broken the cycle; we still force
            # the best possible outcome here instead of turning the whole model
            # infeasible. The validator reports the historic breach separately.
            allowed = max(n - 1 - fixed_worked, 0)
            model.Add(sum(terms) <= allowed)


def _sunday_terms(v: ModelVars, ctx: PlanningContext, employee_id: int, sunday: date) -> list:
    terms = [
        v.x[(employee_id, sunday, s.code)]
        for s in ctx.shifts
        if (employee_id, sunday, s.code) in v.x
    ]
    if ctx.config.sunday_includes_saturday_night:
        saturday = sunday - timedelta(days=1)
        terms.extend(
            v.x[(employee_id, saturday, s.code)]
            for s in ctx.shifts
            if s.is_night and (employee_id, saturday, s.code) in v.x
        )
    return terms


def _boundary_works_sunday(
    ctx: PlanningContext,
    boundary: dict[tuple[int, date], str],
    employee_id: int,
    sunday: date,
) -> bool:
    if (employee_id, sunday) in boundary:
        return True
    if not ctx.config.sunday_includes_saturday_night:
        return False
    code = boundary.get((employee_id, sunday - timedelta(days=1)))
    shift = ctx.shift_by_code.get(code) if code else None
    return bool(shift and shift.is_night)


def add_all_hard_constraints(model: cp_model.CpModel, v: ModelVars, ctx: PlanningContext) -> None:
    add_one_shift_per_day(model, v, ctx)
    add_minimum_staffing(model, v, ctx)
    add_minimum_nurses(model, v, ctx)
    add_weekly_limit(model, v, ctx)
    add_rest_and_night_rules(model, v, ctx)
    add_sunday_rule(model, v, ctx)


def solution_to_assignments(solver: cp_model.CpSolver, v: ModelVars) -> list[PlannedAssignment]:
    out = [
        PlannedAssignment(employee_id=emp, day=day, shift_code=code)
        for (emp, day, code), var in v.x.items()
        if solver.Value(var)
    ]
    out.sort(key=lambda a: (a.day, a.employee_id, a.shift_code))
    return out
