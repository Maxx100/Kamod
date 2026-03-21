from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag


class TagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_by_slugs(self, slugs: list[str]) -> list[Tag]:
        if not slugs:
            return []

        stmt = (
            select(Tag)
            .where(
                Tag.slug.in_(slugs),
                Tag.is_active.is_(True),
            )
            .order_by(Tag.slug.asc())
        )
        return list(self.session.scalars(stmt).all())
