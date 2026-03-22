from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.event_registration import EventRegistration
    from app.models.telegram_notification_job import TelegramNotificationJob
    from app.models.user_telegram_settings import UserTelegramSettings


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("btrim(email::text) <> ''", name="chk_users_email_not_blank"),
        CheckConstraint("btrim(password_hash) <> ''", name="chk_users_password_hash_not_blank"),
        CheckConstraint("btrim(full_name) <> ''", name="chk_users_full_name_not_blank"),
        CheckConstraint(
            "telegram IS NULL OR telegram ~ '^@?[A-Za-z0-9_]{5,32}$'",
            name="chk_users_telegram_format",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR is_active = FALSE",
            name="chk_users_deleted_requires_inactive",
        ),
        CheckConstraint(
            "photo_size_bytes IS NULL OR photo_size_bytes BETWEEN 1 AND 5242880",
            name="chk_users_photo_size_limit",
        ),
        CheckConstraint(
            "photo_content_type IS NULL OR btrim(photo_content_type) <> ''",
            name="chk_users_photo_content_type_not_blank",
        ),
        CheckConstraint(
            """
            (photo_data IS NULL AND photo_content_type IS NULL AND photo_size_bytes IS NULL)
            OR (photo_data IS NOT NULL AND photo_content_type IS NOT NULL AND photo_size_bytes IS NOT NULL)
            """,
            name="chk_users_photo_fields_consistency",
        ),
        Index(
            "idx_users_active",
            "id",
            postgresql_where=text("deleted_at IS NULL AND is_active = TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    university: Mapped[str | None] = mapped_column(Text, nullable=True)
    faculty: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )

    created_events: Mapped[list["Event"]] = relationship(
        back_populates="creator",
        lazy="selectin",
    )
    registrations: Mapped[list["EventRegistration"]] = relationship(
        back_populates="user",
        lazy="selectin",
    )
    telegram_settings: Mapped["UserTelegramSettings | None"] = relationship(
        back_populates="user",
        lazy="selectin",
        uselist=False,
    )
    telegram_jobs: Mapped[list["TelegramNotificationJob"]] = relationship(
        back_populates="user",
        lazy="selectin",
        passive_deletes=True,
    )

    @property
    def has_photo(self) -> bool:
        return self.photo_data is not None
