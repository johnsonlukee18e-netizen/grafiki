"""Spec tests 13, 14 and 15 - Polish holidays and fair distribution."""
from __future__ import annotations

from datetime import date

import pytest

from app.scheduler.solver import generate
from app.scheduler.statistics import build_statistics
from app.scheduler.validator import validate
from app.services.holidays_pl import easter_sunday, polish_holidays
from tests.conftest import make_context, plan


# --- 13. Polish holidays --------------------------------------------------
@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
     (2027, date(2027, 3, 28)), (2030, date(2030, 4, 21))],
)
def test_easter_is_computed_for_any_year(year, expected):
    assert easter_sunday(year) == expected


def test_polish_holidays_2026():
    days = {h.day: h.name for h in polish_holidays(2026)}
    assert len(days) == 13
    for expected in (
        date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 5), date(2026, 4, 6),
        date(2026, 5, 1), date(2026, 5, 3), date(2026, 5, 24), date(2026, 6, 4),
        date(2026, 8, 15), date(2026, 11, 1), date(2026, 11, 11),
        date(2026, 12, 25), date(2026, 12, 26),
    ):
        assert expected in days


def test_holidays_work_for_a_far_future_year():
    """Nothing is hardcoded to 2026."""
    days = [h.day for h in polish_holidays(2031)]
    assert date(2031, 1, 1) in days
    assert date(2031, 4, 13) in days  # Easter Sunday 2031
    assert len(days) == 13


def test_epiphany_only_counts_from_2011():
    assert date(2010, 1, 6) not in [h.day for h in polish_holidays(2010)]
    assert date(2011, 1, 6) in [h.day for h in polish_holidays(2011)]


def test_holidays_are_visible_in_statistics(unstaffed_shifts):
    holiday = date(2026, 11, 11)
    ctx = make_context(
        year=2026, month=11, shifts=unstaffed_shifts, employee_count=2,
        holidays={holiday: "Narodowe Swieto Niepodleglosci"},
    )
    stats = build_statistics(ctx, [plan(1, holiday, "D")])
    row = next(r for r in stats["employees"] if r["employee_id"] == 1)
    assert row["holiday_shifts"] == 1
    day_row = next(d for d in stats["coverage"] if d["date"] == holiday.isoformat())
    assert day_row["is_holiday"] and day_row["holiday_name"]


# --- 14 & 15. fairness ----------------------------------------------------
@pytest.fixture(scope="module")
def solved_week():
    ctx = make_context(days=[date(2026, 9, d) for d in range(1, 15)], employee_count=14)
    result = generate(ctx)
    assert result.success, result.message
    return ctx, result


def test_nights_are_shared_evenly(solved_week):
    ctx, result = solved_week
    stats = build_statistics(ctx, result.assignments)
    nights = [row["nights"] for row in stats["employees"]]
    assert max(nights) - min(nights) <= 1, nights


def test_weekends_are_shared_evenly(solved_week):
    ctx, result = solved_week
    stats = build_statistics(ctx, result.assignments)
    weekends = [row["weekend_shifts"] for row in stats["employees"]]
    assert max(weekends) - min(weekends) <= 1, weekends


def test_generated_schedule_passes_the_independent_validator(solved_week):
    ctx, result = solved_week
    report = validate(ctx, result.assignments)
    assert report.valid, [e.message for e in report.errors][:5]


def test_uneven_distribution_raises_a_warning(unstaffed_shifts):
    """The validator flags an unfair roster even when it is technically legal."""
    days = [date(2026, 9, d) for d in range(1, 15)]
    ctx = make_context(days=days, shifts=unstaffed_shifts, employee_count=4)
    # Employee 1 takes six nights, everybody else none.
    assignments = [plan(1, date(2026, 9, d), "N") for d in (1, 3, 5, 7, 9, 11)]
    result = validate(ctx, assignments)
    assert result.valid  # no hard rule broken
    assert "NIGHT_FAIRNESS" in {w.code for w in result.warnings}


def test_solver_is_reproducible_with_a_single_worker():
    """A fixed seed plus one worker must give the exact same roster twice."""
    from app.scheduler.models import RuleConfig

    config = RuleConfig(solver_time_limit_seconds=20, solver_seed=7, solver_workers=1)

    def run():
        ctx = make_context(
            days=[date(2026, 9, d) for d in range(1, 9)], employee_count=13, config=config
        )
        result = generate(ctx)
        assert result.success, result.message
        return [(a.employee_id, a.day, a.shift_code) for a in result.assignments]

    assert run() == run()
