from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import OrganizerBalance, PaymentTransaction
from app.models.enums import PaymentStatus


class PaymentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, payment: PaymentTransaction) -> None:
        self.session.add(payment)

    def get_by_id(self, payment_id: UUID) -> PaymentTransaction | None:
        stmt = select(PaymentTransaction).where(PaymentTransaction.id == payment_id)
        return self.session.scalar(stmt)

    def get_by_id_for_update(self, payment_id: UUID) -> PaymentTransaction | None:
        stmt = select(PaymentTransaction).where(PaymentTransaction.id == payment_id).with_for_update()
        return self.session.scalar(stmt)

    def get_by_provider_payment_id(self, provider_payment_id: str) -> PaymentTransaction | None:
        stmt = select(PaymentTransaction).where(PaymentTransaction.provider_payment_id == provider_payment_id)
        return self.session.scalar(stmt)

    def get_latest_refundable_for_event_user_for_update(self, event_id: UUID, user_id: UUID) -> PaymentTransaction | None:
        stmt = (
            select(PaymentTransaction)
            .where(
                PaymentTransaction.event_id == event_id,
                PaymentTransaction.user_id == user_id,
                PaymentTransaction.status == PaymentStatus.SUCCEEDED,
                PaymentTransaction.registration_confirmed_at.is_not(None),
            )
            .order_by(PaymentTransaction.paid_at.desc().nullslast(), PaymentTransaction.created_at.desc())
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def list_due_for_settlement_for_update(self, now: datetime, limit: int = 200) -> list[PaymentTransaction]:
        stmt: Select[tuple[PaymentTransaction]] = (
            select(PaymentTransaction)
            .where(
                PaymentTransaction.status == PaymentStatus.SUCCEEDED,
                PaymentTransaction.settlement_due_at.is_not(None),
                PaymentTransaction.settled_at.is_(None),
                PaymentTransaction.settlement_due_at <= now,
            )
            .order_by(PaymentTransaction.settlement_due_at.asc(), PaymentTransaction.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(stmt).all())

    def get_balance(self, organizer_user_id: UUID) -> OrganizerBalance | None:
        stmt = select(OrganizerBalance).where(OrganizerBalance.organizer_user_id == organizer_user_id)
        return self.session.scalar(stmt)

    def get_balance_for_update(self, organizer_user_id: UUID) -> OrganizerBalance | None:
        stmt = (
            select(OrganizerBalance)
            .where(OrganizerBalance.organizer_user_id == organizer_user_id)
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def add_balance(self, balance: OrganizerBalance) -> None:
        self.session.add(balance)
