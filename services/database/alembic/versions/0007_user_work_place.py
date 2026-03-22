"""add users work_place

Revision ID: 0007_user_work_place
Revises: 0006_seed_online_event_tag
Create Date: 2026-03-22 11:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_user_work_place"
down_revision = "0006_seed_online_event_tag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("work_place", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_users_work_place_not_blank",
        "users",
        "work_place IS NULL OR btrim(work_place) <> ''",
    )


def downgrade() -> None:
    op.drop_constraint("chk_users_work_place_not_blank", "users", type_="check")
    op.drop_column("users", "work_place")
