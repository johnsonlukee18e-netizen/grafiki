"""A4 landscape PDF export (ReportLab).

Two documents: the whole department grid and a single employee's roster.
Both carry facility, department, month, legend, statistics, generation date
and the schedule version.
"""
from __future__ import annotations

import logging
import os
import unicodedata
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.models import Employee, EmployeeColor, Schedule
from app.scheduler import rules
from app.services import planning
from app.services.config_service import get_config
from app.services.seniority import employee_color

logger = logging.getLogger(__name__)

#: Unicode TTF fonts tried in order. The built-in Helvetica only covers
#: WinAnsi, so Polish letters such as "ł", "ś" or "ż" in employee names would
#: come out as black boxes. The Docker image ships DejaVu (fonts-dejavu-core).
FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
)


def _register_fonts() -> tuple[str, str]:
    """Register a Unicode font family; fall back to Helvetica if none exists."""
    override = os.environ.get("PDF_FONT_REGULAR"), os.environ.get("PDF_FONT_BOLD")
    candidates = ((override,) if all(override) else ()) + FONT_CANDIDATES
    for regular, bold in candidates:
        if not (os.path.isfile(regular) and os.path.isfile(bold)):
            continue
        try:
            pdfmetrics.registerFont(TTFont("AppSans", regular))
            pdfmetrics.registerFont(TTFont("AppSans-Bold", bold))
            pdfmetrics.registerFontFamily(
                "AppSans",
                normal="AppSans",
                bold="AppSans-Bold",
                italic="AppSans",
                boldItalic="AppSans-Bold",
            )
        except Exception:  # pragma: no cover - a broken font file
            logger.exception("Could not load PDF font %s", regular)
            continue
        return "AppSans", "AppSans-Bold"
    logger.warning(
        "No Unicode TTF font found for PDF export - Polish letters may not render. "
        "Install fonts-dejavu-core or set PDF_FONT_REGULAR / PDF_FONT_BOLD."
    )
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()
UNICODE_FONT = FONT != "Helvetica"

MONTHS_PL = (
    ("styczeń", "styczen"),
    ("luty", "luty"),
    ("marzec", "marzec"),
    ("kwiecień", "kwiecien"),
    ("maj", "maj"),
    ("czerwiec", "czerwiec"),
    ("lipiec", "lipiec"),
    ("sierpień", "sierpien"),
    ("wrzesień", "wrzesien"),
    ("październik", "pazdziernik"),
    ("listopad", "listopad"),
    ("grudzień", "grudzien"),
)
WEEKDAYS_PL = ("Pn", "Wt", "Śr" if UNICODE_FONT else "Sr", "Cz", "Pt", "So", "Nd")


def pl(text: str) -> str:
    """Fixed Polish labels: kept as is with a Unicode font, plain ASCII otherwise."""
    if UNICODE_FONT:
        return text
    text = text.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def esc(value: object) -> str:
    """Escape user data before it goes into ReportLab's mini-markup.

    A department called "Chirurgia & Ortopedia" or a name with "<" would
    otherwise break the paragraph parser and turn the export into a 500.
    """
    return escape(str(value))

COLOR_MAP = {
    EmployeeColor.RED: colors.HexColor("#dc3545"),
    EmployeeColor.YELLOW: colors.HexColor("#ffc107"),
    EmployeeColor.GREEN: colors.HexColor("#198754"),
    EmployeeColor.PURPLE: colors.HexColor("#6f42c1"),
}
WEEKEND_BG = colors.HexColor("#eef1f5")
HOLIDAY_BG = colors.HexColor("#fde2e4")
HEADER_BG = colors.HexColor("#212529")
GRID_COLOR = colors.HexColor("#adb5bd")


def month_title(year: int, month: int) -> str:
    name = MONTHS_PL[month - 1][0 if UNICODE_FONT else 1]
    return f"{name.capitalize()} {year}"


def _styles():
    base = getSampleStyleSheet()
    for style in base.byName.values():
        if isinstance(style, ParagraphStyle):
            style.fontName = FONT_BOLD if "Bold" in style.fontName else FONT
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=15, spaceAfter=2, alignment=TA_CENTER
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#495057"),
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=4
        ),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=7.5, leading=9),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=7, leading=8),
    }


def _document(buffer: BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Grafik pracy",
        author="Nurse Scheduler",
    )


def _header(styles, config, schedule: Schedule, subtitle_extra: str = "") -> list:
    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    subtitle = (
        f"{esc(config.department_name)} &nbsp;|&nbsp; wersja grafiku: v{schedule.version} "
        f"&nbsp;|&nbsp; status: {schedule.status.value} "
        f"&nbsp;|&nbsp; wygenerowano: {generated}"
    )
    if subtitle_extra:
        subtitle = f"{subtitle_extra}<br/>{subtitle}"
    return [
        Paragraph(
            f"{esc(config.facility_name)} - grafik pracy - "
            f"{month_title(schedule.year, schedule.month)}",
            styles["title"],
        ),
        Paragraph(subtitle, styles["subtitle"]),
    ]


def _legend(styles, ctx) -> Table:
    parts = [
        f"{shift.code} = {shift.start_time.strftime('%H:%M')}-"
        f"{shift.end_time.strftime('%H:%M')} ({rules.format_minutes(shift.duration_minutes)} h)"
        for shift in ctx.shifts
    ]
    parts.append("W = wolne")
    rows = [[Paragraph("<b>Legenda:</b> " + " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(parts), styles["small"])]]
    table = Table(rows, colWidths=[277 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, GRID_COLOR),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _grid_table(ctx, assignments, employees, styles) -> Table:
    by_key = {(a.employee_id, a.day): a.shift_code for a in assignments}
    days = ctx.days

    header_day = ["Pracownik"] + [str(d.day) for d in days] + ["Godz."]
    header_weekday = [""] + [WEEKDAYS_PL[d.weekday()] for d in days] + [""]
    data = [header_day, header_weekday]

    shifts = ctx.shift_by_code
    for employee in employees:
        minutes = 0
        row = [Paragraph(esc(f"{employee.last_name} {employee.first_name}"), styles["cell"])]
        for day in days:
            code = by_key.get((employee.id, day))
            row.append(code or "W")
            if code and code in shifts:
                minutes += shifts[code].duration_minutes
        row.append(rules.format_minutes(minutes))
        data.append(row)

    name_width = 34 * mm
    total_width = 277 * mm
    hours_width = 13 * mm
    day_width = (total_width - name_width - hours_width) / len(days)
    widths = [name_width] + [day_width] * len(days) + [hours_width]

    table = Table(data, colWidths=widths, repeatRows=2)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("FONTNAME", (0, 0), (-1, 1), FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, 1), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("FONTNAME", (-1, 2), (-1, -1), FONT_BOLD),
    ]

    for index, day in enumerate(days, start=1):
        if ctx.is_holiday(day):
            style.append(("BACKGROUND", (index, 2), (index, -1), HOLIDAY_BG))
        elif day.weekday() >= 5:
            style.append(("BACKGROUND", (index, 2), (index, -1), WEEKEND_BG))

    for row_index, employee in enumerate(employees, start=2):
        color = COLOR_MAP[employee_color(employee.role, employee.employment_date, days[0])]
        style.append(("LINEBEFORE", (0, row_index), (0, row_index), 4, color))

    table.setStyle(TableStyle(style))
    return table


def _statistics_table(statistics, styles) -> Table:
    head = [
        "Pracownik",
        "Godziny",
        "D",
        "R",
        "N",
        "Soboty",
        "Niedziele",
        "Weekendy",
        pl("Święta"),
        "Wolne",
    ]
    data = [head]
    for row in statistics["employees"]:
        data.append(
            [
                Paragraph(esc(row["employee_name"]), styles["cell"]),
                f"{row['hours_label']}",
                str(row["shifts"].get("D", 0)),
                str(row["shifts"].get("R", 0)),
                str(row["shifts"].get("N", 0)),
                str(row["saturdays"]),
                str(row["sundays"]),
                str(row["weekend_shifts"]),
                str(row["holiday_shifts"]),
                str(row["days_off"]),
            ]
        )
    widths = [60 * mm, 22 * mm] + [16 * mm] * 8
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, GRID_COLOR),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def render_schedule_pdf(db: Session, schedule: Schedule) -> bytes:
    """Whole-department grid + statistics."""
    config = get_config(db)
    employees = planning.employees_for_schedule(db, schedule)
    ctx = planning.build_context(
        db,
        schedule.year,
        schedule.month,
        employees=employees,
        exclude_schedule_id=schedule.id,
        config=config,
    )
    assignments = planning.load_assignments(db, schedule.id)
    from app.scheduler.statistics import build_statistics

    statistics = build_statistics(ctx, assignments)

    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer)
    story: list = []
    story += _header(styles, config, schedule)
    story.append(_grid_table(ctx, assignments, employees, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(_legend(styles, ctx))
    story.append(PageBreak())
    story.append(Paragraph(pl("Statystyki miesięczne"), styles["section"]))
    story.append(_statistics_table(statistics, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"Limit tygodniowy: {rules.format_minutes_pl(config.weekly_minutes_limit)} "
            f"&nbsp;|&nbsp; minimalny odpoczynek: "
            f"{rules.format_minutes_pl(config.min_rest_minutes)} "
            f"&nbsp;|&nbsp; wolna niedziela: co {config.sunday_free_every_n}.",
            styles["small"],
        )
    )
    doc.build(story)
    return buffer.getvalue()


def render_employee_pdf(db: Session, schedule: Schedule, employee: Employee) -> bytes:
    """Single employee: day-by-day list plus their statistics."""
    config = get_config(db)
    ctx = planning.build_context(
        db,
        schedule.year,
        schedule.month,
        employees=planning.employees_for_schedule(db, schedule),
        exclude_schedule_id=schedule.id,
        config=config,
    )
    assignments = [
        a for a in planning.load_assignments(db, schedule.id) if a.employee_id == employee.id
    ]
    from app.scheduler.statistics import build_statistics

    statistics = build_statistics(ctx, assignments)
    own = next(
        (row for row in statistics["employees"] if row["employee_id"] == employee.id),
        None,
    )

    styles = _styles()
    buffer = BytesIO()
    doc = _document(buffer)
    story: list = _header(
        styles,
        config,
        schedule,
        subtitle_extra=f"<b>{esc(employee.full_name)}</b> ({employee.role.value})",
    )

    by_day = {a.day: a.shift_code for a in assignments}
    shifts = ctx.shift_by_code
    data = [[pl("Dzień"), pl("Dzień tyg."), "Zmiana", "Od", "Do", "Czas", "Uwagi"]]
    for day in ctx.days:
        code = by_day.get(day)
        shift = shifts.get(code) if code else None
        notes = []
        if ctx.is_holiday(day):
            notes.append(ctx.holidays[day])
        elif day.weekday() >= 5:
            notes.append("weekend")
        data.append(
            [
                day.strftime("%d.%m.%Y"),
                WEEKDAYS_PL[day.weekday()],
                code or "W",
                shift.start_on(day).strftime("%H:%M") if shift else "-",
                shift.end_on(day).strftime("%d.%m %H:%M") if shift else "-",
                rules.format_minutes(shift.duration_minutes) if shift else "0:00",
                ", ".join(notes),
            ]
        )
    table = Table(
        data,
        colWidths=[24 * mm, 18 * mm, 18 * mm, 18 * mm, 26 * mm, 18 * mm, 60 * mm],
        repeatRows=1,
    )
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for index, day in enumerate(ctx.days, start=1):
        if ctx.is_holiday(day):
            style.append(("BACKGROUND", (0, index), (-1, index), HOLIDAY_BG))
        elif day.weekday() >= 5:
            style.append(("BACKGROUND", (0, index), (-1, index), WEEKEND_BG))
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    if own:
        summary = (
            f"<b>Podsumowanie:</b> godziny {own['hours_label']} "
            f"&nbsp;|&nbsp; D: {own['shifts'].get('D', 0)} "
            f"&nbsp;|&nbsp; R: {own['shifts'].get('R', 0)} "
            f"&nbsp;|&nbsp; N: {own['shifts'].get('N', 0)} "
            f"&nbsp;|&nbsp; soboty: {own['saturdays']} "
            f"&nbsp;|&nbsp; niedziele: {own['sundays']} "
            f"&nbsp;|&nbsp; {pl('święta')}: {own['holiday_shifts']} "
            f"&nbsp;|&nbsp; dni wolne: {own['days_off']}"
        )
        story.append(KeepTogether(Paragraph(summary, styles["small"])))
        weekly = " &nbsp;|&nbsp; ".join(
            f"{week['week']}: {week['label']}" for week in own["weeks"]
        )
        if weekly:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(f"<b>Tygodnie:</b> {weekly}", styles["small"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_legend(styles, ctx))

    doc.build(story)
    return buffer.getvalue()
