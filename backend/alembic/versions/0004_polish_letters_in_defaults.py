"""Polish letters in seeded default names (Dzien -> Dzień, Oddzial -> Oddział)

Only values that are still exactly the old seeded defaults are touched, so
anything a manager typed in stays as it is. Statutory holiday names are
refreshed by holiday_service on the next lookup.

Revision ID: 0004_polish_letters
Revises: 0003_workdays_and_manual_mode
Create Date: 2026-11-24 12:00:00
"""
from __future__ import annotations

from alembic import op

revision = "0004_polish_letters"
down_revision = "0003_workdays_and_manual_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE shifts SET name = 'Dzień' WHERE code = 'D' AND name = 'Dzien'")
    op.execute(
        "UPDATE department_config SET department_name = 'Oddział' "
        "WHERE department_name = 'Oddzial'"
    )


def downgrade() -> None:
    op.execute("UPDATE shifts SET name = 'Dzien' WHERE code = 'D' AND name = 'Dzień'")
    op.execute(
        "UPDATE department_config SET department_name = 'Oddzial' "
        "WHERE department_name = 'Oddział'"
    )
