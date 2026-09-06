"""Per-employee and per-day statistics for a finished roster."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.scheduler import rules
from app.scheduler.models import PlannedAssignment, PlanningContext


def _spread(values: list[int]) -> dict[str, int]:
    if not values:
        return {"min": 0, "max": 0, "spread": 0, "avg": 0}
    return {
        "min": min(values),
        "max": max(values),
        "spread": max(values) - min(values),
        "avg": round(sum(values) / len(values)),
    }


def build_statistics(
    ctx: PlanningContext, assignments: list[PlannedAssignment]
) -> dict[str, Any]:
    """Everything the statistics panel and the PDF need."""
    shifts = ctx.shift_by_code
    per_employee: dict[int, dict[str, Any]] = {}
    days_in_month = len(ctx.days)

    grouped: dict[int, list[PlannedAssignment]] = defaultdict(list)
    for item in assignments:
        grouped[item.employee_id].append(item)

    for employee in ctx.employees:
        items = grouped.get(employee.id, [])
        by_code = defaultdict(int)
        minutes = 0
        saturdays = nights = sundays = holidays = 0
        weekend_days: set[date] = set()
        for item in items:
            shift = shifts.get(item.shift_code)
            if shift is None:
                continue
            by_code[item.shift_code] += 1
            minutes += shift.duration_minutes
            if shift.is_night:
                nights += 1
            weekday = item.day.weekday()
            if weekday == 5:
                saturdays += 1
                weekend_days.add(item.day)
            elif weekday == 6:
                sundays += 1
                weekend_days.add(item.day)
            if ctx.is_holiday(item.day):
                holidays += 1

        weekly = rules.worked_minutes_by_week(items, shifts)
        per_employee[employee.id] = {
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "role": employee.role.value,
            "shifts": {code: by_code.get(code, 0) for code in shifts},
            "total_shifts": sum(by_code.values()),
            "minutes": minutes,
            "hours_label": rules.format_minutes(minutes),
            "limit_label": rules.format_minutes(ctx.config.weekly_minutes_limit),
            "nights": nights,
            "saturdays": saturdays,
            "sundays": sundays,
            "weekend_shifts": len(weekend_days),
            "holiday_shifts": holidays,
            "days_off": days_in_month - sum(by_code.values()),
            "weeks": [
                {
                    "week": rules.week_label(week),
                    "minutes": value,
                    "label": rules.format_minutes(value),
                    "limit_exceeded": rules.weekly_limit_exceeded(value, ctx.config),
                }
                for (_employee_id, week), value in sorted(weekly.items(), key=lambda kv: kv[0][1])
            ],
        }

    coverage = _coverage(ctx, assignments)
    values = list(per_employee.values())
    fairness = {
        "nights": _spread([v["nights"] for v in values]),
        "weekend_shifts": _spread([v["weekend_shifts"] for v in values]),
        "holiday_shifts": _spread([v["holiday_shifts"] for v in values]),
        "minutes": _spread([v["minutes"] for v in values]),
        "total_shifts": _spread([v["total_shifts"] for v in values]),
    }

    return {
        "employees": values,
        "fairness": fairness,
        "coverage": coverage,
        "totals": {
            "assignments": len(assignments),
            "minutes": sum(v["minutes"] for v in values),
            "hours_label": rules.format_minutes(sum(v["minutes"] for v in values)),
            "employees": len(values),
            "days": days_in_month,
            "holidays": len(ctx.holidays),
        },
    }


def _coverage(ctx: PlanningContext, assignments: list[PlannedAssignment]) -> list[dict[str, Any]]:
    """Head count per day and shift, flagged when below the minimum."""
    counts: dict[tuple[date, str], int] = defaultdict(int)
    for item in assignments:
        counts[(item.day, item.shift_code)] += 1
    out: list[dict[str, Any]] = []
    for day in ctx.days:
        row = {
            "date": day.isoformat(),
            "weekday": day.weekday(),
            "is_weekend": day.weekday() >= 5,
            "is_holiday": ctx.is_holiday(day),
            "holiday_name": ctx.holidays.get(day),
            "shifts": {},
        }
        for shift in ctx.shifts:
            actual = counts[(day, shift.code)]
            row["shifts"][shift.code] = {
                "count": actual,
                "required": shift.minimum_staff,
                "understaffed": actual < shift.minimum_staff,
            }
        out.append(row)
    return out
