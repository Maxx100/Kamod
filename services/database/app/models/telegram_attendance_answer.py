from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AttendanceAnswer, enum_values
from app.models.mixins import TimestampMixin


class TelegramAttendanceAnswer(Base, TimestampMixin):
    __tablename__ = "telegram_attendance_answers"
    __table_args__ = (
        UniqueConstraint("request_id", "telegram_user_id", name="uq_tg_attendance_answers_request_telegram_user"),
        CheckConstraint(
            "telegram_user_id > 0",
            name="chk_tg_attendance_answers_telegram_user_id_positive",
        ),
        Index(
            "idx_tg_attendance_answers_event_user",
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
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_notification_jobs.request_id", onupdate="RESTRICT", ondelete="CASCADE"),
        nullable=False,
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
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    answer: Mapped[AttendanceAnswer] = mapped_column(
        Enum(AttendanceAnswer, name="attendance_answer", values_callable=enum_values),
        nullable=False,
    )
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
