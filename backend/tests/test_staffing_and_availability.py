"""Spec tests 9 and 10 - minimum staffing and hard unavailability."""
from __future__ import annotations

from datetime import date

from app.models.enums import AvailabilityType
from app.scheduler import rules
from app.scheduler.solver import generate
from app.scheduler.validator import validate
from tests.conftest import make_context, plan

SEPT = [date(2026, 9, d) for d in range(1, 4)]


def test_minimum_two_people_per_shift_is_enforced():
    ctx = make_context(days=SEPT, employee_count=6)
    only_one = [plan(1, SEPT[0], "D")]
    result = validate(ctx, only_one)
    understaffed = [e for e in result.errors if e.code == rules.RULE_MIN_STAFF]
    # every shift of every day is short of staff
    assert len(understaffed) == len(SEPT) * 3
    first = next(e for e in understaffed if e.day == SEPT[0] and e.shift_code == "D")
    assert first.details == {"required": 2, "actual": 1}
    assert "minimum 2" in first.message


def test_two_people_satisfy_the_minimum():
    ctx = make_context(days=[SEPT[0]], employee_count=6)
    assignments = [
        plan(1, SEPT[0], "D"), plan(2, SEPT[0], "D"),
        plan(3, SEPT[0], "R"), plan(4, SEPT[0], "R"),
        plan(5, SEPT[0], "N"), plan(6, SEPT[0], "N"),
    ]
    result = validate(ctx, assignments)
    assert [e.message for e in result.errors] == []


def test_configurable_minimum_is_respected(shifts):
    """Raising minimum_staff to 3 immediately makes a 2-person shift invalid."""
    from app.scheduler.models import ShiftDef

    stricter = [
        ShiftDef(s.id, s.code, s.name, s.start_time, s.end_time, s.duration_minutes,
                 s.crosses_midnight, 3)
        for s in shifts
    ]
    ctx = make_context(days=[SEPT[0]], employee_count=8, shifts=stricter)
    assignments = [
        plan(1, SEPT[0], "D"), plan(2, SEPT[0], "D"),
        plan(3, SEPT[0], "R"), plan(4, SEPT[0], "R"), plan(5, SEPT[0], "R"),
        plan(6, SEPT[0], "N"), plan(7, SEPT[0], "N"), plan(8, SEPT[0], "N"),
    ]
    result = validate(ctx, assignments)
    codes = [(e.shift_code, e.details["required"], e.details["actual"]) for e in result.errors]
    assert codes == [("D", 3, 2)]


def test_unavailable_employee_may_not_be_scheduled(unstaffed_shifts):
    ctx = make_context(
        shifts=unstaffed_shifts,
        employee_count=2,
        availability={(1, SEPT[0]): AvailabilityType.UNAVAILABLE},
    )
    result = validate(ctx, [plan(1, SEPT[0], "D")])
    errors = [e for e in result.errors if e.code == rules.RULE_UNAVAILABLE]
    assert len(errors) == 1
    assert "niedostepnosc" in errors[0].message
    assert not result.valid


def test_solver_never_assigns_an_unavailable_employee():
    """The generator must route around a hard unavailability, not ignore it."""
    ctx = make_context(
        days=[date(2026, 9, d) for d in range(1, 8)],
        employee_count=13,
        availability={(1, date(2026, 9, 3)): AvailabilityType.UNAVAILABLE},
    )
    result = generate(ctx)
    assert result.success, result.message
    assert not any(
        a.employee_id == 1 and a.day == date(2026, 9, 3) for a in result.assignments
    )
    assert validate(ctx, result.assignments).valid


def test_preferences_are_soft_not_hard(unstaffed_shifts):
    """PREFERRED_OFF that is ignored produces a warning, never an error."""
    ctx = make_context(
        shifts=unstaffed_shifts,
        employee_count=2,
        availability={(1, SEPT[0]): AvailabilityType.PREFERRED_OFF},
    )
    result = validate(ctx, [plan(1, SEPT[0], "D")])
    assert result.valid
    assert [w.code for w in result.warnings if w.day == SEPT[0]] == ["PREFERRED_OFF_IGNORED"]


def test_employee_cannot_work_before_being_employed(unstaffed_shifts):
    from tests.conftest import make_employee

    ctx = make_context(shifts=unstaffed_shifts, employee_count=1)
    ctx.employees = [make_employee(1, employed=date(2026, 9, 15))]
    result = validate(ctx, [plan(1, date(2026, 9, 1), "D")])
    assert rules.RULE_NOT_EMPLOYED in {e.code for e in result.errors}


def test_infeasible_month_reports_reasons_not_a_bare_failure():
    """Ten people cannot cover 2/2/2 within 37:55 - say so, do not relax."""
    ctx = make_context(employee_count=10)
    result = generate(ctx)
    assert not result.success
    assert result.status == "INFEASIBLE"
    assert result.diagnostics, "the manager must be told why"
    assert any(d.code == "WEEK_CAPACITY" for d in result.diagnostics)
    worst = next(d for d in result.diagnostics if d.code == "WEEK_CAPACITY")
    assert worst.details["missing_minutes"] > 0
    assert worst.details["employees_needed"] >= 12
    assert result.suggestions
