"""create event service schema

Revision ID: 0001_create_event_service_schema
Revises:
Create Date: 2026-03-21 13:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_create_event_service_schema"
down_revision = None
branch_labels = None
depends_on = None


event_format_enum = postgresql.ENUM(
    "offline",
    "online",
    name="event_format",
)

event_status_enum = postgresql.ENUM(
    "published",
    "cancelled",
    "completed",
    name="event_status",
)

registration_status_enum = postgresql.ENUM(
    "registered",
    "cancelled",
    name="registration_status",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    bind = op.get_bind()
    event_format_enum.create(bind, checkfirst=True)
    event_status_enum.create(bind, checkfirst=True)
    registration_status_enum.create(bind, checkfirst=True)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("university", sa.Text(), nullable=True),
        sa.Column("faculty", sa.Text(), nullable=True),
        sa.Column("telegram", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("btrim(email::text) <> ''", name="chk_users_email_not_blank"),
        sa.CheckConstraint("btrim(password_hash) <> ''", name="chk_users_password_hash_not_blank"),
        sa.CheckConstraint("btrim(full_name) <> ''", name="chk_users_full_name_not_blank"),
        sa.CheckConstraint(
            "telegram IS NULL OR telegram ~ '^@?[A-Za-z0-9_]{5,32}$'",
            name="chk_users_telegram_format",
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR is_active = FALSE",
            name="chk_users_deleted_requires_inactive",
        ),
    )
    op.create_index(
        "idx_users_active",
        "users",
        ["id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND is_active = TRUE"),
    )

    op.create_table(
        "tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("group_code", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("slug", name="uq_tags_slug"),
        sa.CheckConstraint(
            "slug = lower(slug) AND slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
            name="chk_tags_slug_format",
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="chk_tags_name_not_blank"),
        sa.CheckConstraint(
            "group_code IS NULL OR btrim(group_code) <> ''",
            name="chk_tags_group_code_not_blank",
        ),
    )
    op.create_index(
        "idx_tags_group_code",
        "tags",
        ["group_code", "name"],
        unique=False,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("contacts", sa.Text(), nullable=False),
        sa.Column("format", event_format_enum, nullable=False),
        sa.Column(
            "status",
            event_status_enum,
            nullable=False,
            server_default=sa.text("'published'"),
        ),
        sa.Column("price_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("event_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_events_created_by_user_id_users",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("btrim(title) <> ''", name="chk_events_title_not_blank"),
        sa.CheckConstraint("btrim(description) <> ''", name="chk_events_description_not_blank"),
        sa.CheckConstraint("btrim(contacts) <> ''", name="chk_events_contacts_not_blank"),
        sa.CheckConstraint("price_minor >= 0", name="chk_events_price_non_negative"),
        sa.CheckConstraint("duration_minutes > 0", name="chk_events_duration_positive"),
        sa.CheckConstraint(
            "max_participants IS NULL OR max_participants > 0",
            name="chk_events_max_participants_positive",
        ),
        sa.CheckConstraint(
            "registration_start_at <= registration_end_at",
            name="chk_events_registration_window",
        ),
        sa.CheckConstraint(
            "registration_end_at <= event_start_at",
            name="chk_events_registration_before_start",
        ),
        sa.CheckConstraint(
            "recurrence_rule IS NULL OR btrim(recurrence_rule) <> ''",
            name="chk_events_recurrence_not_blank",
        ),
        sa.CheckConstraint(
            """
            (status = 'published' AND cancelled_at IS NULL AND completed_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL)
            OR (status = 'completed' AND completed_at IS NOT NULL AND cancelled_at IS NULL)
            """,
            name="chk_events_status_timestamps",
        ),
    )
    op.create_index(
        "idx_events_public_feed",
        "events",
        ["event_start_at", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'published'"),
    )
    op.create_index(
        "idx_events_creator",
        "events",
        ["created_by_user_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_events_status_start",
        "events",
        ["status", "event_start_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_events_format_public",
        "events",
        ["format", "event_start_at", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'published'"),
    )

    op.create_table(
        "event_tags",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_event_tags_event_id_events",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name="fk_event_tags_tag_id_tags",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id", "tag_id", name="pk_event_tags"),
    )
    op.create_index(
        "idx_event_tags_tag_event",
        "event_tags",
        ["tag_id", "event_id"],
        unique=False,
    )

    op.create_table(
        "event_registrations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            registration_status_enum,
            nullable=False,
            server_default=sa.text("'registered'"),
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_event_registrations_event_id_events",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_event_registrations_user_id_users",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_registrations_event_user"),
        sa.CheckConstraint(
            """
            (status = 'registered' AND cancelled_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
            """,
            name="chk_event_registrations_status_timestamps",
        ),
    )
    op.create_index(
        "idx_event_registrations_event_active",
        "event_registrations",
        ["event_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'registered'"),
    )
    op.create_index(
        "idx_event_registrations_user_active",
        "event_registrations",
        ["user_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'registered'"),
    )

    op.execute(
        """
        CREATE TRIGGER trg_users_set_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tags_set_updated_at
        BEFORE UPDATE ON tags
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_set_updated_at
        BEFORE UPDATE ON events
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_event_registrations_set_updated_at
        BEFORE UPDATE ON event_registrations
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_event_registrations_set_updated_at ON event_registrations")
    op.execute("DROP TRIGGER IF EXISTS trg_events_set_updated_at ON events")
    op.execute("DROP TRIGGER IF EXISTS trg_tags_set_updated_at ON tags")
    op.execute("DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users")

    op.drop_index("idx_event_registrations_user_active", table_name="event_registrations")
    op.drop_index("idx_event_registrations_event_active", table_name="event_registrations")
    op.drop_table("event_registrations")

    op.drop_index("idx_event_tags_tag_event", table_name="event_tags")
    op.drop_table("event_tags")

    op.drop_index("idx_events_format_public", table_name="events")
    op.drop_index("idx_events_status_start", table_name="events")
    op.drop_index("idx_events_creator", table_name="events")
    op.drop_index("idx_events_public_feed", table_name="events")
    op.drop_table("events")

    op.drop_index("idx_tags_group_code", table_name="tags")
    op.drop_table("tags")

    op.drop_index("idx_users_active", table_name="users")
    op.drop_table("users")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    bind = op.get_bind()
    registration_status_enum.drop(bind, checkfirst=True)
    event_status_enum.drop(bind, checkfirst=True)
    event_format_enum.drop(bind, checkfirst=True)
