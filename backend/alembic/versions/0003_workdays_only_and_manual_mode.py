"""shifts.workdays_only (no R on weekends/holidays); schedules.mode (manual building)

Revision ID: 0003_workdays_and_manual_mode
Revises: 0002_shift_minimum_nurses
Create Date: 2026-11-23 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_workdays_and_manual_mode"
down_revision = "0002_shift_minimum_nurses"
branch_labels = None
depends_on = None

schedule_mode = sa.Enum("AUTO", "MANUAL", name="schedule_mode")


def upgrade() -> None:
    op.add_column(
        "shifts",
        sa.Column("workdays_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Department rule: the morning shift R is never planned on a Saturday,
    # Sunday or public holiday. Other shifts keep running every day.
    op.execute("UPDATE shifts SET workdays_only = true WHERE code = 'R'")

    schedule_mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "schedules",
        sa.Column("mode", schedule_mode, server_default="AUTO", nullable=False),
    )

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'SCHEDULE_MODE_CHANGED'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'SCHEDULE_MANUAL_EDIT'")


def downgrade() -> None:
    # Enum labels added to audit_action cannot be dropped individually; they
    # are unused after a downgrade and harmless.
    op.drop_column("schedules", "mode")
    schedule_mode.drop(op.get_bind(), checkfirst=True)
    op.drop_column("shifts", "workdays_only")
