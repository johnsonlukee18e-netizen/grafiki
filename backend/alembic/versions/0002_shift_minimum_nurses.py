"""shifts.minimum_nurses; audit action SCHEDULE_RESTORED

Revision ID: 0002_shift_minimum_nurses
Revises: 0001_initial_schema
Create Date: 2026-11-16 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_shift_minimum_nurses"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0 keeps existing departments behaving exactly as before; the manager
    # switches the rule on per shift in USTAWIENIA.
    op.add_column(
        "shifts",
        sa.Column("minimum_nurses", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_shift_min_nurses_range",
        "shifts",
        "minimum_nurses >= 0 AND minimum_nurses <= minimum_staff",
    )
    # Restoring an older version of a schedule is audited on its own.
    # PostgreSQL 12+ allows ADD VALUE inside the migration transaction as long
    # as the new value is not used in that same transaction.
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'SCHEDULE_RESTORED'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value; the unused
    # 'SCHEDULE_RESTORED' label is harmless and stays.
    op.drop_constraint("ck_shift_min_nurses_range", "shifts", type_="check")
    op.drop_column("shifts", "minimum_nurses")
