from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Event, EventRegistration, TelegramAttendanceAnswer, TelegramNotificationJob, UserTelegramSettings
from app.models.enums import EventStatus, RegistrationStatus, TelegramJobStatus
from app.schemas.tg import TelegramDueJobsQuery


class TelegramSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_user_id(self, user_id: UUID) -> UserTelegramSettings | None:
        stmt = select(UserTelegramSettings).where(UserTelegramSettings.user_id == user_id)
        return self.session.scalar(stmt)

    def get_by_user_ids(self, user_ids: list[UUID]) -> dict[UUID, UserTelegramSettings]:
        if not user_ids:
            return {}

        stmt = select(UserTelegramSettings).where(UserTelegramSettings.user_id.in_(user_ids))
        settings = self.session.scalars(stmt).all()
        return {item.user_id: item for item in settings}


class TelegramJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: TelegramNotificationJob) -> None:
        self.session.add(job)

    def list_due(self, params: TelegramDueJobsQuery) -> list[TelegramNotificationJob]:
        stmt = (
            select(TelegramNotificationJob)
            .join(Event, TelegramNotificationJob.event_id == Event.id)
            .join(
                EventRegistration,
                and_(
                    EventRegistration.event_id == TelegramNotificationJob.event_id,
                    EventRegistration.user_id == TelegramNotificationJob.user_id,
                ),
            )
            .where(
                TelegramNotificationJob.status == TelegramJobStatus.PENDING,
                TelegramNotificationJob.scheduled_at >= params.from_at,
                TelegramNotificationJob.scheduled_at <= params.to_at,
                Event.deleted_at.is_(None),
                Event.status == EventStatus.PUBLISHED,
                EventRegistration.status == RegistrationStatus.REGISTERED,
            )
            .options(selectinload(TelegramNotificationJob.event))
            .order_by(TelegramNotificationJob.scheduled_at.asc(), TelegramNotificationJob.id.asc())
            .limit(params.limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_by_id_for_update(self, job_id: UUID) -> TelegramNotificationJob | None:
        stmt = (
            select(TelegramNotificationJob)
            .where(TelegramNotificationJob.id == job_id)
            .options(selectinload(TelegramNotificationJob.event))
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def get_by_request_id_for_update(self, request_id: UUID) -> TelegramNotificationJob | None:
        stmt = (
            select(TelegramNotificationJob)
            .where(TelegramNotificationJob.request_id == request_id)
            .options(selectinload(TelegramNotificationJob.event))
            .with_for_update()
        )
        return self.session.scalar(stmt)

    def list_by_event(self, event_id: UUID) -> list[TelegramNotificationJob]:
        stmt = select(TelegramNotificationJob).where(TelegramNotificationJob.event_id == event_id)
        return list(self.session.scalars(stmt).all())

    def list_by_event_user(self, event_id: UUID, user_id: UUID) -> list[TelegramNotificationJob]:
        stmt = select(TelegramNotificationJob).where(
            TelegramNotificationJob.event_id == event_id,
            TelegramNotificationJob.user_id == user_id,
        )
        return list(self.session.scalars(stmt).all())


class TelegramAttendanceAnswerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, answer: TelegramAttendanceAnswer) -> None:
        self.session.add(answer)

    def get_for_update(self, request_id: UUID, telegram_user_id: int) -> TelegramAttendanceAnswer | None:
        stmt = (
            select(TelegramAttendanceAnswer)
            .where(
                TelegramAttendanceAnswer.request_id == request_id,
                TelegramAttendanceAnswer.telegram_user_id == telegram_user_id,
            )
            .with_for_update()
        )
        return self.session.scalar(stmt)
