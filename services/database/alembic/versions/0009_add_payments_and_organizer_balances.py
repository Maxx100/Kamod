"""add payments and organizer balances

Revision ID: 0009_payments_balance
Revises: 0008_event_reg_checked_in
Create Date: 2026-03-22 19:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_payments_balance"
down_revision = "0008_event_reg_checked_in"
branch_labels = None
depends_on = None


payment_status_enum = postgresql.ENUM(
    "pending",
    "succeeded",
    "cancelled",
    "expired",
    name="payment_status",
)


def upgrade() -> None:
    op.create_table(
        "organizer_balances",
        sa.Column("organizer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("available_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("pending_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("settled_total_minor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["organizer_user_id"], ["users.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organizer_user_id", name="pk_organizer_balances"),
        sa.CheckConstraint("available_minor >= 0", name="chk_organizer_balances_available_non_negative"),
        sa.CheckConstraint("pending_minor >= 0", name="chk_organizer_balances_pending_non_negative"),
        sa.CheckConstraint("settled_total_minor >= 0", name="chk_organizer_balances_settled_total_non_negative"),
    )

    op.create_table(
        "payment_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organizer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'yookassa'")),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("ticket_title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'RUB'")),
        sa.Column("status", payment_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], onupdate="RESTRICT", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organizer_user_id"], ["users.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("provider_payment_id", name="uq_payment_transactions_provider_payment_id"),
        sa.CheckConstraint("btrim(provider) <> ''", name="chk_payment_transactions_provider_not_blank"),
        sa.CheckConstraint(
            "provider_payment_id IS NULL OR btrim(provider_payment_id) <> ''",
            name="chk_payment_transactions_provider_payment_id_not_blank",
        ),
        sa.CheckConstraint(
            "ticket_title IS NULL OR btrim(ticket_title) <> ''",
            name="chk_payment_transactions_ticket_title_not_blank",
        ),
        sa.CheckConstraint(
            "description IS NULL OR btrim(description) <> ''",
            name="chk_payment_transactions_description_not_blank",
        ),
        sa.CheckConstraint("amount_minor >= 0", name="chk_payment_transactions_amount_non_negative"),
        sa.CheckConstraint("currency = 'RUB'", name="chk_payment_transactions_currency_rub"),
        sa.CheckConstraint(
            """
            (status = 'pending' AND paid_at IS NULL AND cancelled_at IS NULL AND expired_at IS NULL)
            OR (status = 'succeeded' AND paid_at IS NOT NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
            OR (status = 'expired' AND expired_at IS NOT NULL)
            """,
            name="chk_payment_transactions_status_timestamps",
        ),
        sa.CheckConstraint(
            "settled_at IS NULL OR settlement_due_at IS NOT NULL",
            name="chk_payment_transactions_settled_requires_due_at",
        ),
    )

    op.create_index(
        "idx_payment_transactions_user_created",
        "payment_transactions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_payment_transactions_organizer_settlement_due",
        "payment_transactions",
        ["organizer_user_id", "settlement_due_at"],
        unique=False,
        postgresql_where=sa.text("status = 'succeeded' AND settled_at IS NULL"),
    )

    for table_name in ("organizer_balances", "payment_transactions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_updated_at
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    for table_name in ("payment_transactions", "organizer_balances"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_updated_at ON {table_name}")

    op.drop_index("idx_payment_transactions_organizer_settlement_due", table_name="payment_transactions")
    op.drop_index("idx_payment_transactions_user_created", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_table("organizer_balances")

    payment_status_enum.drop(op.get_bind(), checkfirst=True)
