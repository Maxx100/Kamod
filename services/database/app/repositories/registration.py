from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, EventRegistration
from app.models.enums import RegistrationStatus
from app.schemas.event import ParticipantQueryParams, RegisteredEventsQueryParams


class RegistrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registration: EventRegistration) -> None:
        self.session.add(registration)

    def get_by_id(self, registration_id: UUID) -> EventRegistration | None:
        stmt = select(EventRegistration).where(EventRegistration.id == registration_id)
        return self.session.scalar(stmt)

    def get_for_update(self, event_id: UUID, user_id: UUID) -> EventRegistration | None:
        stmt = (
            select(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == user_id,
            )
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def count_active_for_event(self, event_id: UUID) -> int:
        stmt = select(func.count(EventRegistration.id)).where(
            EventRegistration.event_id == event_id,
            EventRegistration.status == RegistrationStatus.REGISTERED,
        )
        return self.session.scalar(stmt) or 0

    def get_active_counts_by_event_ids(self, event_ids: list[UUID]) -> dict[UUID, int]:
        if not event_ids:
            return {}

        stmt = (
            select(
                EventRegistration.event_id,
                func.count(EventRegistration.id),
            )
            .where(
                EventRegistration.event_id.in_(event_ids),
                EventRegistration.status == RegistrationStatus.REGISTERED,
            )
            .group_by(EventRegistration.event_id)
        )
        return {event_id: count for event_id, count in self.session.execute(stmt).all()}

    def list_participants(
        self,
        event_id: UUID,
        params: ParticipantQueryParams,
    ) -> tuple[list[EventRegistration], int]:
        filters = [
            EventRegistration.event_id == event_id,
            EventRegistration.status == params.status,
        ]

        stmt = (
            select(EventRegistration)
            .where(*filters)
            .options(selectinload(EventRegistration.user))
            .order_by(EventRegistration.registered_at.asc(), EventRegistration.id.asc())
            .limit(params.limit)
            .offset(params.offset)
        )
        count_stmt = select(func.count(EventRegistration.id)).where(*filters)

        registrations = list(self.session.scalars(stmt).all())
        total = self.session.scalar(count_stmt) or 0
        return registrations, total

    def list_user_registrations(
        self,
        user_id: UUID,
        params: RegisteredEventsQueryParams,
    ) -> tuple[list[EventRegistration], int]:
        filters = [
            EventRegistration.user_id == user_id,
        ]
        if params.status is not None:
            filters.append(EventRegistration.status == params.status)

        stmt = (
            select(EventRegistration)
            .join(Event, EventRegistration.event_id == Event.id)
            .where(
                *filters,
                Event.deleted_at.is_(None),
            )
            .options(
                selectinload(EventRegistration.event).selectinload(Event.tags),
                selectinload(EventRegistration.event).selectinload(Event.creator),
            )
            .order_by(EventRegistration.registered_at.desc(), EventRegistration.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        count_stmt = (
            select(func.count(EventRegistration.id))
            .join(Event, EventRegistration.event_id == Event.id)
            .where(
                *filters,
                Event.deleted_at.is_(None),
            )
        )

        registrations = list(self.session.scalars(stmt).all())
        total = self.session.scalar(count_stmt) or 0
        return registrations, total
