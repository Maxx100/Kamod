from uuid import UUID

from pydantic import AwareDatetime, EmailStr, Field, field_validator, model_validator

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


class UserLoginRequest(APIModel):
    login: NonEmptyStr
    password: str

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
    has_photo: bool = False


class UserUpdateRequest(APIModel):
    full_name: NonEmptyStr | None = None
    university: NonEmptyStr | None = None
    faculty: NonEmptyStr | None = None
    telegram: TelegramStr | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "UserUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class UserResponse(TimestampedResponse):
    id: UUID
    email: EmailStr
    full_name: str
    university: str | None = None
    faculty: str | None = None
    telegram: str | None = None
    has_photo: bool = False
    is_active: bool
    deleted_at: AwareDatetime | None = None


class UserPhotoMetaResponse(APIModel):
    has_photo: bool
    content_type: str | None = None
    size_bytes: int = Field(ge=0)
