from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.db import get_db
from app.services import EventService, RegistrationService, TelegramService, UserService


DatabaseSession = Annotated[Session, Depends(get_db)]


def get_current_user_id(x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None) -> UUID:
    if x_user_id is None:
        raise UnauthorizedError("Missing X-User-Id header")

    try:
        return UUID(x_user_id)
    except ValueError as exc:
        raise UnauthorizedError("Invalid X-User-Id header") from exc


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_user_service(session: DatabaseSession) -> UserService:
    return UserService(session)


def get_event_service(session: DatabaseSession) -> EventService:
    return EventService(session)


def get_registration_service(session: DatabaseSession) -> RegistrationService:
    return RegistrationService(session)


def get_telegram_service(session: DatabaseSession) -> TelegramService:
    return TelegramService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
RegistrationServiceDep = Annotated[RegistrationService, Depends(get_registration_service)]
TelegramServiceDep = Annotated[TelegramService, Depends(get_telegram_service)]
