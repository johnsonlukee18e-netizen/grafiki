"""Spec tests 11 and 12 - every fourth Sunday off, continuous across months."""
from __future__ import annotations

from datetime import date, timedelta

from app.scheduler import rules
from app.scheduler.models import RuleConfig, SundayRuleMode
from app.scheduler.validator import validate
from tests.conftest import make_context, plan

# Sundays in September 2026
SUNDAYS = [date(2026, 9, 6), date(2026, 9, 13), date(2026, 9, 20), date(2026, 9, 27)]


def test_september_2026_sundays():
    assert rules.sundays_between(date(2026, 9, 1), date(2026, 9, 30)) == SUNDAYS
    assert all(d.weekday() == 6 for d in SUNDAYS)


def test_working_four_consecutive_sundays_is_an_error(unstaffed_shifts):
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    assignments = [plan(1, sunday, "D") for sunday in SUNDAYS]
    result = validate(ctx, assignments)
    errors = [e for e in result.errors if e.code == rules.RULE_SUNDAY_OFF]
    assert len(errors) == 1
    assert errors[0].details["sundays"] == [s.isoformat() for s in SUNDAYS]
    assert not result.valid


def test_three_worked_sundays_and_one_free_is_fine(unstaffed_shifts):
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    assignments = [plan(1, sunday, "D") for sunday in SUNDAYS[:3]]
    result = validate(ctx, assignments)
    assert [e.code for e in result.errors] == []


def test_the_cycle_does_not_restart_at_the_month_border(unstaffed_shifts):
    """Two Sundays worked in August + two in September still breaks the rule."""
    august = [date(2026, 8, 23), date(2026, 8, 30)]
    ctx = make_context(
        shifts=unstaffed_shifts,
        employee_count=1,
        boundary=[plan(1, sunday, "D") for sunday in august],
    )
    result = validate(ctx, [plan(1, SUNDAYS[0], "D"), plan(1, SUNDAYS[1], "D")])
    errors = [e for e in result.errors if e.code == rules.RULE_SUNDAY_OFF]
    assert errors, "the August Sundays must still count"
    assert errors[0].details["sundays"] == [
        "2026-08-23", "2026-08-30", "2026-09-06", "2026-09-13"
    ]


def test_solver_respects_a_previous_month_that_already_used_three_sundays():
    """After three worked Sundays in August the first September Sunday is off."""
    august = [date(2026, 8, 16), date(2026, 8, 23), date(2026, 8, 30)]
    ctx = make_context(
        days=[date(2026, 9, d) for d in range(1, 8)],
        employee_count=13,
        boundary=[plan(1, sunday, "D") for sunday in august],
    )
    from app.scheduler.solver import generate

    result = generate(ctx)
    assert result.success, result.message
    worked_sunday = any(
        a.employee_id == 1 and a.day == SUNDAYS[0] for a in result.assignments
    )
    assert not worked_sunday, "employee 1 had to get the fourth Sunday off"


def test_configurable_cycle_length(unstaffed_shifts):
    config = RuleConfig(sunday_free_every_n=2)
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1, config=config)
    result = validate(ctx, [plan(1, SUNDAYS[0], "D"), plan(1, SUNDAYS[1], "D")])
    assert rules.RULE_SUNDAY_OFF in {e.code for e in result.errors}


def test_block_mode_uses_the_configured_anchor():
    """BLOCK mode groups Sundays into fixed blocks counted from the anchor."""
    config = RuleConfig(
        sunday_rule_mode=SundayRuleMode.BLOCK, sunday_cycle_anchor=date(2026, 1, 4)
    )
    sundays = rules.sundays_between(date(2026, 1, 4), date(2026, 2, 22))
    windows = rules.sunday_windows(sundays, config)
    assert windows[0] == [date(2026, 1, 4), date(2026, 1, 11), date(2026, 1, 18), date(2026, 1, 25)]
    assert windows[1][0] == date(2026, 2, 1)
    # Blocks never overlap, unlike the sliding windows.
    assert len(windows) == 2


def test_sliding_mode_produces_overlapping_windows():
    config = RuleConfig(sunday_rule_mode=SundayRuleMode.SLIDING)
    sundays = rules.sundays_between(date(2026, 1, 4), date(2026, 2, 1))
    windows = rules.sunday_windows(sundays, config)
    assert len(windows) == len(sundays) - 3
    assert windows[0][0] == date(2026, 1, 4)
    assert windows[1][0] == date(2026, 1, 11)


def test_saturday_night_can_optionally_count_as_working_sunday(unstaffed_shifts):
    config = RuleConfig(sunday_includes_saturday_night=True)
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1, config=config)
    saturdays = [sunday - timedelta(days=1) for sunday in SUNDAYS]
    result = validate(ctx, [plan(1, saturday, "N") for saturday in saturdays])
    assert rules.RULE_SUNDAY_OFF in {e.code for e in result.errors}

    default_ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    default_result = validate(default_ctx, [plan(1, saturday, "N") for saturday in saturdays])
    assert rules.RULE_SUNDAY_OFF not in {e.code for e in default_result.errors}
