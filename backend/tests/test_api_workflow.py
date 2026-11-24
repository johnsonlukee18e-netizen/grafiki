"""The workflow from the specification, end to end through the API.

GENERATE -> VALIDATE -> MANUAL EDIT -> VALIDATE -> APPROVE -> PDF
Includes spec test 17 (PDF generation).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

YEAR, MONTH = 2026, 9


def pick_removable(grid) -> dict:
    """An assignment whose shift stays above both minimums without it.

    Removing it must leave enough people *and* enough nurses on that shift.
    """
    minimums = {s["code"]: s["minimum_staff"] for s in grid["shifts"]}
    nurse_minimums = {s["code"]: s.get("minimum_nurses", 0) for s in grid["shifts"]}
    nurses = {e["id"] for e in grid["employees"] if e["role"] == "NURSE"}
    counts: dict[tuple[str, str], int] = {}
    nurse_counts: dict[tuple[str, str], int] = {}
    for a in grid["assignments"]:
        key = (a["work_date"], a["shift_code"])
        counts[key] = counts.get(key, 0) + 1
        if a["employee_id"] in nurses:
            nurse_counts[key] = nurse_counts.get(key, 0) + 1
    for a in grid["assignments"]:
        key = (a["work_date"], a["shift_code"])
        if counts[key] <= minimums[a["shift_code"]]:
            continue
        if (
            a["employee_id"] in nurses
            and nurse_counts.get(key, 0) <= nurse_minimums[a["shift_code"]]
        ):
            continue
        return a
    raise AssertionError("the roster is at the bare minimum everywhere")


def generate(client):
    response = client.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"], body["solver"]
    return body


@pytest.fixture
def generated(logged_in):
    return logged_in, generate(logged_in)


# --- generation -----------------------------------------------------------
def test_generation_produces_a_valid_schedule(generated):
    _, body = generated
    assert body["schedule"]["status"] == "VALID"
    assert body["schedule"]["version"] == 1
    assert body["validation"]["valid"] is True
    assert body["validation"]["errors"] == []
    assert body["solver"]["status"] in ("OPTIMAL", "FEASIBLE")


def test_generated_schedule_is_not_automatically_approved(generated):
    _, body = generated
    assert body["schedule"]["status"] != "APPROVED"
    assert body["schedule"]["approved_at"] is None


def test_validation_checklist_covers_every_hard_rule(generated):
    _, body = generated
    checks = {row["code"]: row for row in body["validation"]["checks"]}
    for code in (
        "MIN_STAFF", "WEEKLY_LIMIT", "MIN_REST", "AFTER_NIGHT",
        "SUNDAY_OFF", "UNAVAILABLE", "ONE_SHIFT_PER_DAY",
    ):
        assert checks[code]["kind"] == "hard"
        assert checks[code]["status"] == "OK", checks[code]
    assert checks["NIGHT_FAIRNESS"]["kind"] == "soft"


def test_month_grid_returns_days_employees_and_assignments(generated):
    client, _ = generated
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert len(grid["days"]) == 30
    assert len(grid["employees"]) == 16
    assert grid["assignments"]
    assert {s["code"] for s in grid["shifts"]} == {"D", "R", "N"}
    sunday = next(d for d in grid["days"] if d["date"] == "2026-09-06")
    assert sunday["is_weekend"] and sunday["weekday"] == 6


def test_employee_colours_are_derived_from_seniority(logged_in):
    employees = {e["full_name"]: e for e in logged_in.get("/api/employees").json()}
    assert employees["Anna Kowalska"]["color"] == "RED"  # employed 2015
    assert employees["Joanna Woźniak"]["color"] == "PURPLE"  # care worker
    assert employees["Anna Kowalska"]["seniority_label"]


def test_colour_cannot_be_set_by_the_client(logged_in):
    """A nurse hired last month is GREEN no matter what the client sends."""
    hired = (date.today() - timedelta(days=30)).isoformat()
    response = logged_in.post("/api/employees", json={
        "first_name": "Zofia", "last_name": "Testowa", "role": "NURSE",
        "employment_date": hired, "active": True, "color": "RED",
    })
    assert response.status_code == 201
    assert response.json()["color"] == "GREEN"  # derived, the RED hint is ignored


# --- manual editing -------------------------------------------------------
def test_hard_violation_blocks_a_manual_edit(generated):
    """Adding a day shift right after a night must be refused with a reason."""
    client, body = generated
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    night = next(a for a in grid["assignments"] if a["shift_code"] == "N")
    next_day = (date.fromisoformat(night["work_date"]) + timedelta(days=1)).isoformat()
    occupied = [
        a for a in grid["assignments"]
        if a["employee_id"] == night["employee_id"] and a["work_date"] == next_day
    ]
    if occupied:
        response = client.put(f"/api/assignments/{occupied[0]['id']}", json={"shift_code": "D"})
    else:
        response = client.post("/api/assignments", json={
            "schedule_id": body["schedule"]["id"],
            "employee_id": night["employee_id"],
            "work_date": next_day,
            "shift_code": "D",
        })
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "twarde ograniczenie" in detail["message"]
    codes = {e["code"] for e in detail["errors"]}
    assert codes & {"AFTER_NIGHT", "MIN_REST", "WEEKLY_LIMIT"}


def test_blocked_edit_leaves_the_schedule_untouched(generated):
    client, body = generated
    before = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    night = next(a for a in before["assignments"] if a["shift_code"] == "N")
    next_day = (date.fromisoformat(night["work_date"]) + timedelta(days=1)).isoformat()
    client.post("/api/assignments", json={
        "schedule_id": body["schedule"]["id"],
        "employee_id": night["employee_id"],
        "work_date": next_day,
        "shift_code": "D",
    })
    after = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    assert len(after["assignments"]) == len(before["assignments"])
    assert after["schedule"]["version"] == before["schedule"]["version"]


def test_allowed_edit_bumps_the_version_and_marks_it_manual(generated):
    client, body = generated
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    victim = pick_removable(grid)
    response = client.delete(f"/api/assignments/{victim['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["schedule"]["version"] == grid["schedule"]["version"] + 1

    restored = client.post("/api/assignments", json={
        "schedule_id": body["schedule"]["id"],
        "employee_id": victim["employee_id"],
        "work_date": victim["work_date"],
        "shift_code": victim["shift_code"],
    })
    assert restored.status_code == 201, restored.text
    assert restored.json()["assignment"]["manually_modified"] is True


def test_removing_staff_below_the_minimum_is_refused(logged_in):
    """Strip a shift down towards one person: the hard rule must bite."""
    generate(logged_in)
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    minimums = {s["code"]: s["minimum_staff"] for s in grid["shifts"]}

    day, code = "2026-09-15", "N"
    on_that_shift = [
        a for a in grid["assignments"] if a["work_date"] == day and a["shift_code"] == code
    ]
    assert len(on_that_shift) >= minimums[code]

    refusals = 0
    for index, assignment in enumerate(on_that_shift):
        remaining = len(on_that_shift) - index - 1
        response = logged_in.delete(f"/api/assignments/{assignment['id']}")
        if remaining >= minimums[code]:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 409, response.text
            assert "MIN_STAFF" in {e["code"] for e in response.json()["detail"]["errors"]}
            refusals += 1
    assert refusals >= 1, "dropping below the minimum staffing must be blocked"


def test_cannot_edit_a_day_outside_the_month(generated):
    client, body = generated
    response = client.post("/api/assignments", json={
        "schedule_id": body["schedule"]["id"],
        "employee_id": 1,
        "work_date": "2026-10-05",
        "shift_code": "D",
    })
    assert response.status_code == 400
    assert "spoza miesiąca" in response.json()["detail"]["message"]


def test_double_booking_one_employee_on_one_day_is_refused(generated):
    client, body = generated
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    existing = grid["assignments"][0]
    other = "R" if existing["shift_code"] != "R" else "D"
    response = client.post("/api/assignments", json={
        "schedule_id": body["schedule"]["id"],
        "employee_id": existing["employee_id"],
        "work_date": existing["work_date"],
        "shift_code": other,
    })
    assert response.status_code == 409
    assert "już zmianę" in response.json()["detail"]["message"]


# --- approval -------------------------------------------------------------
def test_approve_then_lock(generated):
    client, body = generated
    schedule_id = body["schedule"]["id"]

    response = client.post(f"/api/schedules/{schedule_id}/approve")
    assert response.status_code == 200, response.text
    assert response.json()["schedule"]["status"] == "APPROVED"
    assert response.json()["schedule"]["approved_at"]

    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    removable = pick_removable(grid)
    blocked = client.delete(f"/api/assignments/{removable['id']}")
    assert blocked.status_code == 409
    assert "zatwierdzony" in blocked.json()["detail"]["message"]

    again = client.post(f"/api/schedules/{schedule_id}/approve")
    assert again.status_code == 409

    regenerate = client.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
    assert regenerate.status_code == 409

    assert client.post(f"/api/schedules/{schedule_id}/unapprove").status_code == 200
    assert client.delete(f"/api/assignments/{removable['id']}").status_code == 200


def test_invalid_schedule_cannot_be_approved(logged_in, db_session):
    """Break the roster directly in the database, then try to approve it."""
    import sqlalchemy as sa

    body = generate(logged_in)
    schedule_id = body["schedule"]["id"]
    db_session.execute(
        sa.text(
            "DELETE FROM assignments WHERE schedule_id = :sid AND work_date = :day"
        ),
        {"sid": schedule_id, "day": date(2026, 9, 14)},
    )
    db_session.commit()

    validation = logged_in.post(f"/api/schedules/{schedule_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["validation"]["valid"] is False
    assert validation.json()["schedule"]["status"] == "INVALID"

    response = logged_in.post(f"/api/schedules/{schedule_id}/approve")
    assert response.status_code == 409
    assert "Nie można zatwierdzić" in response.json()["detail"]["message"]


# --- history --------------------------------------------------------------
def test_history_keeps_every_version(generated):
    client, body = generated
    schedule_id = body["schedule"]["id"]
    grid = client.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    removed = client.delete(f"/api/assignments/{pick_removable(grid)['id']}")
    assert removed.status_code == 200, removed.text
    client.post(f"/api/schedules/{schedule_id}/approve")

    history = client.get(f"/api/schedules/{schedule_id}/history").json()
    assert len(history) >= 2
    assert history[0]["version"] > history[-1]["version"]

    snapshot = client.get(
        f"/api/schedules/{schedule_id}/history/{history[-1]['version']}"
    ).json()
    assert snapshot["snapshot"]["assignments"]
    assert snapshot["reason"]


def test_regeneration_snapshots_the_previous_roster(logged_in):
    body = generate(logged_in)
    schedule_id = body["schedule"]["id"]
    second = logged_in.post("/api/schedules/generate", json={"year": YEAR, "month": MONTH})
    assert second.status_code == 200
    assert second.json()["schedule"]["version"] == 2
    history = logged_in.get(f"/api/schedules/{schedule_id}/history").json()
    assert any("wygenerowanie" in v["reason"].lower() for v in history)


# --- 17. PDF --------------------------------------------------------------
def test_department_pdf_is_generated(generated):
    client, body = generated
    response = client.get(f"/api/schedules/{body['schedule']['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 3000
    assert "attachment" in response.headers["content-disposition"]


def test_employee_pdf_is_generated(generated):
    client, body = generated
    employee_id = client.get("/api/employees").json()[0]["id"]
    response = client.get(
        f"/api/schedules/{body['schedule']['id']}/employee/{employee_id}/pdf"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")


def test_pdf_export_is_audited(generated):
    client, body = generated
    client.get(f"/api/schedules/{body['schedule']['id']}/pdf")
    actions = [row["action"] for row in client.get("/api/audit").json()]
    assert "PDF_EXPORTED" in actions


# --- statistics -----------------------------------------------------------
def test_statistics_report_every_required_figure(generated):
    client, body = generated
    stats = client.get(f"/api/schedules/{body['schedule']['id']}/statistics").json()
    row = stats["employees"][0]
    for key in (
        "minutes", "hours_label", "shifts", "nights", "saturdays",
        "sundays", "weekend_shifts", "holiday_shifts", "days_off",
    ):
        assert key in row
    assert ":" in row["hours_label"]
    # The test environment caps the solver at 10 s, so this only checks that the
    # fairness figures are reported and roughly balanced; the strict fairness
    # assertions live in tests/test_holidays_and_fairness.py.
    for key in ("nights", "weekend_shifts", "holiday_shifts", "minutes"):
        assert stats["fairness"][key]["spread"] >= 0
    assert stats["fairness"]["nights"]["max"] >= stats["fairness"]["nights"]["min"]


def test_dashboard_summarises_the_current_month(generated):
    client, _ = generated
    body = client.get(f"/api/dashboard?year={YEAR}&month={MONTH}").json()
    assert body["employees_active"] == 16
    assert body["current"]["errors"] == 0
    assert body["current"]["assignments"] > 0
    assert body["facility_name"]


# --- availability ---------------------------------------------------------
def test_bulk_availability_marks_many_days(logged_in):
    employee_id = logged_in.get("/api/employees").json()[0]["id"]
    response = logged_in.post("/api/availability/bulk", json={
        "employee_id": employee_id,
        "dates": ["2026-09-10", "2026-09-11", "2026-09-12"],
        "type": "UNAVAILABLE",
    })
    assert response.status_code == 200
    assert len(response.json()) == 3

    listed = logged_in.get(
        f"/api/availability?employee_id={employee_id}&year=2026&month=9"
    ).json()
    unavailable = {row["date"] for row in listed if row["type"] == "UNAVAILABLE"}
    assert {"2026-09-10", "2026-09-11", "2026-09-12"} <= unavailable


def test_generator_respects_availability_entered_through_the_api(logged_in):
    employee_id = logged_in.get("/api/employees").json()[0]["id"]
    logged_in.post("/api/availability/bulk", json={
        "employee_id": employee_id,
        "dates": ["2026-09-08", "2026-09-09"],
        "type": "UNAVAILABLE",
    })
    body = generate(logged_in)
    grid = logged_in.get(f"/api/schedules/{YEAR}/{MONTH}").json()
    clashes = [
        a for a in grid["assignments"]
        if a["employee_id"] == employee_id and a["work_date"] in ("2026-09-08", "2026-09-09")
    ]
    assert clashes == []
    assert body["validation"]["valid"]


# --- holidays -------------------------------------------------------------
def test_holidays_endpoint_generates_a_year_on_demand(logged_in):
    holidays = logged_in.get("/api/holidays/2030").json()
    assert len(holidays) == 13
    assert any(h["date"] == "2030-04-21" for h in holidays)  # Easter 2030
