from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.event_tag import event_tags
from app.models.mixins import TimestampMixin


if TYPE_CHECKING:
    from app.models.event import Event


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint(
            "slug = lower(slug) AND slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
            name="chk_tags_slug_format",
        ),
        CheckConstraint("btrim(name) <> ''", name="chk_tags_name_not_blank"),
        CheckConstraint(
            "group_code IS NULL OR btrim(group_code) <> ''",
            name="chk_tags_group_code_not_blank",
        ),
        Index(
            "idx_tags_group_code",
            "group_code",
            "name",
            postgresql_where=text("is_active = TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    group_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )

    events: Mapped[list["Event"]] = relationship(
        secondary=event_tags,
        back_populates="tags",
        lazy="selectin",
    )
