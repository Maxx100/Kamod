from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import RegistrationStatus, enum_values
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventRegistration(Base, TimestampMixin):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_event_registrations_event_user"),
        CheckConstraint(
            """
            (status = 'registered' AND cancelled_at IS NULL)
            OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
            """,
            name="chk_event_registrations_status_timestamps",
        ),
        CheckConstraint(
            """
            checked_in_at IS NULL OR status = 'registered'
            """,
            name="chk_event_registrations_checked_in_requires_registered",
        ),
        Index(
            "idx_event_registrations_event_active",
            "event_id",
            "created_at",
            postgresql_where=text("status = 'registered'"),
        ),
        Index(
            "idx_event_registrations_user_active",
            "user_id",
            "created_at",
            postgresql_where=text("status = 'registered'"),
        ),
        Index(
            "idx_event_registrations_event_checked_in",
            "event_id",
            "checked_in_at",
            postgresql_where=text("checked_in_at IS NOT NULL"),
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
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, name="registration_status", values_callable=enum_values),
        nullable=False,
        default=RegistrationStatus.REGISTERED,
        server_default=text("'registered'"),
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    event: Mapped["Event"] = relationship(
        back_populates="registrations",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        back_populates="registrations",
        lazy="selectin",
    )
