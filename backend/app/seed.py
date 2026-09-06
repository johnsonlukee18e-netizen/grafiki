"""Seed shifts, department configuration, demo employees and availability.

Run with:  python -m app.seed            (idempotent, safe to repeat)
           python -m app.seed --demo     (also adds the demo staff roster)

Why 16 demo employees and not the 10 from the original brief: with the default
minimum staffing (2 people on each of D, R and N) one week demands
7 * (2*720 + 2*455 + 2*720) = 26 530 minutes of work, while one employee may
work at most 2 275 minutes per week. Ten people can supply 22 750 minutes, so
the month is provably impossible - the generator would (correctly) refuse. The
smallest team that can satisfy the rules is 13 people; 16 leaves the solver
room to distribute nights and weekends fairly.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import Availability, AvailabilityType, Employee, EmployeeRole, Shift
from app.services.config_service import get_config
from app.services.holiday_service import ensure_holidays_for_year

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
logger = logging.getLogger("seed")

SHIFTS = (
    # code, name, start, end, minutes, crosses midnight, minimum staff, order
    ("D", "Dzien", time(7, 0), time(19, 0), 720, False, 2, 1),
    ("R", "Ranek", time(7, 0), time(14, 35), 455, False, 2, 2),
    ("N", "Noc", time(19, 0), time(7, 0), 720, True, 2, 3),
)

#: The first ten match the brief (7 nurses + 3 care workers); the rest make the
#: default minimum staffing actually solvable.
DEMO_EMPLOYEES = (
    ("Anna", "Kowalska", EmployeeRole.NURSE, date(2015, 3, 1)),
    ("Barbara", "Nowak", EmployeeRole.NURSE, date(2019, 9, 15)),
    ("Celina", "Wisniewska", EmployeeRole.NURSE, date(2022, 1, 10)),
    ("Dorota", "Wojcik", EmployeeRole.NURSE, date(2024, 6, 1)),
    ("Ewa", "Kowalczyk", EmployeeRole.NURSE, date(2025, 4, 20)),
    ("Feliksa", "Kaminska", EmployeeRole.NURSE, date(2011, 11, 5)),
    ("Grazyna", "Lewandowska", EmployeeRole.NURSE, date(2023, 2, 13)),
    ("Halina", "Zielinska", EmployeeRole.CARE_WORKER, date(2017, 8, 1)),
    ("Irena", "Szymanska", EmployeeRole.CARE_WORKER, date(2021, 5, 4)),
    ("Joanna", "Wozniak", EmployeeRole.CARE_WORKER, date(2025, 1, 7)),
    ("Katarzyna", "Dabrowska", EmployeeRole.NURSE, date(2016, 10, 3)),
    ("Lidia", "Kozlowska", EmployeeRole.NURSE, date(2020, 2, 17)),
    ("Marta", "Jankowska", EmployeeRole.NURSE, date(2024, 11, 12)),
    ("Natalia", "Mazur", EmployeeRole.NURSE, date(2013, 7, 22)),
    ("Olga", "Krawczyk", EmployeeRole.CARE_WORKER, date(2018, 4, 9)),
    ("Patrycja", "Piotrowska", EmployeeRole.CARE_WORKER, date(2022, 9, 26)),
)

#: (employee index, day offset from the 1st, availability type)
DEMO_AVAILABILITY = (
    (0, 4, AvailabilityType.UNAVAILABLE),
    (0, 5, AvailabilityType.UNAVAILABLE),
    (1, 9, AvailabilityType.PREFERRED_NIGHT),
    (2, 2, AvailabilityType.PREFERRED_OFF),
    (3, 14, AvailabilityType.UNAVAILABLE),
    (4, 7, AvailabilityType.PREFERRED_MORNING),
    (5, 20, AvailabilityType.PREFERRED_DAY),
    (7, 11, AvailabilityType.UNAVAILABLE),
    (9, 18, AvailabilityType.PREFERRED_OFF),
    (12, 21, AvailabilityType.PREFERRED_NIGHT),
)


def seed_shifts(db: Session) -> int:
    created = 0
    for code, name, start, end, minutes, crosses, minimum, order in SHIFTS:
        if db.scalar(select(Shift).where(Shift.code == code)):
            continue
        db.add(
            Shift(
                code=code,
                name=name,
                start_time=start,
                end_time=end,
                duration_minutes=minutes,
                crosses_midnight=crosses,
                minimum_staff=minimum,
                active=True,
                sort_order=order,
            )
        )
        created += 1
    db.flush()
    return created


def seed_employees(db: Session) -> int:
    created = 0
    for first, last, role, employed in DEMO_EMPLOYEES:
        exists = db.scalar(
            select(Employee).where(Employee.first_name == first, Employee.last_name == last)
        )
        if exists:
            continue
        db.add(
            Employee(
                first_name=first,
                last_name=last,
                role=role,
                employment_date=employed,
                active=True,
            )
        )
        created += 1
    db.flush()
    return created


def seed_availability(db: Session, year: int, month: int) -> int:
    people = list(
        db.scalars(select(Employee).order_by(Employee.id))
    )
    if not people:
        return 0
    first_day = date(year, month, 1)
    created = 0
    for index, offset, kind in DEMO_AVAILABILITY:
        if index >= len(people):
            continue
        day = first_day + timedelta(days=offset)
        if day.month != month:
            continue
        employee = people[index]
        exists = db.scalar(
            select(Availability).where(
                Availability.employee_id == employee.id, Availability.day == day
            )
        )
        if exists:
            continue
        db.add(Availability(employee_id=employee.id, day=day, type=kind))
        created += 1
    db.flush()
    return created


def run(demo: bool, year: int, month: int) -> None:
    with SessionLocal() as db:
        config = get_config(db)
        shifts = seed_shifts(db)
        holidays = ensure_holidays_for_year(db, year, config.country_code)
        if year != date.today().year:
            holidays += ensure_holidays_for_year(db, date.today().year, config.country_code)
        employees = availability = 0
        if demo:
            employees = seed_employees(db)
            availability = seed_availability(db, year, month)
        facility = f"{config.facility_name} / {config.department_name}"
        db.commit()

    logger.info("Configuration: %s", facility)
    logger.info("Shifts created: %d", shifts)
    logger.info("Holidays imported: %d", holidays)
    if demo:
        logger.info("Demo employees created: %d", employees)
        logger.info("Demo availability rows created: %d", availability)


def main() -> None:
    today = date.today()
    parser = argparse.ArgumentParser(description="Seed the nurse scheduler database")
    parser.add_argument("--demo", action="store_true", help="also insert the demo staff roster")
    parser.add_argument("--year", type=int, default=today.year)
    parser.add_argument("--month", type=int, default=today.month)
    args = parser.parse_args()
    run(demo=args.demo, year=args.year, month=args.month)


if __name__ == "__main__":
    main()
