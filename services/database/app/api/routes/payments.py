from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import CurrentUserId, PaymentServiceDep
from app.schemas.payment import (
    OrganizerBalanceResponse,
    PaymentCreateRequest,
    PaymentResponse,
    PaymentStatusUpdateRequest,
    SettlementRunResponse,
)


router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse)
def create_payment(
    payload: PaymentCreateRequest,
    current_user_id: CurrentUserId,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return service.create_payment(current_user_id, payload)


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: UUID,
    current_user_id: CurrentUserId,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return service.get_payment(payment_id, current_user_id)


@router.post("/{payment_id}/status", response_model=PaymentResponse)
def update_payment_status(
    payment_id: UUID,
    payload: PaymentStatusUpdateRequest,
    current_user_id: CurrentUserId,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return service.update_payment_status(payment_id, payload, current_user_id)


@router.post("/{payment_id}/confirm-registration", response_model=PaymentResponse)
def confirm_payment_registration(
    payment_id: UUID,
    current_user_id: CurrentUserId,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return service.confirm_registration(payment_id, current_user_id)


@router.post("/settlements/run", response_model=SettlementRunResponse)
def run_due_settlements(
    service: PaymentServiceDep,
) -> SettlementRunResponse:
    return service.run_due_settlements()


@router.get("/organizers/me/balance", response_model=OrganizerBalanceResponse)
def get_my_organizer_balance(
    current_user_id: CurrentUserId,
    service: PaymentServiceDep,
) -> OrganizerBalanceResponse:
    service.run_due_settlements()
    return service.get_organizer_balance(current_user_id)
