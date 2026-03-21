"""add event photo binary storage

Revision ID: 0003_event_photo_binary_storage
Revises: 0002_tg_notification_jobs
Create Date: 2026-03-21 22:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_event_photo_binary_storage"
down_revision = "0002_tg_notification_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("photo_content_type", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("photo_data", sa.LargeBinary(), nullable=True))
    op.add_column("events", sa.Column("photo_size_bytes", sa.Integer(), nullable=True))

    op.create_check_constraint(
        "chk_events_photo_size_limit",
        "events",
        "photo_size_bytes IS NULL OR photo_size_bytes BETWEEN 1 AND 10485760",
    )
    op.create_check_constraint(
        "chk_events_photo_content_type_not_blank",
        "events",
        "photo_content_type IS NULL OR btrim(photo_content_type) <> ''",
    )
    op.create_check_constraint(
        "chk_events_photo_fields_consistency",
        "events",
        """
        (photo_data IS NULL AND photo_content_type IS NULL AND photo_size_bytes IS NULL)
        OR (photo_data IS NOT NULL AND photo_content_type IS NOT NULL AND photo_size_bytes IS NOT NULL)
        """,
    )


def downgrade() -> None:
    op.drop_constraint("chk_events_photo_fields_consistency", "events", type_="check")
    op.drop_constraint("chk_events_photo_content_type_not_blank", "events", type_="check")
    op.drop_constraint("chk_events_photo_size_limit", "events", type_="check")

    op.drop_column("events", "photo_size_bytes")
    op.drop_column("events", "photo_data")
    op.drop_column("events", "photo_content_type")
