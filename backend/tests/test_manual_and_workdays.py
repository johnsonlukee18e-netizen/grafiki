"""Morning shift only on working days, and RECZNE UKLADANIE (manual building)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.models.enums import AvailabilityType
from app.scheduler import rules
from app.scheduler.models import RuleConfig
from app.scheduler.solver import generate
from app.scheduler.validator import validate
from tests.conftest import ALL_SHIFTS, make_context, plan

YEAR, MONTH = 2026, 9
WEEK = [date(2026, 9, d) for d in range(7, 14)]  # Mon 7 .. Sun 13
HOLIDAY = date(2026, 9, 9)  # a Wednesday, made a holiday for the test


def workday_shifts():
    return [replace(s, workdays_only=(s.code == "R")) for s in ALL_SHIFTS]


# --- core: R only on working days ----------------------------------------
def test_solver_never_plans_a_morning_on_weekends_or_holidays():
    ctx = make_context(
        employee_count=14,
        shifts=workday_shifts(),
        days=WEEK,
        holidays={HOLIDAY: "Test"},
        config=RuleConfig(solver_time_limit_seconds=10, solver_workers=4),
    )
    result = generate(ctx)
    assert result.success, result.message
    mornings = {a.day for a in result.assignments if a.shift_code == "R"}
    assert mornings.isdisjoint({HOLIDAY, date(2026, 9, 12), date(2026, 9, 13)})
    assert date(2026, 9, 7) in mornings  # still staffed on a normal Monday
    report = validate(ctx, result.assignments)
    assert report.valid, [e.message for e in report.errors]


def test_validator_flags_a_morning_on_sunday_but_not_missing_staff():
    sunday = date(2026, 9, 13)
    ctx = make_context(employee_count=6, shifts=workday_shifts(), days=[sunday])
    report = validate(ctx, [plan(1, sunday, "R")])
    codes = {(e.code, e.shift_code) for e in report.errors}
    assert (rules.RULE_SHIFT_DAY, "R") in codes
    # R does not exist on Sunday, so "R understaffed" must not be reported.
    assert (rules.RULE_MIN_STAFF, "R") not in codes


def test_morning_preference_on_a_weekend_is_not_a_warning():
    saturday = date(2026, 9, 12)
    ctx = make_context(
        employee_count=6,
        shifts=[replace(s, minimum_staff=0) for s in workday_shifts()],
        days=[saturday],
        availability={(1, saturday): AvailabilityType.PREFERRED_MORNING},
    )
    report = validate(ctx, [plan(1, saturday, "D")])
    assert not [w for w in report.warnings if w.code == "PREFERENCE_IGNORED"]


def test_weekend_capacity_check_ignores_the_morning_shift():
    # 7 * (2*720 + 2*720) + 5 * 2*455 = 24 710 min; 11 people * 2275 = 25 025.
    # With R counted on weekends (26 530) the week would be reported impossible.
    ctx = make_context(employee_count=11, shifts=workday_shifts(), days=WEEK)
    from app.scheduler import diagnostics

    assert not [d for d in diagnostics.pre_solve_checks(ctx) if d.code == "WEEK_CAPACITY"]


# --- API: manual building -------------------------------------------------
def _start(client, year=YEAR, month=MONTH):
    response = client.post("/api/schedules/manual", json={"year": year, "month": month})
    assert response.status_code == 200, response.text
    return response.json()


def _cells(client, schedule_id, cells):
    return client.put(f"/api/schedules/{schedule_id}/cells", json={"cells": cells})


def test_seed_marks_the_morning_as_working_days_only(logged_in):
    shifts = {s["code"]: s for s in logged_in.get("/api/settings/shifts").json()}
    assert shifts["R"]["workdays_only"] is True
    assert shifts["D"]["workdays_only"] is False


def test_manual_building_flow(logged_in):
    schedule = _start(logged_in)
    assert schedule["mode"] == "MANUAL"
    assert schedule["status"] == "DRAFT"
    sid = schedule["id"]
    employee = logged_in.get("/api/employees").json()[0]

    # Free editing: a lone shift breaks staffing everywhere, yet it is saved.
    response = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "D"},
        {"employee_id": employee["id"], "date": "2026-09-13", "shift_code": "R"},  # Sunday
    ])
    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 2
    assert response.json()["schedule"]["status"] == "DRAFT"

    # Opening the page does not judge a draft.
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert grid["validation"] is None
    assert grid["schedule"]["status"] == "DRAFT"
    assert len(grid["assignments"]) == 2

    # "Wyslij do sprawdzenia" lists what must be fixed.
    checked = logged_in.post(f"/api/schedules/{sid}/validate").json()
    assert checked["schedule"]["status"] == "INVALID"
    codes = {e["code"] for e in checked["validation"]["errors"]}
    assert {"MIN_STAFF", "SHIFT_NOT_ON_DAY"} <= codes
    assert logged_in.post(f"/api/schedules/{sid}/approve").status_code == 409

    # The first edit after a check keeps the checked state in the history.
    again = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-13", "shift_code": None},
    ])
    assert again.status_code == 200
    assert again.json()["schedule"]["status"] == "DRAFT"
    assert again.json()["schedule"]["version"] == 2
    history = logged_in.get(f"/api/schedules/{sid}/history").json()
    assert [h["version"] for h in history] == [1]

    # Further draft edits do not flood the history.
    _cells(logged_in, sid, [{"employee_id": employee["id"], "date": "2026-09-08", "shift_code": "N"}])
    assert len(logged_in.get(f"/api/schedules/{sid}/history").json()) == 1

    # Setting a cell to what it already is changes nothing.
    same = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-08", "shift_code": "N"},
    ])
    assert same.json()["changed"] == 0

    audit = {row["action"] for row in logged_in.get("/api/audit").json()}
    assert {"SCHEDULE_MODE_CHANGED", "SCHEDULE_MANUAL_EDIT"} <= audit


def test_manual_cells_validation_errors(logged_in):
    sid = _start(logged_in)["id"]
    employee = logged_in.get("/api/employees").json()[0]
    outside = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-10-01", "shift_code": "D"},
    ])
    assert outside.status_code == 400
    duplicate = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "D"},
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "N"},
    ])
    assert duplicate.status_code == 400
    unknown = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "X"},
    ])
    assert unknown.status_code == 400
    off = _cells(logged_in, sid, [
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "W"},
    ])
    assert off.status_code == 200 and off.json()["changed"] == 0


def test_cells_are_refused_for_a_generated_schedule(logged_in):
    body = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH}).json()
    assert body["success"], body["solver"]
    assert body["schedule"]["mode"] == "AUTO"
    employee = logged_in.get("/api/employees").json()[0]
    response = _cells(logged_in, body["schedule"]["id"], [
        {"employee_id": employee["id"], "date": "2026-09-07", "shift_code": "D"},
    ])
    assert response.status_code == 409


def test_manual_can_start_from_a_generated_roster_and_switch_back(logged_in):
    body = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH}).json()
    generated = len(logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["assignments"])

    schedule = _start(logged_in)
    assert schedule["mode"] == "MANUAL"
    assert schedule["status"] == "VALID"  # kept, the roster is unchanged so far
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert len(grid["assignments"]) == generated

    again = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH}).json()
    assert again["success"]
    assert again["schedule"]["mode"] == "AUTO"
    assert body["schedule"]["id"] == again["schedule"]["id"]


def test_manual_is_refused_for_an_approved_month(logged_in):
    body = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH}).json()
    assert logged_in.post(f"/api/schedules/{body['schedule']['id']}/approve").status_code == 200
    response = logged_in.post("/api/schedules/manual", json={"year": YEAR, "month": MONTH})
    assert response.status_code == 409


def test_a_checked_manual_schedule_can_be_approved(logged_in):
    body = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH}).json()
    assert body["success"], body["solver"]
    sid = _start(logged_in)["id"]
    cell = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["assignments"][0]
    original = cell["shift_code"]
    other = "N" if original != "N" else "D"
    where = {"employee_id": cell["employee_id"], "date": cell["work_date"]}

    # Change a cell and put it back: a draft again, identical to the valid roster.
    assert _cells(logged_in, sid, [{**where, "shift_code": other}]).status_code == 200
    assert _cells(logged_in, sid, [{**where, "shift_code": original}]).status_code == 200
    assert logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["schedule"]["status"] == "DRAFT"

    checked = logged_in.post(f"/api/schedules/{sid}/validate").json()
    assert checked["validation"]["valid"], checked["validation"]["errors"]
    approved = logged_in.post(f"/api/schedules/{sid}/approve")
    assert approved.status_code == 200
    assert approved.json()["schedule"]["status"] == "APPROVED"
