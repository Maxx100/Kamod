from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import OrganizerBalance, PaymentTransaction
from app.models.enums import EventStatus, PaymentStatus
from app.repositories import EventRepository, PaymentRepository, UserRepository
from app.schemas.payment import (
    OrganizerBalanceResponse,
    PaymentCreateRequest,
    PaymentResponse,
    PaymentStatusUpdateRequest,
    SettlementRunResponse,
)


class PaymentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.events = EventRepository(session)
        self.payments = PaymentRepository(session)

    def create_payment(self, current_user_id: UUID, payload: PaymentCreateRequest) -> PaymentResponse:
        now = datetime.now(UTC)

        with self.session.begin():
            user = self.users.get_active_by_id(current_user_id)
            if user is None:
                raise NotFoundError("User not found")

            event = self.events.get_by_id(payload.event_id)
            if event is None or event.deleted_at is not None:
                raise NotFoundError("Event not found")

            if event.status != EventStatus.PUBLISHED:
                raise ConflictError("Event is not available for payment")
            if now < event.registration_start_at or now > event.registration_end_at:
                raise ConflictError("Registration window is closed")

            if payload.provider_payment_id:
                existing = self.payments.get_by_provider_payment_id(payload.provider_payment_id)
                if existing is not None and existing.user_id != current_user_id:
                    raise ConflictError("Payment already exists")

            payment = PaymentTransaction(
                event_id=payload.event_id,
                user_id=current_user_id,
                organizer_user_id=event.created_by_user_id,
                provider=payload.provider,
                provider_payment_id=payload.provider_payment_id,
                ticket_title=payload.ticket_title,
                description=payload.description,
                amount_minor=payload.amount_minor,
                currency=payload.currency,
                status=PaymentStatus.PENDING,
                expires_at=payload.expires_at,
                paid_at=None,
                cancelled_at=None,
                expired_at=None,
                registration_confirmed_at=None,
                settlement_due_at=None,
                settled_at=None,
            )
            self.payments.add(payment)
            self.session.flush()

        return self._to_payment_response(payment)

    def get_payment(self, payment_id: UUID, current_user_id: UUID) -> PaymentResponse:
        payment = self.payments.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError("Payment not found")
        if payment.user_id != current_user_id and payment.organizer_user_id != current_user_id:
            raise ForbiddenError("Access denied")
        return self._to_payment_response(payment)

    def update_payment_status(
        self,
        payment_id: UUID,
        payload: PaymentStatusUpdateRequest,
        current_user_id: UUID,
    ) -> PaymentResponse:
        now = datetime.now(UTC)

        with self.session.begin():
            payment = self.payments.get_by_id_for_update(payment_id)
            if payment is None:
                raise NotFoundError("Payment not found")
            if payment.user_id != current_user_id:
                raise ForbiddenError("Access denied")

            self._apply_status_transition(payment, payload.status, payload.paid_at or now, now)
            self.session.flush()

        return self._to_payment_response(payment)

    def confirm_registration(self, payment_id: UUID, current_user_id: UUID) -> PaymentResponse:
        now = datetime.now(UTC)

        with self.session.begin():
            payment = self.payments.get_by_id_for_update(payment_id)
            if payment is None:
                raise NotFoundError("Payment not found")
            if payment.user_id != current_user_id:
                raise ForbiddenError("Access denied")
            if payment.status != PaymentStatus.SUCCEEDED:
                raise ConflictError("Payment is not completed")

            if payment.registration_confirmed_at is None:
                payment.registration_confirmed_at = now

            self.session.flush()

        return self._to_payment_response(payment)

    def run_due_settlements(self, limit: int = 200) -> SettlementRunResponse:
        now = datetime.now(UTC)
        processed = 0

        with self.session.begin():
            due_payments = self.payments.list_due_for_settlement_for_update(now=now, limit=limit)
            for payment in due_payments:
                balance = self._get_or_create_balance_for_update(payment.organizer_user_id)
                amount = max(int(payment.amount_minor), 0)
                balance.pending_minor = max(int(balance.pending_minor) - amount, 0)
                balance.available_minor = int(balance.available_minor) + amount
                balance.settled_total_minor = int(balance.settled_total_minor) + amount
                payment.settled_at = now
                processed += 1

        return SettlementRunResponse(processed=processed)

    def get_organizer_balance(self, organizer_user_id: UUID) -> OrganizerBalanceResponse:
        with self.session.begin():
            balance = self._get_or_create_balance_for_update(organizer_user_id)
            self.session.flush()
        return self._to_balance_response(balance)

    def refund_for_cancelled_registration(self, event_id: UUID, user_id: UUID) -> None:
        payment = self.payments.get_latest_refundable_for_event_user_for_update(event_id=event_id, user_id=user_id)
        if payment is None:
            return

        amount = max(int(payment.amount_minor), 0)
        if amount <= 0:
            payment.status = PaymentStatus.CANCELLED
            payment.cancelled_at = datetime.now(UTC)
            return

        organizer_balance = self._get_or_create_balance_for_update(payment.organizer_user_id)
        user_balance = self._get_or_create_balance_for_update(payment.user_id)

        remaining = amount
        pending_part = min(int(organizer_balance.pending_minor), remaining)
        organizer_balance.pending_minor = int(organizer_balance.pending_minor) - pending_part
        remaining -= pending_part

        if remaining > 0:
            available_part = min(int(organizer_balance.available_minor), remaining)
            organizer_balance.available_minor = int(organizer_balance.available_minor) - available_part
            remaining -= available_part

        if remaining > 0:
            raise ConflictError("Organizer balance is insufficient for refund")

        user_balance.available_minor = int(user_balance.available_minor) + amount

        payment.status = PaymentStatus.CANCELLED
        payment.cancelled_at = datetime.now(UTC)

    def _get_or_create_balance_for_update(self, organizer_user_id: UUID) -> OrganizerBalance:
        balance = self.payments.get_balance_for_update(organizer_user_id)
        if balance is not None:
            return balance

        balance = OrganizerBalance(
            organizer_user_id=organizer_user_id,
            available_minor=0,
            pending_minor=0,
            settled_total_minor=0,
        )
        self.payments.add_balance(balance)
        self.session.flush()

        reloaded = self.payments.get_balance_for_update(organizer_user_id)
        if reloaded is None:
            raise ConflictError("Unable to initialize organizer balance")
        return reloaded

    def _apply_status_transition(
        self,
        payment: PaymentTransaction,
        next_status: PaymentStatus,
        paid_at: datetime,
        now: datetime,
    ) -> None:
        if payment.status == PaymentStatus.SUCCEEDED and next_status == PaymentStatus.SUCCEEDED:
            return
        if payment.status == PaymentStatus.CANCELLED:
            return
        if payment.status == PaymentStatus.EXPIRED:
            return

        if next_status == PaymentStatus.PENDING:
            if now >= payment.expires_at and payment.status == PaymentStatus.PENDING:
                payment.status = PaymentStatus.EXPIRED
                payment.expired_at = now
            return

        if next_status == PaymentStatus.CANCELLED and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CANCELLED
            payment.cancelled_at = now
            return

        if next_status == PaymentStatus.EXPIRED and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.EXPIRED
            payment.expired_at = now
            return

        if next_status == PaymentStatus.SUCCEEDED:
            if payment.status != PaymentStatus.PENDING:
                return
            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = paid_at
            payment.cancelled_at = None
            payment.expired_at = None

            event = self.events.get_by_id(payment.event_id)
            if event is None:
                raise NotFoundError("Event not found")

            payment.settlement_due_at = event.event_start_at + timedelta(hours=24)

            balance = self._get_or_create_balance_for_update(payment.organizer_user_id)
            balance.pending_minor = int(balance.pending_minor) + max(int(payment.amount_minor), 0)

    @staticmethod
    def _to_payment_response(payment: PaymentTransaction) -> PaymentResponse:
        return PaymentResponse.model_validate(payment)

    @staticmethod
    def _to_balance_response(balance: OrganizerBalance) -> OrganizerBalanceResponse:
        return OrganizerBalanceResponse.model_validate(balance)
