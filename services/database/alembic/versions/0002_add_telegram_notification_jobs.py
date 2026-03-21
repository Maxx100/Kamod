"""add telegram notification jobs

Revision ID: 0002_tg_notification_jobs
Revises: 0001_create_event_service_schema
Create Date: 2026-03-21 15:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_tg_notification_jobs"
down_revision = "0001_create_event_service_schema"
branch_labels = None
depends_on = None


telegram_job_kind_enum = postgresql.ENUM(
    "reminder_24h",
    "reminder_1h",
    "attendance_ask_24h",
    name="telegram_job_kind",
)

telegram_job_status_enum = postgresql.ENUM(
    "pending",
    "claimed",
    "sent",
    "failed",
    "cancelled",
    name="telegram_job_status",
)

attendance_answer_enum = postgresql.ENUM(
    "yes",
    "no",
    name="attendance_answer",
)


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("attendance_ask_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "chk_events_attendance_ask_enabled_boolean",
        "events",
        "attendance_ask_enabled IN (TRUE, FALSE)",
    )

    op.create_table(
        "user_telegram_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("reminder_24h_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_1h_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_telegram_settings"),
        sa.UniqueConstraint("telegram_user_id", name="uq_user_telegram_settings_telegram_user_id"),
        sa.UniqueConstraint("telegram_chat_id", name="uq_user_telegram_settings_telegram_chat_id"),
        sa.CheckConstraint(
            "telegram_user_id IS NULL OR telegram_user_id > 0",
            name="chk_user_tg_settings_telegram_user_id_positive",
        ),
        sa.CheckConstraint(
            "telegram_chat_id IS NULL OR telegram_chat_id > 0",
            name="chk_user_tg_settings_telegram_chat_id_positive",
        ),
    )

    op.create_table(
        "telegram_notification_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", telegram_job_kind_enum, nullable=False),
        sa.Column(
            "status",
            telegram_job_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", "user_id", "kind", name="uq_tg_jobs_event_user_kind"),
        sa.UniqueConstraint("request_id", name="uq_tg_jobs_request_id"),
        sa.CheckConstraint(
            "telegram_chat_id > 0",
            name="chk_tg_jobs_telegram_chat_id_positive",
        ),
        sa.CheckConstraint(
            "telegram_user_id IS NULL OR telegram_user_id > 0",
            name="chk_tg_jobs_telegram_user_id_positive",
        ),
        sa.CheckConstraint(
            "telegram_message_id IS NULL OR telegram_message_id > 0",
            name="chk_tg_jobs_telegram_message_id_positive",
        ),
        sa.CheckConstraint(
            "claimed_by IS NULL OR btrim(claimed_by) <> ''",
            name="chk_tg_jobs_claimed_by_not_blank",
        ),
        sa.CheckConstraint(
            "error IS NULL OR btrim(error) <> ''",
            name="chk_tg_jobs_error_not_blank",
        ),
        sa.CheckConstraint(
            """
            (kind = 'attendance_ask_24h' AND request_id IS NOT NULL)
            OR (kind IN ('reminder_24h', 'reminder_1h') AND request_id IS NULL)
            """,
            name="chk_tg_jobs_request_id_required_for_attendance",
        ),
        sa.CheckConstraint(
            """
            (status = 'pending' AND claimed_at IS NULL AND sent_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'claimed' AND claimed_at IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'sent' AND sent_at IS NOT NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'failed' AND failed_at IS NOT NULL AND sent_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND sent_at IS NULL)
            """,
            name="chk_tg_jobs_status_timestamps",
        ),
    )
    op.create_index(
        "idx_tg_jobs_due_pending",
        "telegram_notification_jobs",
        ["scheduled_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_tg_jobs_event_user",
        "telegram_notification_jobs",
        ["event_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "telegram_attendance_answers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("answer", attendance_answer_enum, nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["request_id"], ["telegram_notification_jobs.request_id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.UniqueConstraint(
            "request_id",
            "telegram_user_id",
            name="uq_tg_attendance_answers_request_telegram_user",
        ),
        sa.CheckConstraint(
            "telegram_user_id > 0",
            name="chk_tg_attendance_answers_telegram_user_id_positive",
        ),
    )
    op.create_index(
        "idx_tg_attendance_answers_event_user",
        "telegram_attendance_answers",
        ["event_id", "user_id"],
        unique=False,
    )

    for table_name in (
        "user_telegram_settings",
        "telegram_notification_jobs",
        "telegram_attendance_answers",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_updated_at
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    for table_name in (
        "telegram_attendance_answers",
        "telegram_notification_jobs",
        "user_telegram_settings",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_updated_at ON {table_name}")

    op.drop_index("idx_tg_attendance_answers_event_user", table_name="telegram_attendance_answers")
    op.drop_table("telegram_attendance_answers")

    op.drop_index("idx_tg_jobs_event_user", table_name="telegram_notification_jobs")
    op.drop_index("idx_tg_jobs_due_pending", table_name="telegram_notification_jobs")
    op.drop_table("telegram_notification_jobs")

    op.drop_table("user_telegram_settings")

    op.drop_constraint("chk_events_attendance_ask_enabled_boolean", "events", type_="check")
    op.drop_column("events", "attendance_ask_enabled")

    attendance_answer_enum.drop(op.get_bind(), checkfirst=True)
    telegram_job_status_enum.drop(op.get_bind(), checkfirst=True)
    telegram_job_kind_enum.drop(op.get_bind(), checkfirst=True)
