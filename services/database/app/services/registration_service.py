from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import EventRegistration
from app.models.enums import EventStatus, RegistrationStatus
from app.repositories import EventRepository, RegistrationRepository, UserRepository
from app.schemas.event import (
    ParticipantListResponse,
    ParticipantQueryParams,
    RegisteredEventListResponse,
    RegisteredEventsQueryParams,
    RegistrationResponse,
)
from app.services.mappers import (
    to_participant_response,
    to_registered_event_list_item,
    to_registration_response,
)


class RegistrationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.events = EventRepository(session)
        self.registrations = RegistrationRepository(session)
        self.users = UserRepository(session)

    def register_for_event(
        self,
        event_id: UUID,
        current_user_id: UUID,
    ) -> tuple[RegistrationResponse, bool]:
        created = False

        with self.session.begin():
            user = self.users.get_active_by_id(current_user_id)
            if user is None:
                raise NotFoundError("User not found")

            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")

            now = datetime.now(timezone.utc)
            self._ensure_registration_is_open(event.status, event.registration_start_at, event.registration_end_at, now)

            registration = self.registrations.get_for_update(event_id, current_user_id)
            if registration is not None and registration.status == RegistrationStatus.REGISTERED:
                raise ConflictError("User is already registered for this event")

            active_registrations = self.registrations.count_active_for_event(event_id)
            if event.max_participants is not None and active_registrations >= event.max_participants:
                raise ConflictError("Event participant limit has been reached")

            if registration is None:
                registration = EventRegistration(
                    event_id=event_id,
                    user_id=current_user_id,
                    status=RegistrationStatus.REGISTERED,
                    registered_at=now,
                    cancelled_at=None,
                )
                self.registrations.add(registration)
                created = True
            else:
                registration.status = RegistrationStatus.REGISTERED
                registration.registered_at = now
                registration.cancelled_at = None

            self.session.flush()

        return to_registration_response(registration), created

    def cancel_registration(self, event_id: UUID, current_user_id: UUID) -> None:
        with self.session.begin():
            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")
            if event.status == EventStatus.COMPLETED:
                raise ConflictError("Registrations cannot be cancelled for completed events")

            registration = self.registrations.get_for_update(event_id, current_user_id)
            if registration is None or registration.status != RegistrationStatus.REGISTERED:
                raise NotFoundError("Active registration not found")

            registration.status = RegistrationStatus.CANCELLED
            registration.cancelled_at = datetime.now(timezone.utc)

    def list_participants(
        self,
        event_id: UUID,
        current_user_id: UUID,
        params: ParticipantQueryParams,
    ) -> ParticipantListResponse:
        event = self.events.get_by_id(event_id)
        if event is None:
            raise NotFoundError("Event not found")
        if event.created_by_user_id != current_user_id:
            raise ForbiddenError("Only the event creator can view participants")

        registrations, total = self.registrations.list_participants(event_id, params)
        return ParticipantListResponse(
            items=[to_participant_response(registration) for registration in registrations],
            limit=params.limit,
            offset=params.offset,
            total=total,
        )

    def list_user_registered_events(
        self,
        user_id: UUID,
        current_user_id: UUID,
        params: RegisteredEventsQueryParams,
    ) -> RegisteredEventListResponse:
        if user_id != current_user_id:
            raise ForbiddenError("You can only access your own registrations")

        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")

        registrations, total = self.registrations.list_user_registrations(user_id, params)
        event_ids = [registration.event_id for registration in registrations]
        counts = self.registrations.get_active_counts_by_event_ids(event_ids)

        return RegisteredEventListResponse(
            items=[
                to_registered_event_list_item(registration, counts.get(registration.event_id, 0))
                for registration in registrations
            ],
            limit=params.limit,
            offset=params.offset,
            total=total,
        )

    @staticmethod
    def _ensure_registration_is_open(
        event_status: EventStatus,
        registration_start_at,
        registration_end_at,
        now: datetime,
    ) -> None:
        if event_status != EventStatus.PUBLISHED:
            raise ConflictError("Registration is not available for this event")
        if now < registration_start_at:
            raise ConflictError("Registration has not started yet")
        if now > registration_end_at:
            raise ConflictError("Registration is already closed")
