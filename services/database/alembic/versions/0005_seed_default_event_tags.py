"""seed default event tags

Revision ID: 0005_seed_default_event_tags
Revises: 0004_user_profile_photo
Create Date: 2026-03-22 00:45:00
"""

from __future__ import annotations

from alembic import op


revision = "0005_seed_default_event_tags"
down_revision = "0004_user_profile_photo"
branch_labels = None
depends_on = None


DEFAULT_TAGS = (
    ("hackathon", "Хакатон", "type"),
    ("conference", "Конференция", "type"),
    ("workshop", "Мастер-класс", "type"),
    ("meetup", "Митап", "type"),
    ("competition", "Конкурс", "type"),
    ("online", "Онлайн", "format"),
    ("other", "Другое", "type"),
)


def upgrade() -> None:
    values_sql = ",\n        ".join(
        f"('{slug}', '{name}', '{group_code}', TRUE)"
        for slug, name, group_code in DEFAULT_TAGS
    )
    op.execute(
        f"""
        INSERT INTO tags (slug, name, group_code, is_active)
        VALUES
        {values_sql}
        ON CONFLICT (slug) DO UPDATE
        SET
            name = EXCLUDED.name,
            group_code = EXCLUDED.group_code,
            is_active = TRUE,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    slugs_sql = ", ".join(f"'{slug}'" for slug, _, _ in DEFAULT_TAGS)
    op.execute(
        f"""
        DELETE FROM tags
        WHERE slug IN ({slugs_sql})
          AND NOT EXISTS (
              SELECT 1
              FROM event_tags
              WHERE event_tags.tag_id = tags.id
          );
        """
    )
