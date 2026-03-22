from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: User) -> None:
        self.session.add(user)

    def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
        return self.session.scalar(stmt)

    def get_by_id_for_update(self, user_id: UUID) -> User | None:
        stmt = (
            select(User)
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def get_active_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        return self.session.scalar(stmt)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.session.scalar(stmt)

    def get_by_telegram_username(self, username: str) -> User | None:
        normalized = username.strip().lower()
        if not normalized:
            return None

        with_at = normalized if normalized.startswith("@") else f"@{normalized}"
        without_at = normalized[1:] if normalized.startswith("@") else normalized

        stmt = select(User).where(
            User.deleted_at.is_(None),
            func.lower(func.coalesce(User.telegram, "")).in_([with_at, without_at]),
        )
        return self.session.scalar(stmt)
