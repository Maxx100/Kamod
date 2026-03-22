from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.user import User


class OrganizerBalance(Base, TimestampMixin):
    __tablename__ = "organizer_balances"
    __table_args__ = (
        CheckConstraint("available_minor >= 0", name="chk_organizer_balances_available_non_negative"),
        CheckConstraint("pending_minor >= 0", name="chk_organizer_balances_pending_non_negative"),
        CheckConstraint("settled_total_minor >= 0", name="chk_organizer_balances_settled_total_non_negative"),
    )

    organizer_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", onupdate="RESTRICT", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    available_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    pending_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    settled_total_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    organizer: Mapped["User"] = relationship(lazy="selectin")
