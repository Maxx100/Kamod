"""add event registrations checked_in_at

Revision ID: 0008_event_reg_checked_in
Revises: 0007_user_work_place
Create Date: 2026-03-22 19:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_event_reg_checked_in"
down_revision = "0007_user_work_place"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_registrations", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "chk_event_registrations_checked_in_requires_registered",
        "event_registrations",
        "checked_in_at IS NULL OR status = 'registered'",
    )
    op.create_index(
        "idx_event_registrations_event_checked_in",
        "event_registrations",
        ["event_id", "checked_in_at"],
        unique=False,
        postgresql_where=sa.text("checked_in_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_event_registrations_event_checked_in", table_name="event_registrations")
    op.drop_constraint("chk_event_registrations_checked_in_requires_registered", "event_registrations", type_="check")
    op.drop_column("event_registrations", "checked_in_at")
