"""CP-SAT driver: build, solve, explain.

The solver only ever returns rosters that satisfy every HARD constraint. If
no such roster exists it returns the reasons instead of a relaxed schedule.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ortools.sat.python import cp_model

from app.scheduler import constraints as hard
from app.scheduler import diagnostics as diag
from app.scheduler import optimizer
from app.scheduler.models import PlannedAssignment, PlanningContext

logger = logging.getLogger(__name__)

#: Seconds granted to the diagnostic (feasibility-only) model.
DIAGNOSTIC_TIME_LIMIT = 15.0


@dataclass
class GenerationResult:
    success: bool
    status: str
    assignments: list[PlannedAssignment] = field(default_factory=list)
    objective: int | None = None
    is_optimal: bool = False
    wall_time_seconds: float = 0.0
    message: str = ""
    diagnostics: list[diag.Diagnostic] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "objective": self.objective,
            "is_optimal": self.is_optimal,
            "wall_time_seconds": round(self.wall_time_seconds, 3),
            "message": self.message,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "suggestions": self.suggestions,
        }


def _configure(solver: cp_model.CpSolver, ctx: PlanningContext, time_limit: float) -> None:
    params = solver.parameters
    params.max_time_in_seconds = time_limit
    params.random_seed = ctx.config.solver_seed
    params.num_search_workers = max(1, ctx.config.solver_workers)
    params.log_search_progress = False
    # CP-SAT parallel workers race each other, so only a single worker gives a
    # bit-for-bit reproducible roster. Set solver_workers=1 in the department
    # configuration when reproducibility matters more than speed.


def generate(ctx: PlanningContext) -> GenerationResult:
    """Produce the best roster the solver can find within its time budget."""
    pre = diag.pre_solve_checks(ctx)
    blocking = [d for d in pre if d.code in diag.BLOCKING_CODES]
    if blocking:
        return GenerationResult(
            success=False,
            status="INFEASIBLE",
            message=(
                "Nie znaleziono grafiku spelniajacego wszystkie wymagania. "
                "Ponizsze warunki wykluczaja sie wzajemnie."
            ),
            diagnostics=blocking,
            suggestions=diag.suggestions_for(blocking, ctx),
        )

    model = cp_model.CpModel()
    variables = hard.create_variables(model, ctx)
    hard.add_all_hard_constraints(model, variables, ctx)
    optimizer.add_objective(model, variables, ctx)

    solver = cp_model.CpSolver()
    _configure(solver, ctx, float(ctx.config.solver_time_limit_seconds))
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    logger.info(
        "solver finished status=%s wall=%.2fs vars=%d",
        status_name,
        solver.WallTime(),
        len(variables.x),
    )

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignments = hard.solution_to_assignments(solver, variables)
        is_optimal = status == cp_model.OPTIMAL
        message = (
            "Znaleziono optymalny grafik."
            if is_optimal
            else (
                "Zwrocono najlepszy grafik znaleziony w dostepnym czasie "
                f"({ctx.config.solver_time_limit_seconds} s). "
                "Wszystkie twarde ograniczenia sa spelnione, ale rozwiazanie "
                "moze nie byc optymalne - zwieksz limit czasu, aby poprawic wynik."
            )
        )
        return GenerationResult(
            success=True,
            status=status_name,
            assignments=assignments,
            objective=int(solver.ObjectiveValue()),
            is_optimal=is_optimal,
            wall_time_seconds=solver.WallTime(),
            message=message,
        )

    if status == cp_model.INFEASIBLE:
        core = _infeasibility_core(ctx)
        found = pre + core
        return GenerationResult(
            success=False,
            status=status_name,
            wall_time_seconds=solver.WallTime(),
            message=(
                "Nie znaleziono grafiku spelniajacego wszystkie wymagania. "
                "Ponizej znajduja sie zidentyfikowane przyczyny."
            ),
            diagnostics=found,
            suggestions=diag.suggestions_for(found, ctx),
        )

    return GenerationResult(
        success=False,
        status=status_name,
        wall_time_seconds=solver.WallTime(),
        message=(
            "Solver nie zdazyl znalezc zadnego poprawnego grafiku w limicie czasu "
            f"({ctx.config.solver_time_limit_seconds} s). Zwieksz limit czasu w USTAWIENIACH."
        ),
        diagnostics=pre,
        suggestions=[
            "Zwieksz solver_time_limit_seconds w ustawieniach.",
            "Zmniejsz liczbe twardych ograniczen (np. nadmiarowe niedostepnosci).",
        ],
    )


def _infeasibility_core(ctx: PlanningContext) -> list[diag.Diagnostic]:
    """Ask CP-SAT which staffing requirements cannot hold together.

    Every minimum-staffing requirement is guarded by an assumption literal;
    the solver then names a subset that is already contradictory.
    """
    model = cp_model.CpModel()
    variables = hard.create_variables(model, ctx)
    hard.add_one_shift_per_day(model, variables, ctx)
    hard.add_weekly_limit(model, variables, ctx)
    hard.add_rest_and_night_rules(model, variables, ctx)
    hard.add_sunday_rule(model, variables, ctx)

    literals: dict[cp_model.IntVar, tuple[date, str, int, bool]] = {}
    for day in ctx.days:
        for shift in ctx.shifts:
            if shift.minimum_staff <= 0:
                continue
            candidates = [
                variables.x[(e.id, day, shift.code)]
                for e in ctx.employees
                if (e.id, day, shift.code) in variables.x
            ]
            literal = model.NewBoolVar(f"need_{day.isoformat()}_{shift.code}")
            model.Add(sum(candidates) >= shift.minimum_staff).OnlyEnforceIf(literal)
            literals[literal] = (day, shift.code, shift.minimum_staff, False)
            if shift.minimum_nurses > 0:
                nurses = model.NewBoolVar(f"nurses_{day.isoformat()}_{shift.code}")
                model.Add(
                    sum(hard.nurse_candidates(variables, ctx, day, shift)) >= shift.minimum_nurses
                ).OnlyEnforceIf(nurses)
                literals[nurses] = (day, shift.code, shift.minimum_nurses, True)

    model.AddAssumptions(list(literals.keys()))
    solver = cp_model.CpSolver()
    _configure(solver, ctx, DIAGNOSTIC_TIME_LIMIT)
    status = solver.Solve(model)

    if status != cp_model.INFEASIBLE:
        return []

    index_to_literal = {literal.Index(): literal for literal in literals}
    out: list[diag.Diagnostic] = []
    for index in solver.SufficientAssumptionsForInfeasibility():
        literal = index_to_literal.get(index)
        if literal is None:
            continue
        day, code, required, nurses_only = literals[literal]
        unavailable = diag.unavailable_summary(ctx, day)
        who = "pielegniarek" if nurses_only else "osob"
        message = (
            f"{day.isoformat()}: zmiana {code} wymaga {required} {who}, ale nie da sie ich "
            "obsadzic bez zlamania innych regul (odpoczynek, regula po nocce, limit godzin, "
            "wolne niedziele)."
        )
        if unavailable:
            message += " Niedostepni tego dnia: " + ", ".join(unavailable) + "."
        out.append(
            diag.Diagnostic(
                code="CORE_MIN_NURSES" if nurses_only else "CORE_MIN_STAFF",
                message=message,
                day=day,
                shift_code=code,
                details={
                    "required": required,
                    "nurses_only": nurses_only,
                    "unavailable_employees": unavailable,
                },
            )
        )
    return out[:20]
