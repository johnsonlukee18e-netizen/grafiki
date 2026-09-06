"""Spec tests 1, 2 and 16 - the 37:55 weekly limit and month-boundary weeks."""
from __future__ import annotations

from datetime import date

import pytest

from app.scheduler import rules
from app.scheduler.models import RuleConfig
from app.scheduler.validator import validate
from tests.conftest import make_context, plan

WEEKLY_LIMIT = 2275  # 37 h 55 min


def test_limit_constant_is_37h55():
    assert RuleConfig().weekly_minutes_limit == WEEKLY_LIMIT
    assert rules.format_minutes(WEEKLY_LIMIT) == "37:55"
    assert rules.format_minutes_pl(WEEKLY_LIMIT) == "37 h 55 min"


def test_exactly_at_the_limit_is_accepted(unstaffed_shifts):
    """3 x D (2160) + 115 min short of the cap: 3 x D + 0 = 2160 <= 2275."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    # Monday 2026-09-07 .. Wednesday 2026-09-09 -> three day shifts.
    assignments = [
        plan(1, date(2026, 9, 7), "D"),
        plan(1, date(2026, 9, 9), "D"),
        plan(1, date(2026, 9, 11), "D"),
    ]
    total = 3 * 720
    assert total <= WEEKLY_LIMIT
    result = validate(ctx, assignments)
    assert [e.message for e in result.errors] == []


def test_exact_limit_boundary_is_not_a_violation():
    """A week summing to exactly the limit must pass; one minute more must not."""
    config = RuleConfig()
    assert not rules.weekly_limit_exceeded(WEEKLY_LIMIT, config)
    assert rules.weekly_limit_exceeded(WEEKLY_LIMIT + 1, config)


def test_exceeding_the_limit_is_an_error(unstaffed_shifts):
    """4 x D = 2880 minutes in one Monday-Sunday week."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    assignments = [
        plan(1, date(2026, 9, 7), "D"),
        plan(1, date(2026, 9, 9), "D"),
        plan(1, date(2026, 9, 11), "D"),
        plan(1, date(2026, 9, 13), "D"),
    ]
    result = validate(ctx, assignments)
    errors = [e for e in result.errors if e.code == rules.RULE_WEEKLY_LIMIT]
    assert len(errors) == 1
    assert errors[0].details["minutes"] == 4 * 720
    assert errors[0].details["over_by"] == 4 * 720 - WEEKLY_LIMIT
    assert "37 h 55 min" in errors[0].message
    assert not result.valid


def test_week_crossing_the_month_border_counts_both_months(unstaffed_shifts):
    """August 31 (Monday) belongs to the same week as September 1-6."""
    ctx = make_context(
        shifts=unstaffed_shifts,
        employee_count=1,
        boundary=[plan(1, date(2026, 8, 31), "D")],  # previous month, 720 min
    )
    # Two more day shifts inside September keep us at 2160 - still legal.
    ok = validate(ctx, [plan(1, date(2026, 9, 2), "D"), plan(1, date(2026, 9, 4), "D")])
    assert [e.code for e in ok.errors] == []

    # A third one inside September pushes the shared week to 2880 minutes.
    over = validate(
        ctx,
        [
            plan(1, date(2026, 9, 2), "D"),
            plan(1, date(2026, 9, 4), "D"),
            plan(1, date(2026, 9, 6), "D"),
        ],
    )
    errors = [e for e in over.errors if e.code == rules.RULE_WEEKLY_LIMIT]
    assert len(errors) == 1, [e.message for e in over.errors]
    assert errors[0].details["week"] == "2026-08-31 - 2026-09-06"
    assert errors[0].details["minutes"] == 2880


def test_iso_weeks_run_monday_to_sunday():
    monday = date(2026, 8, 31)
    sunday = date(2026, 9, 6)
    assert monday.weekday() == 0 and sunday.weekday() == 6
    assert rules.iso_week_key(monday) == rules.iso_week_key(sunday)
    assert rules.iso_week_key(sunday) != rules.iso_week_key(date(2026, 9, 7))


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, "0:00"), (455, "7:35"), (720, "12:00"), (2275, "37:55"), (2160, "36:00")],
)
def test_minutes_are_formatted_without_floats(minutes, expected):
    assert rules.format_minutes(minutes) == expected
