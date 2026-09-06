"""Shared test fixtures.

Unit tests for the scheduling core need no database at all. API tests run
against a real PostgreSQL database (``<database>_test``) created on the fly.
"""
from __future__ import annotations

import calendar
import os
from collections.abc import Iterator
from datetime import date, time

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEV_AUTH_ENABLED", "true")
os.environ.setdefault("SESSION_SECRET", "test-secret-key-that-is-long-enough-32ch")
os.environ.setdefault("SOLVER_TIME_LIMIT_SECONDS", "10")
# The limiter keeps per-IP counters on the shared app instance, which would
# bleed between tests. It has its own dedicated test instead.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.config import settings  # noqa: E402
from app.models.enums import EmployeeRole  # noqa: E402
from app.scheduler.models import (  # noqa: E402
    EmployeeCtx,
    PlannedAssignment,
    PlanningContext,
    RuleConfig,
    ShiftDef,
)

DAY = ShiftDef(1, "D", "Dzien", time(7, 0), time(19, 0), 720, False, 2)
MORNING = ShiftDef(2, "R", "Ranek", time(7, 0), time(14, 35), 455, False, 2)
NIGHT = ShiftDef(3, "N", "Noc", time(19, 0), time(7, 0), 720, True, 2)
ALL_SHIFTS = [DAY, MORNING, NIGHT]


def make_employee(employee_id: int, employed: date | None = None) -> EmployeeCtx:
    return EmployeeCtx(
        id=employee_id,
        first_name=f"Imie{employee_id}",
        last_name=f"Nazwisko{employee_id}",
        role=EmployeeRole.NURSE if employee_id % 4 else EmployeeRole.CARE_WORKER,
        employment_date=employed or date(2015, 1, 1),
        active=True,
    )


def make_context(
    year: int = 2026,
    month: int = 9,
    employee_count: int = 6,
    shifts: list[ShiftDef] | None = None,
    config: RuleConfig | None = None,
    availability: dict | None = None,
    holidays: dict | None = None,
    boundary: list[PlannedAssignment] | None = None,
    days: list[date] | None = None,
) -> PlanningContext:
    """A planning context with every knob exposed to the test."""
    if days is None:
        last = calendar.monthrange(year, month)[1]
        days = [date(year, month, d) for d in range(1, last + 1)]
    return PlanningContext(
        year=year,
        month=month,
        days=days,
        employees=[make_employee(i) for i in range(1, employee_count + 1)],
        shifts=shifts if shifts is not None else list(ALL_SHIFTS),
        config=config or RuleConfig(solver_time_limit_seconds=10),
        availability=availability or {},
        holidays=holidays or {},
        boundary=boundary or [],
    )


def plan(employee_id: int, day: date, code: str) -> PlannedAssignment:
    return PlannedAssignment(employee_id=employee_id, day=day, shift_code=code)


@pytest.fixture
def shifts() -> list[ShiftDef]:
    return list(ALL_SHIFTS)


@pytest.fixture
def unstaffed_shifts() -> list[ShiftDef]:
    """Same shifts but with no staffing requirement - isolates other rules."""
    return [
        ShiftDef(s.id, s.code, s.name, s.start_time, s.end_time, s.duration_minutes,
                 s.crosses_midnight, 0)
        for s in ALL_SHIFTS
    ]


# --------------------------------------------------------------------------
# Database-backed fixtures (API tests)
# --------------------------------------------------------------------------
def _test_database_url() -> str:
    url = settings.database_url
    base, _, name = url.rpartition("/")
    return f"{base}/{name}_test"


@pytest.fixture(scope="session")
def db_engine():
    """Create (and drop) a dedicated test database."""
    import sqlalchemy as sa

    admin_url = settings.database_url.rpartition("/")[0] + "/postgres"
    target = _test_database_url()
    db_name = target.rpartition("/")[2]

    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    except sa.exc.OperationalError as exc:  # pragma: no cover - no server available
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    finally:
        admin.dispose()

    engine = sa.create_engine(target, future=True)
    import app.models  # noqa: F401
    from app.database.base import Base

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db_session(db_engine) -> Iterator:
    """A clean database for every test."""
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker

    from app.database.base import Base

    with db_engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine, db_session):
    """FastAPI test client wired to the test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.api.deps import get_db_session
    from app.main import app

    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db_session):
    """Shifts, configuration, holidays and a workable team."""
    from app.seed import seed_availability, seed_employees, seed_shifts
    from app.services.config_service import get_config
    from app.services.holiday_service import ensure_holidays_for_year

    get_config(db_session)
    seed_shifts(db_session)
    ensure_holidays_for_year(db_session, 2026)
    seed_employees(db_session)
    seed_availability(db_session, 2026, 9)
    db_session.commit()
    return db_session


@pytest.fixture
def logged_in(client, seeded):
    """A dev-authenticated ADMIN session with the CSRF header set."""
    response = client.post("/api/auth/dev-login")
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get(settings.csrf_cookie_name)
    return client


@pytest.fixture
def manager_client(logged_in, db_engine):
    """Downgrade the logged-in account to MANAGER."""
    import sqlalchemy as sa

    with db_engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET role = 'MANAGER'"))
    return logged_in
