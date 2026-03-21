from uuid import UUID

from pydantic import AwareDatetime, EmailStr, field_validator

from app.schemas.common import APIModel, NonEmptyStr, TelegramStr, TimestampedResponse


class UserRegisterRequest(APIModel):
    email: EmailStr
    password: str
    full_name: NonEmptyStr
    university: NonEmptyStr | None = None
    faculty: NonEmptyStr | None = None
    telegram: TelegramStr | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must contain at least 8 characters")
        if value.isspace():
            raise ValueError("Password cannot contain only whitespace")
        return value


class UserSummary(APIModel):
    id: UUID
    full_name: str
    university: str | None = None
    faculty: str | None = None
    telegram: str | None = None


class UserResponse(TimestampedResponse):
    id: UUID
    email: EmailStr
    full_name: str
    university: str | None = None
    faculty: str | None = None
    telegram: str | None = None
    is_active: bool
    deleted_at: AwareDatetime | None = None
