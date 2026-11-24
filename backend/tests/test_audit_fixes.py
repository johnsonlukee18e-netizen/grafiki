"""Regression tests for the production-readiness audit.

Covers: nurses on every shift, inactive employees in past months, the
"same violation, only worse" edit gate, partial-update payloads, the solver
time cap, PDF export with Polish names, restoring old versions, generation
locking and keeping validation fresh.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.models.enums import EmployeeRole
from app.scheduler import diagnostics, rules
from app.scheduler.models import EmployeeCtx, RuleConfig
from app.scheduler.solver import GenerationResult, generate
from app.scheduler.validator import validate
from tests.conftest import ALL_SHIFTS, make_context, plan

YEAR, MONTH = 2026, 9
FIRST_WEEK = [date(2026, 9, d) for d in range(7, 14)]  # Monday..Sunday


def with_nurses(minimum_nurses: int):
    return [replace(s, minimum_nurses=minimum_nurses) for s in ALL_SHIFTS]


# --- minimum nurses: core -------------------------------------------------
def test_solver_puts_a_nurse_on_every_shift():
    ctx = make_context(
        employee_count=16,
        shifts=with_nurses(1),
        days=FIRST_WEEK,
        config=RuleConfig(solver_time_limit_seconds=10, solver_workers=4),
    )
    result = generate(ctx)
    assert result.success, result.message
    nurses = {e.id for e in ctx.employees if e.is_nurse}
    for day in FIRST_WEEK:
        for shift in ALL_SHIFTS:
            crew = [
                a.employee_id
                for a in result.assignments
                if a.day == day and a.shift_code == shift.code
            ]
            assert any(e in nurses for e in crew), (day, shift.code, crew)
    report = validate(ctx, result.assignments)
    assert not [e for e in report.errors if e.code == rules.RULE_MIN_NURSES]


def test_validator_flags_a_shift_without_a_nurse():
    ctx = make_context(employee_count=8, shifts=with_nurses(1), days=[date(2026, 9, 7)])
    care_workers = [e.id for e in ctx.employees if not e.is_nurse]
    assert len(care_workers) == 2
    day = date(2026, 9, 7)
    roster = [plan(care_workers[0], day, "D"), plan(care_workers[1], day, "D")]
    report = validate(ctx, roster)
    codes = {(e.code, e.shift_code) for e in report.errors}
    assert (rules.RULE_MIN_NURSES, "D") in codes


def test_nurse_shortage_is_explained_before_solving():
    ctx = make_context(employee_count=8, shifts=with_nurses(2), days=FIRST_WEEK)
    # 6 nurses available, but 3 shifts x 2 nurses = 6 per day and only
    # 2275 minutes per nurse per week -> the week cannot be covered.
    result = generate(ctx)
    assert not result.success
    codes = {d.code for d in result.diagnostics}
    assert "WEEK_NURSE_CAPACITY" in codes
    assert any("pielęgniar" in s for s in result.suggestions)


def test_nurse_rule_off_by_default():
    ctx = make_context(employee_count=4, days=[date(2026, 9, 7)])
    assert all(s.minimum_nurses == 0 for s in ctx.shifts)
    assert not diagnostics._daily_nurses(ctx)


# --- inactive employees ---------------------------------------------------
def _inactive_context(today: date):
    ctx = make_context(employee_count=2, days=[date(2026, 9, 7)], shifts=with_nurses(0))
    ctx.shifts = [replace(s, minimum_staff=0) for s in ctx.shifts]
    ctx.employees = [
        EmployeeCtx(1, "A", "B", EmployeeRole.NURSE, date(2015, 1, 1), active=False),
        ctx.employees[1],
    ]
    ctx.today = today
    return ctx


def test_inactive_employee_in_a_past_month_is_not_an_error():
    ctx = _inactive_context(today=date(2026, 11, 16))
    report = validate(ctx, [plan(1, date(2026, 9, 7), "D")])
    assert not [e for e in report.errors if e.code == rules.RULE_INACTIVE]


def test_inactive_employee_in_the_future_is_an_error():
    ctx = _inactive_context(today=date(2026, 9, 1))
    report = validate(ctx, [plan(1, date(2026, 9, 7), "D")])
    assert [e for e in report.errors if e.code == rules.RULE_INACTIVE]


# --- the edit gate --------------------------------------------------------
def test_a_worse_version_of_an_existing_violation_counts_as_new():
    from app.services.schedule_service import _new_or_worse

    before = [{
        "code": "WEEKLY_LIMIT", "employee_id": 1, "date": "2026-09-07", "shift_code": None,
        "details": {"over_by": 100},
    }]
    same = [dict(before[0])]
    worse = [{**before[0], "details": {"over_by": 555}}]
    better = [{**before[0], "details": {"over_by": 10}}]
    assert _new_or_worse(same, before) == []
    assert _new_or_worse(better, before) == []
    assert _new_or_worse(worse, before) == worse

    understaffed = [{
        "code": "MIN_STAFF", "employee_id": None, "date": "2026-09-07", "shift_code": "D",
        "details": {"required": 2, "actual": 1},
    }]
    emptier = [{**understaffed[0], "details": {"required": 2, "actual": 0}}]
    assert _new_or_worse(emptier, understaffed) == emptier


# --- API ------------------------------------------------------------------
def _generate(client):
    response = client.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"], body["solver"]
    return body


def test_partial_updates_reject_null_and_blank(logged_in):
    employee = logged_in.get("/api/employees").json()[0]
    for payload in ({"first_name": None}, {"first_name": "   "}, {"active": None}):
        response = logged_in.put(f"/api/employees/{employee['id']}", json=payload)
        assert response.status_code == 422, (payload, response.text)
    assert logged_in.put("/api/settings", json={"weekly_minutes_limit": None}).status_code == 422
    shift = logged_in.get("/api/settings/shifts").json()[0]
    assert logged_in.put(
        f"/api/settings/shifts/{shift['id']}", json={"start_time": None}
    ).status_code == 422
    # a legitimate null: clearing the note of an availability entry
    row = logged_in.post("/api/availability", json={
        "employee_id": employee["id"], "date": "2026-09-03", "type": "PREFERRED_OFF",
        "note": "urlop?",
    }).json()
    response = logged_in.put(f"/api/availability/{row['id']}", json={"note": None})
    assert response.status_code == 200 and response.json()["note"] is None


def test_solver_time_limit_is_capped_below_the_proxy_timeout(logged_in):
    from app.config import settings

    too_long = settings.solver_max_seconds + 1
    response = logged_in.put("/api/settings", json={"solver_time_limit_seconds": too_long})
    assert response.status_code == 422


def test_minimum_nurses_cannot_exceed_minimum_staff(logged_in):
    shift = logged_in.get("/api/settings/shifts").json()[0]
    assert shift["minimum_nurses"] == 1  # seeded default for new installs
    response = logged_in.put(
        f"/api/settings/shifts/{shift['id']}", json={"minimum_nurses": shift["minimum_staff"] + 1}
    )
    assert response.status_code == 422
    ok = logged_in.put(f"/api/settings/shifts/{shift['id']}", json={"minimum_nurses": 2})
    assert ok.status_code == 200 and ok.json()["minimum_nurses"] == 2


def test_pdf_export_handles_polish_names(logged_in):
    employee = logged_in.get("/api/employees").json()[0]
    renamed = logged_in.put(
        f"/api/employees/{employee['id']}",
        json={"first_name": "Michał", "last_name": "Żółć & <Syn>"},
    )
    assert renamed.status_code == 200
    body = _generate(logged_in)
    schedule_id = body["schedule"]["id"]

    whole = logged_in.get(f"/api/schedules/{schedule_id}/pdf")
    assert whole.status_code == 200, whole.text
    assert whole.content.startswith(b"%PDF")

    single = logged_in.get(f"/api/schedules/{schedule_id}/employee/{employee['id']}/pdf")
    assert single.status_code == 200, single.text
    disposition = single.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "michał" not in disposition  # the raw header stays ASCII


def test_restore_an_older_version(logged_in):
    body = _generate(logged_in)
    schedule_id = body["schedule"]["id"]
    v1 = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["assignments"]

    _generate(logged_in)  # v1 is snapshotted, the roster becomes v2
    history = logged_in.get(f"/api/schedules/{schedule_id}/history").json()
    assert [h["version"] for h in history] == [1]

    response = logged_in.post(f"/api/schedules/{schedule_id}/history/1/restore")
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored["schedule"]["version"] == 3
    assert restored["skipped"] == []

    now = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["assignments"]
    key = lambda a: (a["employee_id"], a["work_date"], a["shift_code"])  # noqa: E731
    assert sorted(map(key, now)) == sorted(map(key, v1))

    versions = [h["version"] for h in logged_in.get(f"/api/schedules/{schedule_id}/history").json()]
    assert versions == [2, 1]  # nothing was lost - v2 is in the history now
    assert logged_in.post(
        f"/api/schedules/{schedule_id}/history/3/restore"
    ).status_code == 400  # already current

    audit = logged_in.get("/api/audit").json()
    assert any(row["action"] == "SCHEDULE_RESTORED" for row in audit)


def test_restore_is_refused_for_an_approved_schedule(logged_in):
    body = _generate(logged_in)
    schedule_id = body["schedule"]["id"]
    _generate(logged_in)
    assert logged_in.post(f"/api/schedules/{schedule_id}/approve").status_code == 200
    response = logged_in.post(f"/api/schedules/{schedule_id}/history/1/restore")
    assert response.status_code == 409


def test_failed_regeneration_keeps_the_previous_status(logged_in, monkeypatch):
    body = _generate(logged_in)
    assert body["schedule"]["status"] == "VALID"

    from app.services import schedule_service

    monkeypatch.setattr(
        schedule_service,
        "generate",
        lambda ctx: GenerationResult(success=False, status="INFEASIBLE", message="x"),
    )
    response = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["schedule"]["status"] == "VALID"
    assert logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()["assignments"]


def test_concurrent_generation_of_one_month_is_refused(logged_in, db_session):
    from app.services.schedule_service import try_lock_month_generation

    assert try_lock_month_generation(db_session, YEAR, MONTH)  # held until rollback
    try:
        response = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
        assert response.status_code == 409
        assert "generowany" in response.json()["detail"]["message"]
    finally:
        db_session.rollback()


def _rostered_cell(client):
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    return grid["assignments"][0]


def test_month_view_revalidates_after_new_unavailability(logged_in):
    _generate(logged_in)
    cell = _rostered_cell(logged_in)
    added = logged_in.post("/api/availability", json={
        "employee_id": cell["employee_id"], "date": cell["work_date"], "type": "UNAVAILABLE",
    })
    assert added.status_code == 201
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert grid["schedule"]["status"] == "INVALID"
    assert any(e["code"] == "UNAVAILABLE" for e in grid["validation"]["errors"])


def test_opening_an_approved_schedule_does_not_unapprove_it(logged_in):
    body = _generate(logged_in)
    schedule_id = body["schedule"]["id"]
    assert logged_in.post(f"/api/schedules/{schedule_id}/approve").status_code == 200
    cell = _rostered_cell(logged_in)
    logged_in.post("/api/availability", json={
        "employee_id": cell["employee_id"], "date": cell["work_date"], "type": "UNAVAILABLE",
    })
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert grid["schedule"]["status"] == "APPROVED"
    assert any(e["code"] == "UNAVAILABLE" for e in grid["validation"]["errors"])
    assert logged_in.get(f"/api/schedules/{schedule_id}/statistics").status_code == 200
    again = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert again["schedule"]["status"] == "APPROVED"


@pytest.mark.parametrize("name", ["kowalczyk_michał.pdf", "a b.pdf", "zażółć.pdf"])
def test_attachment_header_is_latin1_safe(name):
    from app.api.schedules import attachment_header

    header = attachment_header(name)
    header.encode("latin-1")  # would raise for a raw non-ASCII filename
    assert header.startswith('attachment; filename="')
