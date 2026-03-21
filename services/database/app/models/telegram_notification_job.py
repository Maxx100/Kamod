from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import TelegramJobKind, TelegramJobStatus, enum_values
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class TelegramNotificationJob(Base, TimestampMixin):
    __tablename__ = "telegram_notification_jobs"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "kind", name="uq_tg_jobs_event_user_kind"),
        UniqueConstraint("request_id", name="uq_tg_jobs_request_id"),
        CheckConstraint(
            "telegram_chat_id > 0",
            name="chk_tg_jobs_telegram_chat_id_positive",
        ),
        CheckConstraint(
            "telegram_user_id IS NULL OR telegram_user_id > 0",
            name="chk_tg_jobs_telegram_user_id_positive",
        ),
        CheckConstraint(
            "telegram_message_id IS NULL OR telegram_message_id > 0",
            name="chk_tg_jobs_telegram_message_id_positive",
        ),
        CheckConstraint(
            "claimed_by IS NULL OR btrim(claimed_by) <> ''",
            name="chk_tg_jobs_claimed_by_not_blank",
        ),
        CheckConstraint(
            "error IS NULL OR btrim(error) <> ''",
            name="chk_tg_jobs_error_not_blank",
        ),
        CheckConstraint(
            """
            (kind = 'attendance_ask_24h' AND request_id IS NOT NULL)
            OR (kind IN ('reminder_24h', 'reminder_1h') AND request_id IS NULL)
            """,
            name="chk_tg_jobs_request_id_required_for_attendance",
        ),
        CheckConstraint(
            """
            (status = 'pending' AND claimed_at IS NULL AND sent_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'claimed' AND claimed_at IS NOT NULL AND sent_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'sent' AND sent_at IS NOT NULL AND failed_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'failed' AND failed_at IS NOT NULL AND sent_at IS NULL AND cancelled_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND sent_at IS NULL)
            """,
            name="chk_tg_jobs_status_timestamps",
        ),
        Index(
            "idx_tg_jobs_due_pending",
            "scheduled_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "idx_tg_jobs_event_user",
            "event_id",
            "user_id",
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
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[TelegramJobKind] = mapped_column(
        Enum(TelegramJobKind, name="telegram_job_kind", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[TelegramJobStatus] = mapped_column(
        Enum(TelegramJobStatus, name="telegram_job_status", values_callable=enum_values),
        nullable=False,
        default=TelegramJobStatus.PENDING,
        server_default=text("'pending'"),
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    claimed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event"] = relationship(
        back_populates="telegram_jobs",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        back_populates="telegram_jobs",
        lazy="selectin",
    )
