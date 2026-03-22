from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import PaymentStatus, enum_values
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class PaymentTransaction(Base, TimestampMixin):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        CheckConstraint("btrim(provider) <> ''", name="chk_payment_transactions_provider_not_blank"),
        CheckConstraint(
            "provider_payment_id IS NULL OR btrim(provider_payment_id) <> ''",
            name="chk_payment_transactions_provider_payment_id_not_blank",
        ),
        CheckConstraint(
            "ticket_title IS NULL OR btrim(ticket_title) <> ''",
            name="chk_payment_transactions_ticket_title_not_blank",
        ),
        CheckConstraint(
            "description IS NULL OR btrim(description) <> ''",
            name="chk_payment_transactions_description_not_blank",
        ),
        CheckConstraint("amount_minor >= 0", name="chk_payment_transactions_amount_non_negative"),
        CheckConstraint("currency = 'RUB'", name="chk_payment_transactions_currency_rub"),
        CheckConstraint(
            """
            (status = 'pending' AND paid_at IS NULL AND cancelled_at IS NULL AND expired_at IS NULL)
            OR (status = 'succeeded' AND paid_at IS NOT NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
            OR (status = 'expired' AND expired_at IS NOT NULL)
            """,
            name="chk_payment_transactions_status_timestamps",
        ),
        CheckConstraint(
            "settled_at IS NULL OR settlement_due_at IS NOT NULL",
            name="chk_payment_transactions_settled_requires_due_at",
        ),
        Index(
            "idx_payment_transactions_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "idx_payment_transactions_organizer_settlement_due",
            "organizer_user_id",
            "settlement_due_at",
            postgresql_where=text("status = 'succeeded' AND settled_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", onupdate="RESTRICT", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="RESTRICT"),
        nullable=False,
    )
    organizer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="yookassa",
        server_default=text("'yookassa'"),
    )
    provider_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    ticket_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="RUB", server_default=text("'RUB'"))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=enum_values),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=text("'pending'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settlement_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event"] = relationship(lazy="selectin")
    user: Mapped["User"] = relationship(foreign_keys=[user_id], lazy="selectin")
    organizer: Mapped["User"] = relationship(foreign_keys=[organizer_user_id], lazy="selectin")
