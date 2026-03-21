from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.models import Event
from app.models.enums import EventStatus
from app.repositories import EventRepository, RegistrationRepository, TagRepository, UserRepository
from app.schemas.event import (
    CreatedEventsQueryParams,
    EventCreateRequest,
    EventListQueryParams,
    EventListResponse,
    EventResponse,
    EventUpdateRequest,
)
from app.services.mappers import to_event_list_item, to_event_response
from app.services.telegram_service import TelegramService


class EventService:
    MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024

    def __init__(self, session: Session) -> None:
        self.session = session
        self.events = EventRepository(session)
        self.users = UserRepository(session)
        self.tags = TagRepository(session)
        self.registrations = RegistrationRepository(session)
        self.telegram = TelegramService(session)

    def create_event(self, current_user_id: UUID, payload: EventCreateRequest) -> EventResponse:
        with self.session.begin():
            creator = self.users.get_active_by_id(current_user_id)
            if creator is None:
                raise NotFoundError("User not found")

            tags = self._resolve_tags(payload.tag_slugs)
            event = Event(
                created_by_user_id=current_user_id,
                title=payload.title,
                description=payload.description,
                photo_url=self._stringify_url(payload.photo_url),
                contacts=payload.contacts,
                format=payload.format,
                status=EventStatus.PUBLISHED,
                price_minor=payload.price_minor,
                event_start_at=payload.event_start_at,
                registration_start_at=payload.registration_start_at,
                registration_end_at=payload.registration_end_at,
                duration_minutes=payload.duration_minutes,
                max_participants=payload.max_participants,
                recurrence_rule=payload.recurrence_rule,
                attendance_ask_enabled=payload.attendance_ask_enabled,
            )
            event.tags = tags
            self._validate_event_state(event)
            self.events.add(event)
            self.session.flush()
            event_id = event.id

        return self.get_event(event_id)

    def update_event(
        self,
        event_id: UUID,
        current_user_id: UUID,
        payload: EventUpdateRequest,
    ) -> EventResponse:
        with self.session.begin():
            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")

            self._ensure_creator_access(event, current_user_id)
            if event.status != EventStatus.PUBLISHED:
                raise ConflictError("Only published events can be edited")

            if "title" in payload.model_fields_set:
                event.title = payload.title
            if "description" in payload.model_fields_set:
                event.description = payload.description
            if "photo_url" in payload.model_fields_set:
                event.photo_url = self._stringify_url(payload.photo_url)
            if "event_start_at" in payload.model_fields_set:
                event.event_start_at = payload.event_start_at
            if "registration_start_at" in payload.model_fields_set:
                event.registration_start_at = payload.registration_start_at
            if "registration_end_at" in payload.model_fields_set:
                event.registration_end_at = payload.registration_end_at
            if "format" in payload.model_fields_set:
                event.format = payload.format
            if "price_minor" in payload.model_fields_set:
                event.price_minor = payload.price_minor
            if "contacts" in payload.model_fields_set:
                event.contacts = payload.contacts
            if "recurrence_rule" in payload.model_fields_set:
                event.recurrence_rule = payload.recurrence_rule
            if "attendance_ask_enabled" in payload.model_fields_set:
                event.attendance_ask_enabled = bool(payload.attendance_ask_enabled)
            if "max_participants" in payload.model_fields_set:
                event.max_participants = payload.max_participants
            if "duration_minutes" in payload.model_fields_set:
                event.duration_minutes = payload.duration_minutes
            if "tag_slugs" in payload.model_fields_set:
                event.tags = self._resolve_tags(payload.tag_slugs or [])

            self._validate_event_state(event)

            active_registrations = self.registrations.count_active_for_event(event.id)
            if (
                event.max_participants is not None
                and active_registrations > event.max_participants
            ):
                raise ConflictError("max_participants cannot be lower than registered participants")

            self.telegram.sync_jobs_for_event(event)

        return self.get_event(event_id)

    def cancel_event(self, event_id: UUID, current_user_id: UUID) -> EventResponse:
        with self.session.begin():
            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")

            self._ensure_creator_access(event, current_user_id)
            if event.status != EventStatus.PUBLISHED:
                raise ConflictError("Event is already cancelled or completed")

            event.status = EventStatus.CANCELLED
            event.cancelled_at = datetime.now(timezone.utc)
            event.completed_at = None
            self.telegram.sync_jobs_for_event(event)

        return self.get_event(event_id)

    def complete_event(self, event_id: UUID, current_user_id: UUID) -> EventResponse:
        with self.session.begin():
            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")

            self._ensure_creator_access(event, current_user_id)
            if event.status != EventStatus.PUBLISHED:
                raise ConflictError("Event is already cancelled or completed")

            event.status = EventStatus.COMPLETED
            event.completed_at = datetime.now(timezone.utc)
            event.cancelled_at = None
            self.telegram.sync_jobs_for_event(event)

        return self.get_event(event_id)

    def list_events(self, params: EventListQueryParams) -> EventListResponse:
        events, total = self.events.list_public(params)
        counts = self.registrations.get_active_counts_by_event_ids([event.id for event in events])
        return EventListResponse(
            items=[
                to_event_list_item(event, counts.get(event.id, 0))
                for event in events
            ],
            limit=params.limit,
            offset=params.offset,
            total=total,
        )

    def get_event(self, event_id: UUID) -> EventResponse:
        event = self.events.get_by_id(event_id)
        if event is None:
            raise NotFoundError("Event not found")

        registered_count = self.registrations.count_active_for_event(event_id)
        return to_event_response(event, registered_count)

    def list_created_events(
        self,
        user_id: UUID,
        params: CreatedEventsQueryParams,
    ) -> EventListResponse:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")

        events, total = self.events.list_created_by_user(user_id, params)
        counts = self.registrations.get_active_counts_by_event_ids([event.id for event in events])
        return EventListResponse(
            items=[
                to_event_list_item(event, counts.get(event.id, 0))
                for event in events
            ],
            limit=params.limit,
            offset=params.offset,
            total=total,
        )

    def upload_event_photo(
        self,
        event_id: UUID,
        current_user_id: UUID,
        *,
        content_type: str,
        data: bytes,
    ) -> EventResponse:
        if not data:
            raise UnprocessableError("Photo file is empty")
        if len(data) > self.MAX_PHOTO_SIZE_BYTES:
            raise UnprocessableError("Photo size must be <= 10MB")
        if not content_type.startswith("image/"):
            raise UnprocessableError("Only image files are allowed")

        with self.session.begin():
            event = self.events.get_for_update(event_id)
            if event is None:
                raise NotFoundError("Event not found")

            self._ensure_creator_access(event, current_user_id)

            event.photo_data = data
            event.photo_content_type = content_type
            event.photo_size_bytes = len(data)
            self.session.flush()

        return self.get_event(event_id)

    def get_event_photo(self, event_id: UUID) -> tuple[str, bytes]:
        event = self.events.get_by_id(event_id)
        if event is None:
            raise NotFoundError("Event not found")
        if event.photo_data is None or event.photo_content_type is None:
            raise NotFoundError("Event photo not found")
        return event.photo_content_type, bytes(event.photo_data)

    def _resolve_tags(self, tag_slugs: list[str]):
        if not tag_slugs:
            return []

        normalized_slugs = list(dict.fromkeys(tag_slugs))
        tags = self.tags.get_active_by_slugs(normalized_slugs)
        found_slugs = {tag.slug for tag in tags}
        missing_slugs = [slug for slug in normalized_slugs if slug not in found_slugs]
        if missing_slugs:
            raise UnprocessableError(
                f"Unknown or inactive tags: {', '.join(missing_slugs)}",
                code="unknown_tags",
            )
        return sorted(tags, key=lambda tag: normalized_slugs.index(tag.slug))

    def _validate_event_state(self, event: Event) -> None:
        if event.registration_start_at > event.registration_end_at:
            raise UnprocessableError("registration_start_at must be <= registration_end_at")
        if event.registration_end_at > event.event_start_at:
            raise UnprocessableError("registration_end_at must be <= event_start_at")
        if event.price_minor < 0:
            raise UnprocessableError("price_minor must be >= 0")
        if event.duration_minutes <= 0:
            raise UnprocessableError("duration_minutes must be > 0")
        if event.max_participants is not None and event.max_participants <= 0:
            raise UnprocessableError("max_participants must be > 0")

    def _ensure_creator_access(self, event: Event, current_user_id: UUID) -> None:
        if event.created_by_user_id != current_user_id:
            raise ForbiddenError("Only the event creator can perform this action")

    @staticmethod
    def _stringify_url(value) -> str | None:
        if value is None:
            return None
        return str(value)
