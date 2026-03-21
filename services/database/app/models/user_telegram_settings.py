from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.user import User


class UserTelegramSettings(Base, TimestampMixin):
    __tablename__ = "user_telegram_settings"
    __table_args__ = (
        CheckConstraint(
            "telegram_user_id IS NULL OR telegram_user_id > 0",
            name="chk_user_tg_settings_telegram_user_id_positive",
        ),
        CheckConstraint(
            "telegram_chat_id IS NULL OR telegram_chat_id > 0",
            name="chk_user_tg_settings_telegram_chat_id_positive",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
    )
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
    )
    reminder_24h_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    reminder_1h_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )

    user: Mapped["User"] = relationship(
        back_populates="telegram_settings",
        lazy="selectin",
    )
