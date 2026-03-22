from __future__ import annotations

from datetime import datetime, timezone

from app.models import Event, EventRegistration, Tag, User
from app.models.enums import EventStatus
from app.schemas.event import (
    EventListItemResponse,
    EventResponse,
    ParticipantResponse,
    RegisteredEventListItemResponse,
    RegistrationResponse,
)
from app.schemas.tg import TelegramDueJobResponse
from app.schemas.tag import TagSummary
from app.schemas.user import UserResponse, UserSummary


def is_registration_open(event: Event, now: datetime | None = None) -> bool:
    reference_time = now or datetime.now(timezone.utc)
    return (
        event.deleted_at is None
        and event.status == EventStatus.PUBLISHED
        and event.registration_start_at <= reference_time <= event.registration_end_at
    )


def to_user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def to_user_summary(user: User) -> UserSummary:
    return UserSummary.model_validate(user)


def to_tag_summary(tag: Tag) -> TagSummary:
    return TagSummary.model_validate(tag)


def to_event_list_item(event: Event, registered_count: int = 0) -> EventListItemResponse:
    return EventListItemResponse(
        id=event.id,
        title=event.title,
        format=event.format,
        status=event.status,
        price_minor=event.price_minor,
        event_start_at=event.event_start_at,
        max_participants=event.max_participants,
        registered_count=registered_count,
        tag_slugs=[tag.slug for tag in event.tags],
        has_photo=event.photo_data is not None,
    )


def to_event_response(event: Event, registered_count: int = 0) -> EventResponse:
    return EventResponse(
        id=event.id,
        created_by_user_id=event.created_by_user_id,
        title=event.title,
        description=event.description,
        photo_url=event.photo_url,
        contacts=event.contacts,
        format=event.format,
        status=event.status,
        price_minor=event.price_minor,
        event_start_at=event.event_start_at,
        registration_start_at=event.registration_start_at,
        registration_end_at=event.registration_end_at,
        duration_minutes=event.duration_minutes,
        max_participants=event.max_participants,
        recurrence_rule=event.recurrence_rule,
        attendance_ask_enabled=event.attendance_ask_enabled,
        cancelled_at=event.cancelled_at,
        completed_at=event.completed_at,
        deleted_at=event.deleted_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
        registered_count=registered_count,
        is_registration_open=is_registration_open(event),
        creator=to_user_summary(event.creator) if event.creator else None,
        tags=[to_tag_summary(tag) for tag in event.tags],
        tag_slugs=[tag.slug for tag in event.tags],
        has_photo=event.photo_data is not None,
    )


def to_registration_response(registration: EventRegistration) -> RegistrationResponse:
    return RegistrationResponse.model_validate(registration)


def to_participant_response(registration: EventRegistration) -> ParticipantResponse:
    return ParticipantResponse(
        user_id=registration.user_id,
        full_name=registration.user.full_name,
        telegram=registration.user.telegram,
        university=registration.user.university,
        work_place=registration.user.work_place,
        status=registration.status,
        registered_at=registration.registered_at,
        checked_in_at=registration.checked_in_at,
    )


def to_registered_event_list_item(
    registration: EventRegistration,
    registered_count: int = 0,
) -> RegisteredEventListItemResponse:
    event = registration.event
    return RegisteredEventListItemResponse(
        id=event.id,
        title=event.title,
        format=event.format,
        status=event.status,
        price_minor=event.price_minor,
        event_start_at=event.event_start_at,
        max_participants=event.max_participants,
        registered_count=registered_count,
        tag_slugs=[tag.slug for tag in event.tags],
        registration_status=registration.status,
        registered_at=registration.registered_at,
        cancelled_at=registration.cancelled_at,
    )


def to_tg_due_job_response(job) -> TelegramDueJobResponse:
    telegram_username = None
    if job.user and job.user.telegram:
        telegram_username = str(job.user.telegram).strip()

    return TelegramDueJobResponse(
        job_id=job.id,
        event_id=job.event_id,
        user_id=job.user_id,
        chat_id=job.telegram_chat_id,
        telegram_username=telegram_username,
        kind=job.kind,
        scheduled_at=job.scheduled_at,
        title=job.event.title,
        starts_at=job.event.event_start_at,
        request_id=job.request_id,
    )
