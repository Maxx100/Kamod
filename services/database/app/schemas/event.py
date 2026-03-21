from uuid import UUID

from pydantic import AwareDatetime, AnyHttpUrl, Field, model_validator

from app.models.enums import EventFormat, EventStatus, RegistrationStatus
from app.schemas.common import APIModel, NonEmptyStr, OffsetPagination, SlugStr, TimestampedResponse
from app.schemas.tag import TagSummary
from app.schemas.user import UserSummary


def _deduplicate_slugs(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class EventCreateRequest(APIModel):
    title: NonEmptyStr
    description: NonEmptyStr
    photo_url: AnyHttpUrl | None = None
    tag_slugs: list[SlugStr] = Field(default_factory=list)
    event_start_at: AwareDatetime
    registration_start_at: AwareDatetime
    registration_end_at: AwareDatetime
    format: EventFormat
    price_minor: int = Field(default=0, ge=0)
    contacts: NonEmptyStr
    recurrence_rule: NonEmptyStr | None = None
    attendance_ask_enabled: bool = False
    max_participants: int | None = Field(default=None, gt=0)
    duration_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_dates(self) -> "EventCreateRequest":
        if self.registration_start_at > self.registration_end_at:
            raise ValueError("registration_start_at must be <= registration_end_at")
        if self.registration_end_at > self.event_start_at:
            raise ValueError("registration_end_at must be <= event_start_at")
        self.tag_slugs = _deduplicate_slugs(self.tag_slugs)
        return self


class EventUpdateRequest(APIModel):
    title: NonEmptyStr | None = None
    description: NonEmptyStr | None = None
    photo_url: AnyHttpUrl | None = None
    tag_slugs: list[SlugStr] | None = None
    event_start_at: AwareDatetime | None = None
    registration_start_at: AwareDatetime | None = None
    registration_end_at: AwareDatetime | None = None
    format: EventFormat | None = None
    price_minor: int | None = Field(default=None, ge=0)
    contacts: NonEmptyStr | None = None
    recurrence_rule: NonEmptyStr | None = None
    attendance_ask_enabled: bool | None = None
    max_participants: int | None = Field(default=None, gt=0)
    duration_minutes: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_payload(self) -> "EventUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if self.tag_slugs is not None:
            self.tag_slugs = _deduplicate_slugs(self.tag_slugs)
        provided_dates = [
            self.registration_start_at,
            self.registration_end_at,
            self.event_start_at,
        ]
        if all(value is not None for value in provided_dates):
            if self.registration_start_at > self.registration_end_at:
                raise ValueError("registration_start_at must be <= registration_end_at")
            if self.registration_end_at > self.event_start_at:
                raise ValueError("registration_end_at must be <= event_start_at")
        return self


class EventListQueryParams(APIModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: EventStatus | None = None
    created_by_user_id: UUID | None = None
    tag: SlugStr | None = None
    format: EventFormat | None = None
    is_free: bool | None = None
    starts_from: AwareDatetime | None = None
    starts_to: AwareDatetime | None = None
    registration_open: bool | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "EventListQueryParams":
        if self.starts_from and self.starts_to and self.starts_from > self.starts_to:
            raise ValueError("starts_from must be <= starts_to")
        return self


class EventListItemResponse(APIModel):
    id: UUID
    title: str
    format: EventFormat
    status: EventStatus
    price_minor: int
    event_start_at: AwareDatetime
    max_participants: int | None = None
    registered_count: int = 0
    tag_slugs: list[SlugStr] = Field(default_factory=list)


class EventListResponse(OffsetPagination):
    items: list[EventListItemResponse]


class EventResponse(TimestampedResponse):
    id: UUID
    created_by_user_id: UUID
    title: str
    description: str
    photo_url: AnyHttpUrl | None = None
    contacts: str
    format: EventFormat
    status: EventStatus
    price_minor: int
    event_start_at: AwareDatetime
    registration_start_at: AwareDatetime
    registration_end_at: AwareDatetime
    duration_minutes: int
    max_participants: int | None = None
    recurrence_rule: str | None = None
    attendance_ask_enabled: bool
    cancelled_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    deleted_at: AwareDatetime | None = None
    registered_count: int = 0
    is_registration_open: bool = False
    creator: UserSummary | None = None
    tags: list[TagSummary] = Field(default_factory=list)
    tag_slugs: list[SlugStr] = Field(default_factory=list)


class RegistrationResponse(TimestampedResponse):
    id: UUID
    event_id: UUID
    user_id: UUID
    status: RegistrationStatus
    registered_at: AwareDatetime
    cancelled_at: AwareDatetime | None = None


class ParticipantQueryParams(APIModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: RegistrationStatus = RegistrationStatus.REGISTERED


class ParticipantResponse(APIModel):
    user_id: UUID
    full_name: str
    telegram: str | None = None
    status: RegistrationStatus
    registered_at: AwareDatetime


class ParticipantListResponse(OffsetPagination):
    items: list[ParticipantResponse]


class RegisteredEventsQueryParams(APIModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: RegistrationStatus | None = None


class CreatedEventsQueryParams(APIModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    status: EventStatus | None = None


class RegisteredEventListItemResponse(EventListItemResponse):
    registration_status: RegistrationStatus
    registered_at: AwareDatetime
    cancelled_at: AwareDatetime | None = None


class RegisteredEventListResponse(OffsetPagination):
    items: list[RegisteredEventListItemResponse]
