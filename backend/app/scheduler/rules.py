"""Single source of truth for every scheduling rule.

The CP-SAT model (``constraints.py``) and the independent validator
(``validator.py``) both ask *these* functions whether a situation is legal.
Neither re-implements a rule on its own.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.scheduler.models import (
    PlannedAssignment,
    RuleConfig,
    ShiftDef,
    SundayRuleMode,
)

MINUTES_PER_HOUR = 60

# --- rule identifiers (used by API + UI) ---------------------------------
RULE_MIN_STAFF = "MIN_STAFF"
RULE_MIN_NURSES = "MIN_NURSES"
RULE_WEEKLY_LIMIT = "WEEKLY_LIMIT"
RULE_MIN_REST = "MIN_REST"
RULE_AFTER_NIGHT = "AFTER_NIGHT"
RULE_SUNDAY_OFF = "SUNDAY_OFF"
RULE_UNAVAILABLE = "UNAVAILABLE"
RULE_ONE_SHIFT_PER_DAY = "ONE_SHIFT_PER_DAY"
RULE_NOT_EMPLOYED = "NOT_EMPLOYED"
RULE_INACTIVE = "INACTIVE"

HARD_RULES = (
    RULE_MIN_STAFF,
    RULE_MIN_NURSES,
    RULE_WEEKLY_LIMIT,
    RULE_MIN_REST,
    RULE_AFTER_NIGHT,
    RULE_SUNDAY_OFF,
    RULE_UNAVAILABLE,
    RULE_ONE_SHIFT_PER_DAY,
    RULE_NOT_EMPLOYED,
    RULE_INACTIVE,
)


# --- time helpers ---------------------------------------------------------
def format_minutes(minutes: int) -> str:
    """2275 -> ``37:55`` (never floats)."""
    sign = "-" if minutes < 0 else ""
    minutes = abs(int(minutes))
    return f"{sign}{minutes // MINUTES_PER_HOUR}:{minutes % MINUTES_PER_HOUR:02d}"


def format_minutes_pl(minutes: int) -> str:
    """2275 -> ``37 h 55 min`` for user-facing messages."""
    minutes = int(minutes)
    hours, mins = divmod(abs(minutes), MINUTES_PER_HOUR)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"


def rest_minutes(previous_end: datetime, next_start: datetime) -> int:
    """Whole minutes of rest between two shifts (negative when overlapping)."""
    return int((next_start - previous_end).total_seconds() // MINUTES_PER_HOUR)


# --- HARD 3: minimum rest -------------------------------------------------
def rest_is_sufficient(previous_end: datetime, next_start: datetime, config: RuleConfig) -> bool:
    return rest_minutes(previous_end, next_start) >= config.min_rest_minutes


# --- HARD 4: what may follow a night --------------------------------------
def follows_night_illegally(previous: ShiftDef, following: ShiftDef, gap_days: int) -> bool:
    """After a night shift the very next day may only be free or another night."""
    return previous.is_night and gap_days == 1 and not following.is_night


def shift_pair_is_legal(
    previous: ShiftDef,
    previous_day: date,
    following: ShiftDef,
    following_day: date,
    config: RuleConfig,
) -> tuple[bool, str | None]:
    """Check the two chronological rules that bind a pair of shifts.

    Returns ``(legal, rule_code)``; ``rule_code`` names the broken rule.
    """
    if following_day <= previous_day:
        raise ValueError("following_day must be after previous_day")
    gap_days = (following_day - previous_day).days
    if follows_night_illegally(previous, following, gap_days):
        return False, RULE_AFTER_NIGHT
    if not rest_is_sufficient(previous.end_on(previous_day), following.start_on(following_day), config):
        return False, RULE_MIN_REST
    return True, None


#: Two shifts further apart than this many days can never interact.
MAX_INTERACTION_DAYS = 2


# --- HARD 2: weekly limit -------------------------------------------------
def iso_week_key(day: date) -> tuple[int, int]:
    """(iso_year, iso_week) - weeks always run Monday -> Sunday."""
    iso = day.isocalendar()
    return iso[0], iso[1]


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_end(day: date) -> date:
    return week_start(day) + timedelta(days=6)


def week_label(key: tuple[int, int]) -> str:
    monday = date.fromisocalendar(key[0], key[1], 1)
    sunday = monday + timedelta(days=6)
    return f"{monday.isoformat()} - {sunday.isoformat()}"


def weekly_limit_exceeded(total_minutes: int, config: RuleConfig) -> bool:
    return total_minutes > config.weekly_minutes_limit


# --- HARD 5: every Nth Sunday off ----------------------------------------
def sundays_between(start: date, end: date) -> list[date]:
    """All Sundays in the inclusive range, ascending."""
    first = start + timedelta(days=(6 - start.weekday()) % 7)
    out: list[date] = []
    cursor = first
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=7)
    return out


def sunday_windows(
    sundays: list[date], config: RuleConfig, anchor: date | None = None
) -> list[list[date]]:
    """Groups of Sundays in which at least one must be free.

    ``SLIDING``: every N consecutive Sundays (the strict reading - the cycle
    can never be reset by a month boundary).
    ``BLOCK``: fixed blocks of N counted from ``sunday_cycle_anchor``.
    """
    n = config.sunday_free_every_n
    if n < 1 or len(sundays) < n:
        return []
    ordered = sorted(sundays)
    if config.sunday_rule_mode is SundayRuleMode.SLIDING:
        return [ordered[i : i + n] for i in range(len(ordered) - n + 1)]

    base = anchor or config.sunday_cycle_anchor
    buckets: dict[int, list[date]] = {}
    for sunday in ordered:
        index = ((sunday - base).days // 7) // n
        buckets.setdefault(index, []).append(sunday)
    return [group for _, group in sorted(buckets.items()) if len(group) == n]


# --- roster helpers shared by solver diagnostics and validator ------------
def timeline(
    assignments: list[PlannedAssignment], shifts: dict[str, ShiftDef]
) -> dict[int, list[PlannedAssignment]]:
    """Per-employee assignments ordered in time."""
    per_employee: dict[int, list[PlannedAssignment]] = {}
    for item in assignments:
        if item.shift_code not in shifts:
            continue
        per_employee.setdefault(item.employee_id, []).append(item)
    for items in per_employee.values():
        items.sort(key=lambda a: (a.day, shifts[a.shift_code].start_time))
    return per_employee


def worked_minutes_by_week(
    assignments: list[PlannedAssignment], shifts: dict[str, ShiftDef]
) -> dict[tuple[int, tuple[int, int]], int]:
    """(employee_id, iso_week) -> minutes. A shift counts in the week of its start."""
    totals: dict[tuple[int, tuple[int, int]], int] = {}
    for item in assignments:
        shift = shifts.get(item.shift_code)
        if shift is None:
            continue
        key = (item.employee_id, iso_week_key(item.day))
        totals[key] = totals.get(key, 0) + shift.duration_minutes
    return totals
