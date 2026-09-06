"""Seniority -> colour derivation (single source of truth).

Colours are never stored: they follow from role + employment date, so the
API recomputes them on every read.
"""
from __future__ import annotations

from datetime import date

from app.models.enums import EmployeeColor, EmployeeRole

#: Nurse thresholds expressed in whole years of service.
NURSE_RED_YEARS = 3  # strictly more than 3 years
NURSE_YELLOW_YEARS = 1  # more than 1 year and up to 3 years


def years_of_service(employment_date: date, on_date: date | None = None) -> float:
    """Completed years of service as a fraction (calendar-accurate)."""
    reference = on_date or date.today()
    if employment_date > reference:
        return 0.0
    full_years = reference.year - employment_date.year
    anniversary = _safe_anniversary(employment_date, reference.year)
    if reference < anniversary:
        full_years -= 1
        anniversary = _safe_anniversary(employment_date, reference.year - 1)
    next_anniversary = _safe_anniversary(employment_date, anniversary.year + 1)
    span = (next_anniversary - anniversary).days or 1
    return full_years + (reference - anniversary).days / span


def _safe_anniversary(employment_date: date, year: int) -> date:
    """Feb 29 hires fall back to Feb 28 in non-leap years."""
    try:
        return employment_date.replace(year=year)
    except ValueError:
        return employment_date.replace(year=year, day=28)


def employee_color(
    role: EmployeeRole, employment_date: date, on_date: date | None = None
) -> EmployeeColor:
    if role is EmployeeRole.CARE_WORKER:
        return EmployeeColor.PURPLE
    years = years_of_service(employment_date, on_date)
    if years > NURSE_RED_YEARS:
        return EmployeeColor.RED
    if years > NURSE_YELLOW_YEARS:
        return EmployeeColor.YELLOW
    return EmployeeColor.GREEN


def seniority_label(employment_date: date, on_date: date | None = None) -> str:
    """Human readable seniority, e.g. ``4 lata 2 mies.``"""
    reference = on_date or date.today()
    if employment_date > reference:
        return "0 mies."
    months = (reference.year - employment_date.year) * 12 + (
        reference.month - employment_date.month
    )
    if reference.day < employment_date.day:
        months -= 1
    months = max(months, 0)
    years, rest = divmod(months, 12)
    if years == 0:
        return f"{rest} mies."
    return f"{years} {_year_word(years)} {rest} mies."


def _year_word(years: int) -> str:
    if years == 1:
        return "rok"
    last_two = years % 100
    last = years % 10
    if 12 <= last_two <= 14:
        return "lat"
    if last in (2, 3, 4):
        return "lata"
    return "lat"
