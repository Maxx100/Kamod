"""add user profile photo storage

Revision ID: 0004_user_profile_photo
Revises: 0003_event_photo_binary_storage
Create Date: 2026-03-21 23:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_user_profile_photo"
down_revision = "0003_event_photo_binary_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_content_type", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("photo_data", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("photo_size_bytes", sa.Integer(), nullable=True))

    op.create_check_constraint(
        "chk_users_photo_size_limit",
        "users",
        "photo_size_bytes IS NULL OR photo_size_bytes BETWEEN 1 AND 5242880",
    )
    op.create_check_constraint(
        "chk_users_photo_content_type_not_blank",
        "users",
        "photo_content_type IS NULL OR btrim(photo_content_type) <> ''",
    )
    op.create_check_constraint(
        "chk_users_photo_fields_consistency",
        "users",
        """
        (photo_data IS NULL AND photo_content_type IS NULL AND photo_size_bytes IS NULL)
        OR (photo_data IS NOT NULL AND photo_content_type IS NOT NULL AND photo_size_bytes IS NOT NULL)
        """,
    )


def downgrade() -> None:
    op.drop_constraint("chk_users_photo_fields_consistency", "users", type_="check")
    op.drop_constraint("chk_users_photo_content_type_not_blank", "users", type_="check")
    op.drop_constraint("chk_users_photo_size_limit", "users", type_="check")

    op.drop_column("users", "photo_size_bytes")
    op.drop_column("users", "photo_data")
    op.drop_column("users", "photo_content_type")
