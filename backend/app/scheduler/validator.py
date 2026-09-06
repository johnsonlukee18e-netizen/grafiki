"""Independent schedule validator.

This module deliberately re-checks the finished roster *without* looking at
the solver: it walks real timestamps and asks ``rules.py`` the same questions
the CP-SAT model asked. If the two ever disagree the schedule is reported as
invalid - the generator is never the only place a rule is enforced.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.models.enums import AvailabilityType
from app.scheduler import rules
from app.scheduler.models import PlannedAssignment, PlanningContext, Violation
from app.scheduler.statistics import build_statistics

#: Order of the checklist shown in the validation panel.
CHECKS: tuple[tuple[str, str], ...] = (
    (rules.RULE_MIN_STAFF, "Minimalna obsada"),
    (rules.RULE_WEEKLY_LIMIT, "Tygodniowy limit godzin"),
    (rules.RULE_MIN_REST, "Minimalny odpoczynek"),
    (rules.RULE_AFTER_NIGHT, "Regula po nocce"),
    (rules.RULE_SUNDAY_OFF, "Wolna niedziela w cyklu"),
    (rules.RULE_UNAVAILABLE, "Dostepnosc pracownikow"),
    (rules.RULE_ONE_SHIFT_PER_DAY, "Jedna zmiana dziennie"),
    (rules.RULE_NOT_EMPLOYED, "Data zatrudnienia"),
)

#: Soft checks reported as warnings only.
WARN_NIGHT_FAIRNESS = "NIGHT_FAIRNESS"
WARN_WEEKEND_FAIRNESS = "WEEKEND_FAIRNESS"
WARN_HOLIDAY_FAIRNESS = "HOLIDAY_FAIRNESS"
WARN_HOURS_FAIRNESS = "HOURS_FAIRNESS"
WARN_PREFERENCE = "PREFERENCE_IGNORED"
WARN_PREFERRED_OFF = "PREFERRED_OFF_IGNORED"

SOFT_CHECKS: tuple[tuple[str, str], ...] = (
    (WARN_NIGHT_FAIRNESS, "Rowny podzial nocy"),
    (WARN_WEEKEND_FAIRNESS, "Rowny podzial weekendow"),
    (WARN_HOLIDAY_FAIRNESS, "Rowny podzial swiat"),
    (WARN_HOURS_FAIRNESS, "Rowny podzial godzin"),
    (WARN_PREFERENCE, "Preferencje pracownikow"),
    (WARN_PREFERRED_OFF, "Preferowane dni wolne"),
)

#: A spread larger than this many shifts triggers a fairness warning.
FAIRNESS_TOLERANCE_SHIFTS = 1
#: A spread larger than this many minutes triggers an hours warning.
FAIRNESS_TOLERANCE_MINUTES = 480


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
            "statistics": self.statistics,
            "checks": self.checks,
        }


def validate(ctx: PlanningContext, assignments: list[PlannedAssignment]) -> ValidationResult:
    """Run every rule against ``assignments`` and return a full report."""
    employees = ctx.employee_by_id
    errors: list[Violation] = []
    warnings: list[Violation] = []

    in_window = [a for a in assignments if ctx.first_day <= a.day <= ctx.last_day]
    combined = sorted(
        in_window + list(ctx.boundary), key=lambda a: (a.employee_id, a.day, a.shift_code)
    )

    def name_of(employee_id: int) -> str:
        employee = employees.get(employee_id)
        return employee.full_name if employee else f"#{employee_id}"

    errors += _check_unknown_references(ctx, in_window)
    errors += _check_one_shift_per_day(in_window, name_of)
    errors += _check_minimum_staffing(ctx, in_window)
    errors += _check_availability(ctx, in_window, name_of)
    errors += _check_employment(ctx, in_window, name_of)
    errors += _check_weekly_limit(ctx, combined, name_of)
    errors += _check_sequences(ctx, combined, name_of)
    errors += _check_sundays(ctx, combined, name_of)

    statistics = build_statistics(ctx, in_window)
    warnings += _check_fairness(statistics)
    warnings += _check_preferences(ctx, in_window, name_of)

    checks = _build_checklist(errors, warnings)
    return ValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        statistics=statistics,
        checks=checks,
    )


# --- individual checks ----------------------------------------------------
def _check_unknown_references(
    ctx: PlanningContext, assignments: list[PlannedAssignment]
) -> list[Violation]:
    shifts = ctx.shift_by_code
    employees = ctx.employee_by_id
    out: list[Violation] = []
    for item in assignments:
        if item.shift_code not in shifts:
            out.append(
                Violation(
                    code="UNKNOWN_SHIFT",
                    severity="error",
                    message=f"Nieznana zmiana '{item.shift_code}' w dniu {item.day.isoformat()}.",
                    day=item.day,
                    shift_code=item.shift_code,
                )
            )
        if item.employee_id not in employees:
            out.append(
                Violation(
                    code="UNKNOWN_EMPLOYEE",
                    severity="error",
                    message=(
                        f"Grafik zawiera przypisanie nieaktywnego lub nieistniejacego "
                        f"pracownika (id {item.employee_id}) w dniu {item.day.isoformat()}."
                    ),
                    employee_id=item.employee_id,
                    day=item.day,
                )
            )
    return out


def _check_one_shift_per_day(assignments: list[PlannedAssignment], name_of) -> list[Violation]:
    seen: dict[tuple[int, date], list[str]] = defaultdict(list)
    for item in assignments:
        seen[(item.employee_id, item.day)].append(item.shift_code)
    out: list[Violation] = []
    for (employee_id, day), codes in sorted(seen.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if len(codes) > 1:
            out.append(
                Violation(
                    code=rules.RULE_ONE_SHIFT_PER_DAY,
                    severity="error",
                    message=(
                        f"{name_of(employee_id)} ma {len(codes)} zmiany "
                        f"({', '.join(sorted(codes))}) w dniu {day.isoformat()}. "
                        "Dozwolona jest jedna zmiana dziennie."
                    ),
                    employee_id=employee_id,
                    day=day,
                )
            )
    return out


def _check_minimum_staffing(
    ctx: PlanningContext, assignments: list[PlannedAssignment]
) -> list[Violation]:
    counts: dict[tuple[date, str], int] = defaultdict(int)
    for item in assignments:
        counts[(item.day, item.shift_code)] += 1
    out: list[Violation] = []
    for day in ctx.days:
        for shift in ctx.shifts:
            if shift.minimum_staff <= 0:
                continue
            actual = counts[(day, shift.code)]
            if actual < shift.minimum_staff:
                out.append(
                    Violation(
                        code=rules.RULE_MIN_STAFF,
                        severity="error",
                        message=(
                            f"{day.isoformat()}: zmiana {shift.code} ma {actual} "
                            f"os. przy wymaganym minimum {shift.minimum_staff}."
                        ),
                        day=day,
                        shift_code=shift.code,
                        details={"required": shift.minimum_staff, "actual": actual},
                    )
                )
    return out


def _check_availability(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    out: list[Violation] = []
    for item in assignments:
        if ctx.is_unavailable(item.employee_id, item.day):
            out.append(
                Violation(
                    code=rules.RULE_UNAVAILABLE,
                    severity="error",
                    message=(
                        f"{name_of(item.employee_id)} zglosil(a) niedostepnosc "
                        f"{item.day.isoformat()}, a ma przypisana zmiane {item.shift_code}."
                    ),
                    employee_id=item.employee_id,
                    day=item.day,
                    shift_code=item.shift_code,
                )
            )
    return out


def _check_employment(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    employees = ctx.employee_by_id
    out: list[Violation] = []
    for item in assignments:
        employee = employees.get(item.employee_id)
        if employee is None:
            continue
        if employee.employment_date > item.day:
            out.append(
                Violation(
                    code=rules.RULE_NOT_EMPLOYED,
                    severity="error",
                    message=(
                        f"{name_of(item.employee_id)} nie jest jeszcze zatrudniony(a) "
                        f"{item.day.isoformat()} (data zatrudnienia: "
                        f"{employee.employment_date.isoformat()})."
                    ),
                    employee_id=item.employee_id,
                    day=item.day,
                    shift_code=item.shift_code,
                )
            )
        if not employee.active:
            out.append(
                Violation(
                    code=rules.RULE_INACTIVE,
                    severity="error",
                    message=(
                        f"{name_of(item.employee_id)} jest nieaktywny(a), a ma zmiane "
                        f"{item.shift_code} w dniu {item.day.isoformat()}."
                    ),
                    employee_id=item.employee_id,
                    day=item.day,
                    shift_code=item.shift_code,
                )
            )
    return out


def _check_weekly_limit(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    """HARD 2 - weeks run Monday->Sunday and never restart at a month border."""
    shifts = ctx.shift_by_code
    totals = rules.worked_minutes_by_week(assignments, shifts)
    limit = ctx.config.weekly_minutes_limit
    window_weeks = {rules.iso_week_key(day) for day in ctx.days}
    out: list[Violation] = []
    for (employee_id, week), minutes in sorted(totals.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if week not in window_weeks:
            continue  # a week entirely outside the planned month
        if rules.weekly_limit_exceeded(minutes, ctx.config):
            out.append(
                Violation(
                    code=rules.RULE_WEEKLY_LIMIT,
                    severity="error",
                    message=(
                        f"{name_of(employee_id)}: {rules.format_minutes_pl(minutes)} pracy "
                        f"w tygodniu {rules.week_label(week)}. "
                        f"Limit to {rules.format_minutes_pl(limit)}."
                    ),
                    employee_id=employee_id,
                    day=date.fromisocalendar(week[0], week[1], 1),
                    details={
                        "week": rules.week_label(week),
                        "minutes": minutes,
                        "limit": limit,
                        "over_by": minutes - limit,
                    },
                )
            )
    return out


def _check_sequences(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    """HARD 3 + HARD 4 on real timestamps, including month boundaries."""
    shifts = ctx.shift_by_code
    out: list[Violation] = []
    for employee_id, items in rules.timeline(assignments, shifts).items():
        for previous, following in zip(items, items[1:], strict=False):
            if previous.day == following.day:
                continue  # reported by the one-shift-per-day check
            first = shifts[previous.shift_code]
            second = shifts[following.shift_code]
            legal, broken = rules.shift_pair_is_legal(
                first, previous.day, second, following.day, ctx.config
            )
            if legal:
                continue
            if not _touches_window(ctx, previous.day, following.day):
                continue
            gap = rules.rest_minutes(first.end_on(previous.day), second.start_on(following.day))
            if broken == rules.RULE_AFTER_NIGHT:
                message = (
                    f"{name_of(employee_id)}: po nocce {previous.day.isoformat()} "
                    f"({first.code}) nastepnego dnia moze byc tylko wolne lub noc, "
                    f"a zaplanowano {second.code} ({following.day.isoformat()})."
                )
            else:
                message = (
                    f"{name_of(employee_id)}: zmiana {previous.day.isoformat()} "
                    f"({first.code}) konczy sie o "
                    f"{first.end_on(previous.day).strftime('%d.%m %H:%M')}, a kolejna "
                    f"({second.code}) zaczyna sie o "
                    f"{second.start_on(following.day).strftime('%d.%m %H:%M')}. "
                    f"Odpoczynek: {rules.format_minutes_pl(gap)}. "
                    f"Wymagane minimum: {rules.format_minutes_pl(ctx.config.min_rest_minutes)}."
                )
            out.append(
                Violation(
                    code=broken or rules.RULE_MIN_REST,
                    severity="error",
                    message=message,
                    employee_id=employee_id,
                    day=following.day,
                    shift_code=second.code,
                    details={
                        "rest_minutes": gap,
                        "required_minutes": ctx.config.min_rest_minutes,
                        "previous_date": previous.day.isoformat(),
                        "previous_shift": first.code,
                    },
                )
            )
    return out


def _touches_window(ctx: PlanningContext, first_day: date, second_day: date) -> bool:
    return (
        ctx.first_day <= first_day <= ctx.last_day
        or ctx.first_day <= second_day <= ctx.last_day
    )


def _check_sundays(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    """HARD 5 - the cycle keeps running across month borders."""
    config = ctx.config
    n = config.sunday_free_every_n
    if n < 1:
        return []
    shifts = ctx.shift_by_code
    worked: set[tuple[int, date]] = set()
    for item in assignments:
        if item.day.weekday() == 6:
            worked.add((item.employee_id, item.day))
        elif config.sunday_includes_saturday_night and item.day.weekday() == 5:
            shift = shifts.get(item.shift_code)
            if shift and shift.is_night:
                worked.add((item.employee_id, item.day + timedelta(days=1)))

    lookaround = timedelta(days=7 * (n - 1))
    all_sundays = rules.sundays_between(ctx.first_day - lookaround, ctx.last_day + lookaround)
    windows = rules.sunday_windows(all_sundays, config)
    day_set = set(ctx.days)
    out: list[Violation] = []
    for employee in ctx.employees:
        for window in windows:
            if not any(sunday in day_set for sunday in window):
                continue
            if all((employee.id, sunday) in worked for sunday in window):
                out.append(
                    Violation(
                        code=rules.RULE_SUNDAY_OFF,
                        severity="error",
                        message=(
                            f"{employee.full_name} pracuje we wszystkie {n} kolejne niedziele "
                            f"({', '.join(s.isoformat() for s in window)}). "
                            f"Wymagana jest co najmniej jedna wolna niedziela w cyklu."
                        ),
                        employee_id=employee.id,
                        day=window[-1],
                        details={"sundays": [s.isoformat() for s in window]},
                    )
                )
    return out


def _check_fairness(statistics: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    totals = statistics.get("fairness", {})
    checks = (
        ("nights", WARN_NIGHT_FAIRNESS, "nocnych zmian", FAIRNESS_TOLERANCE_SHIFTS),
        ("weekend_shifts", WARN_WEEKEND_FAIRNESS, "dyzurow weekendowych", FAIRNESS_TOLERANCE_SHIFTS),
        ("holiday_shifts", WARN_HOLIDAY_FAIRNESS, "dyzurow swiatecznych", FAIRNESS_TOLERANCE_SHIFTS),
    )
    for key, code, label, tolerance in checks:
        spread = totals.get(key, {}).get("spread")
        if spread is None or spread <= tolerance:
            continue
        out.append(
            Violation(
                code=code,
                severity="warning",
                message=(
                    f"Nierowny podzial {label}: roznica miedzy pracownikami wynosi {spread}."
                ),
                details=totals.get(key, {}),
            )
        )
    minutes = totals.get("minutes", {})
    spread = minutes.get("spread")
    if spread is not None and spread > FAIRNESS_TOLERANCE_MINUTES:
        out.append(
            Violation(
                code=WARN_HOURS_FAIRNESS,
                severity="warning",
                message=(
                    "Nierowny podzial godzin: roznica miedzy pracownikami wynosi "
                    f"{rules.format_minutes_pl(spread)}."
                ),
                details=minutes,
            )
        )
    return out


def _check_preferences(
    ctx: PlanningContext, assignments: list[PlannedAssignment], name_of
) -> list[Violation]:
    from app.scheduler.optimizer import PREFERENCE_TO_SHIFT

    assigned = {(a.employee_id, a.day): a.shift_code for a in assignments}
    out: list[Violation] = []
    for (employee_id, day), declared in sorted(ctx.availability.items(), key=lambda kv: kv[0][1]):
        if day < ctx.first_day or day > ctx.last_day:
            continue
        code = assigned.get((employee_id, day))
        if declared is AvailabilityType.PREFERRED_OFF and code:
            out.append(
                Violation(
                    code=WARN_PREFERRED_OFF,
                    severity="warning",
                    message=(
                        f"{name_of(employee_id)} prosil(a) o wolne {day.isoformat()}, "
                        f"a otrzymal(a) zmiane {code}."
                    ),
                    employee_id=employee_id,
                    day=day,
                    shift_code=code,
                )
            )
            continue
        wanted = PREFERENCE_TO_SHIFT.get(declared)
        if wanted and code and code != wanted:
            out.append(
                Violation(
                    code=WARN_PREFERENCE,
                    severity="warning",
                    message=(
                        f"{name_of(employee_id)} preferuje zmiane {wanted} "
                        f"{day.isoformat()}, a otrzymal(a) {code}."
                    ),
                    employee_id=employee_id,
                    day=day,
                    shift_code=code,
                )
            )
    return out


def _build_checklist(errors: list[Violation], warnings: list[Violation]) -> list[dict[str, Any]]:
    """The KONTROLA GRAFIKU panel: one row per rule with its status."""
    error_codes = defaultdict(int)
    for item in errors:
        error_codes[item.code] += 1
    warning_codes = defaultdict(int)
    for item in warnings:
        warning_codes[item.code] += 1

    rows: list[dict[str, Any]] = []
    for code, label in CHECKS:
        count = error_codes.get(code, 0)
        rows.append(
            {
                "code": code,
                "label": label,
                "kind": "hard",
                "status": "ERROR" if count else "OK",
                "count": count,
            }
        )
    for code, label in SOFT_CHECKS:
        count = warning_codes.get(code, 0)
        rows.append(
            {
                "code": code,
                "label": label,
                "kind": "soft",
                "status": "WARNING" if count else "OK",
                "count": count,
            }
        )
    unlisted = set(error_codes) - {code for code, _ in CHECKS}
    for code in sorted(unlisted):
        rows.append(
            {
                "code": code,
                "label": code,
                "kind": "hard",
                "status": "ERROR",
                "count": error_codes[code],
            }
        )
    return rows
