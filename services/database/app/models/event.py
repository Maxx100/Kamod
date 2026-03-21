from __future__ import annotations

from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import EventFormat, EventStatus, enum_values
from app.models.event_tag import event_tags
from app.models.mixins import SoftDeleteMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.telegram_notification_job import TelegramNotificationJob
    from app.models.event_registration import EventRegistration
    from app.models.tag import Tag
    from app.models.user import User


class Event(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="chk_events_title_not_blank"),
        CheckConstraint("btrim(description) <> ''", name="chk_events_description_not_blank"),
        CheckConstraint("btrim(contacts) <> ''", name="chk_events_contacts_not_blank"),
        CheckConstraint("price_minor >= 0", name="chk_events_price_non_negative"),
        CheckConstraint("duration_minutes > 0", name="chk_events_duration_positive"),
        CheckConstraint(
            "max_participants IS NULL OR max_participants > 0",
            name="chk_events_max_participants_positive",
        ),
        CheckConstraint(
            "attendance_ask_enabled IN (TRUE, FALSE)",
            name="chk_events_attendance_ask_enabled_boolean",
        ),
        CheckConstraint(
            "registration_start_at <= registration_end_at",
            name="chk_events_registration_window",
        ),
        CheckConstraint(
            "registration_end_at <= event_start_at",
            name="chk_events_registration_before_start",
        ),
        CheckConstraint(
            "recurrence_rule IS NULL OR btrim(recurrence_rule) <> ''",
            name="chk_events_recurrence_not_blank",
        ),
        CheckConstraint(
            "photo_size_bytes IS NULL OR photo_size_bytes BETWEEN 1 AND 10485760",
            name="chk_events_photo_size_limit",
        ),
        CheckConstraint(
            "photo_content_type IS NULL OR btrim(photo_content_type) <> ''",
            name="chk_events_photo_content_type_not_blank",
        ),
        CheckConstraint(
            """
            (photo_data IS NULL AND photo_content_type IS NULL AND photo_size_bytes IS NULL)
            OR (photo_data IS NOT NULL AND photo_content_type IS NOT NULL AND photo_size_bytes IS NOT NULL)
            """,
            name="chk_events_photo_fields_consistency",
        ),
        CheckConstraint(
            """
            (status = 'published' AND cancelled_at IS NULL AND completed_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL)
            OR (status = 'completed' AND completed_at IS NOT NULL AND cancelled_at IS NULL)
            """,
            name="chk_events_status_timestamps",
        ),
        Index(
            "idx_events_public_feed",
            "event_start_at",
            "id",
            postgresql_where=text("deleted_at IS NULL AND status = 'published'"),
        ),
        Index(
            "idx_events_creator",
            "created_by_user_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_events_status_start",
            "status",
            "event_start_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_events_format_public",
            "format",
            "event_start_at",
            "id",
            postgresql_where=text("deleted_at IS NULL AND status = 'published'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contacts: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[EventFormat] = mapped_column(
        Enum(EventFormat, name="event_format", values_callable=enum_values),
        nullable=False,
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", values_callable=enum_values),
        nullable=False,
        default=EventStatus.PUBLISHED,
        server_default=text("'published'"),
    )
    price_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    event_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    attendance_ask_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creator: Mapped["User"] = relationship(
        back_populates="created_events",
        lazy="selectin",
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=event_tags,
        back_populates="events",
        lazy="selectin",
    )
    registrations: Mapped[list["EventRegistration"]] = relationship(
        back_populates="event",
        lazy="selectin",
        passive_deletes=True,
    )
    telegram_jobs: Mapped[list["TelegramNotificationJob"]] = relationship(
        back_populates="event",
        lazy="selectin",
        passive_deletes=True,
    )
