from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import PaymentStatus
from app.schemas.common import APIModel, NonEmptyStr, TimestampedResponse


class PaymentCreateRequest(APIModel):
    event_id: UUID
    amount_minor: int = Field(ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    provider: NonEmptyStr = "yookassa"
    provider_payment_id: NonEmptyStr | None = None
    ticket_title: NonEmptyStr | None = None
    description: NonEmptyStr | None = None
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_currency(self) -> "PaymentCreateRequest":
        self.currency = self.currency.upper()
        if self.currency != "RUB":
            raise ValueError("Only RUB currency is supported")
        return self


class PaymentStatusUpdateRequest(APIModel):
    status: PaymentStatus
    paid_at: AwareDatetime | None = None


class PaymentResponse(TimestampedResponse):
    id: UUID
    event_id: UUID
    user_id: UUID
    organizer_user_id: UUID
    amount_minor: int
    currency: str
    provider: str
    provider_payment_id: str | None = None
    ticket_title: str | None = None
    description: str | None = None
    status: PaymentStatus
    expires_at: AwareDatetime
    paid_at: AwareDatetime | None = None
    cancelled_at: AwareDatetime | None = None
    expired_at: AwareDatetime | None = None
    registration_confirmed_at: AwareDatetime | None = None
    settlement_due_at: AwareDatetime | None = None
    settled_at: AwareDatetime | None = None


class SettlementRunResponse(APIModel):
    processed: int = Field(ge=0)


class OrganizerBalanceResponse(TimestampedResponse):
    organizer_user_id: UUID
    available_minor: int = Field(ge=0)
    pending_minor: int = Field(ge=0)
    settled_total_minor: int = Field(ge=0)
