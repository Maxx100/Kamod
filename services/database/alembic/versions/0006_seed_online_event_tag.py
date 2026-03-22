"""seed online event tag

Revision ID: 0006_seed_online_event_tag
Revises: 0005_seed_default_event_tags
Create Date: 2026-03-22 01:20:00
"""

from __future__ import annotations

from alembic import op


revision = "0006_seed_online_event_tag"
down_revision = "0005_seed_default_event_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tags (slug, name, group_code, is_active)
        VALUES ('online', 'Онлайн', 'format', TRUE)
        ON CONFLICT (slug) DO UPDATE
        SET
            name = EXCLUDED.name,
            group_code = EXCLUDED.group_code,
            is_active = TRUE,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM tags
        WHERE slug = 'online'
          AND NOT EXISTS (
              SELECT 1
              FROM event_tags
              WHERE event_tags.tag_id = tags.id
          );
        """
    )
