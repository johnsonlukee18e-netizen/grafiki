"""Polish statutory public holidays, computed for any year.

Based on the Act of 18 January 1951 on days free from work. Movable feasts
derive from Gregorian Easter (anonymous Gregorian computus).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple


class HolidayDef(NamedTuple):
    day: date
    name: str


#: (month, day, name, first year in force)
_FIXED: tuple[tuple[int, int, str, int], ...] = (
    (1, 1, "Nowy Rok", 1951),
    (1, 6, "Święto Trzech Króli", 2011),
    (5, 1, "Święto Państwowe (1 Maja)", 1951),
    (5, 3, "Święto Narodowe Trzeciego Maja", 1990),
    (8, 15, "Wniebowzięcie Najświętszej Maryi Panny", 1989),
    (11, 1, "Wszystkich Świętych", 1989),
    (11, 11, "Narodowe Święto Niepodległości", 1989),
    (12, 25, "Boże Narodzenie (pierwszy dzień)", 1951),
    (12, 26, "Boże Narodzenie (drugi dzień)", 1951),
)

#: (offset from Easter Sunday, name)
_MOVABLE: tuple[tuple[int, str], ...] = (
    (0, "Wielkanoc"),
    (1, "Poniedziałek Wielkanocny"),
    (49, "Zesłanie Ducha Świętego (Zielone Świątki)"),
    (60, "Boże Ciało"),
)


def easter_sunday(year: int) -> date:
    """Gregorian Easter for the given year."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month = (h + lam - 7 * m + 114) // 31
    day = ((h + lam - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def polish_holidays(year: int) -> list[HolidayDef]:
    """Every statutory day off work in Poland for ``year``, sorted by date."""
    if not 1900 <= year <= 2200:
        raise ValueError(f"year out of supported range: {year}")
    out: list[HolidayDef] = [
        HolidayDef(date(year, month, day), name)
        for month, day, name, since in _FIXED
        if year >= since
    ]
    easter = easter_sunday(year)
    out.extend(HolidayDef(easter + timedelta(days=offset), name) for offset, name in _MOVABLE)
    return sorted(out, key=lambda h: h.day)
