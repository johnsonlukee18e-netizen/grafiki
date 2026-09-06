"""Spec tests 3-8 - the 11 hour rest and what may follow a night shift."""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.scheduler import rules
from app.scheduler.models import RuleConfig, ShiftDef
from app.scheduler.validator import validate
from tests.conftest import DAY, MORNING, NIGHT, make_context, plan

CONFIG = RuleConfig()


def test_exactly_eleven_hours_of_rest_is_allowed():
    """19:00 -> 06:00 next day is exactly 11 h and must pass."""
    end = datetime(2026, 9, 10, 19, 0)
    start = datetime(2026, 9, 11, 6, 0)
    assert rules.rest_minutes(end, start) == 660
    assert rules.rest_is_sufficient(end, start, CONFIG)


def test_ten_hours_fifty_nine_minutes_is_rejected():
    end = datetime(2026, 9, 10, 19, 0)
    start = datetime(2026, 9, 11, 5, 59)
    assert rules.rest_minutes(end, start) == 659
    assert not rules.rest_is_sufficient(end, start, CONFIG)


def test_rest_is_measured_on_real_timestamps():
    """A night ends the following morning, not on its own work date."""
    night_end = NIGHT.end_on(date(2026, 9, 10))
    assert night_end == datetime(2026, 9, 11, 7, 0)
    assert NIGHT.start_on(date(2026, 9, 10)) == datetime(2026, 9, 10, 19, 0)


def test_night_then_free_is_allowed(unstaffed_shifts):
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    result = validate(ctx, [plan(1, date(2026, 9, 10), "N")])
    assert result.valid


def test_night_then_night_is_allowed(unstaffed_shifts):
    """N -> N gives 12 h of rest and is explicitly permitted."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    result = validate(ctx, [plan(1, date(2026, 9, 10), "N"), plan(1, date(2026, 9, 11), "N")])
    assert result.valid, [e.message for e in result.errors]


@pytest.mark.parametrize("code", ["R", "D"])
def test_night_then_morning_or_day_is_an_error(unstaffed_shifts, code):
    """Spec tests 7 and 8: after a night only a night or a free day may follow."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    result = validate(ctx, [plan(1, date(2026, 9, 10), "N"), plan(1, date(2026, 9, 11), code)])
    assert not result.valid
    codes = {e.code for e in result.errors}
    assert rules.RULE_AFTER_NIGHT in codes
    message = next(e.message for e in result.errors if e.code == rules.RULE_AFTER_NIGHT)
    assert "po nocce" in message
    assert code in message


def test_after_night_rule_only_binds_the_very_next_day(unstaffed_shifts):
    """N on the 10th and D on the 12th is fine (24 h of rest)."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    result = validate(ctx, [plan(1, date(2026, 9, 10), "N"), plan(1, date(2026, 9, 12), "D")])
    assert result.valid, [e.message for e in result.errors]


def test_rest_violation_message_is_human_readable():
    """A custom evening shift ending at 19:00 followed by a 05:30 start."""
    early = ShiftDef(9, "E", "Wczesna", time(5, 30), time(13, 0), 450, False, 0)
    evening = ShiftDef(8, "P", "Popoludnie", time(7, 0), time(19, 0), 720, False, 0)
    ctx = make_context(shifts=[early, evening], employee_count=1)
    result = validate(ctx, [plan(1, date(2026, 9, 10), "P"), plan(1, date(2026, 9, 11), "E")])
    error = next(e for e in result.errors if e.code == rules.RULE_MIN_REST)
    assert error.details["rest_minutes"] == 630
    assert "10 h 30 min" in error.message
    assert "11 h" in error.message


def test_night_before_the_month_blocks_the_first_day(unstaffed_shifts):
    """The rule survives the month border: N on Aug 31 -> D on Sep 1 is illegal."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1,
                       boundary=[plan(1, date(2026, 8, 31), "N")])
    result = validate(ctx, [plan(1, date(2026, 9, 1), "D")])
    assert rules.RULE_AFTER_NIGHT in {e.code for e in result.errors}


def test_night_at_the_end_of_the_month_blocks_the_next_month(unstaffed_shifts):
    """N on Sep 30 -> R on Oct 1 (already planned) must be reported."""
    ctx = make_context(shifts=unstaffed_shifts, employee_count=1,
                       boundary=[plan(1, date(2026, 10, 1), "R")])
    result = validate(ctx, [plan(1, date(2026, 9, 30), "N")])
    assert rules.RULE_AFTER_NIGHT in {e.code for e in result.errors}


def test_shift_pair_helper_names_the_broken_rule():
    legal, code = rules.shift_pair_is_legal(NIGHT, date(2026, 9, 10), DAY, date(2026, 9, 11), CONFIG)
    assert not legal and code == rules.RULE_AFTER_NIGHT

    # D ends at 19:00, R starts at 07:00 the next day -> 12 h, perfectly legal.
    legal, code = rules.shift_pair_is_legal(DAY, date(2026, 9, 10), MORNING, date(2026, 9, 11), CONFIG)
    assert legal and code is None

    legal, code = rules.shift_pair_is_legal(NIGHT, date(2026, 9, 10), NIGHT, date(2026, 9, 11), CONFIG)
    assert legal and code is None
