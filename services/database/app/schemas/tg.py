from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.models.enums import AttendanceAnswer, TelegramJobKind
from app.schemas.common import APIModel, NonEmptyStr


def _ensure_utc(value: AwareDatetime) -> AwareDatetime:
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ValueError("datetime must be in UTC")
    return value


class TelegramDueJobsQuery(APIModel):
    from_at: AwareDatetime = Field(alias="from")
    to_at: AwareDatetime = Field(alias="to")
    limit: int = Field(default=500, ge=1, le=500)

    @field_validator("from_at", "to_at")
    @classmethod
    def validate_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def validate_window(self) -> "TelegramDueJobsQuery":
        if self.from_at > self.to_at:
            raise ValueError("from must be <= to")
        return self


class TelegramDueJobResponse(APIModel):
    job_id: UUID
    event_id: UUID
    user_id: UUID
    chat_id: int
    telegram_username: str | None = None
    kind: TelegramJobKind
    scheduled_at: AwareDatetime
    title: str
    starts_at: AwareDatetime
    request_id: UUID | None = None


class TelegramClaimJobRequest(APIModel):
    worker_id: NonEmptyStr


class TelegramClaimJobResponse(APIModel):
    ok: bool = True
    claimed: bool


class TelegramCompleteJobRequest(APIModel):
    sent_at: AwareDatetime
    telegram_message_id: int = Field(gt=0)

    @field_validator("sent_at")
    @classmethod
    def validate_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return _ensure_utc(value)


class TelegramFailJobRequest(APIModel):
    failed_at: AwareDatetime
    error: NonEmptyStr

    @field_validator("failed_at")
    @classmethod
    def validate_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return _ensure_utc(value)


class TelegramOperationResponse(APIModel):
    ok: bool = True


class TelegramAttendanceAnswerRequest(APIModel):
    request_id: UUID
    event_id: UUID
    user_id: UUID
    telegram_user_id: int = Field(gt=0)
    answer: AttendanceAnswer
    answered_at: AwareDatetime

    @field_validator("answered_at")
    @classmethod
    def validate_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return _ensure_utc(value)


class TelegramLinkStartRequest(APIModel):
    telegram_user_id: int = Field(gt=0)
    chat_id: int = Field(gt=0)
    username: NonEmptyStr


class TelegramLinkStartResponse(APIModel):
    ok: bool = True
    linked: bool
    user_id: UUID | None = None
