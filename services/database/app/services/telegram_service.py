from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import uuid
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.models import Event, EventRegistration, TelegramAttendanceAnswer, TelegramNotificationJob
from app.models.enums import EventStatus, RegistrationStatus, TelegramJobKind, TelegramJobStatus
from app.models.user_telegram_settings import UserTelegramSettings
from app.repositories import (
    EventRepository,
    RegistrationRepository,
    TelegramAttendanceAnswerRepository,
    TelegramJobRepository,
    TelegramSettingsRepository,
    UserRepository,
)
from app.schemas.tg import (
    TelegramAttendanceAnswerRequest,
    TelegramClaimJobRequest,
    TelegramClaimJobResponse,
    TelegramCompleteJobRequest,
    TelegramDueJobResponse,
    TelegramDueJobsQuery,
    TelegramFailJobRequest,
    TelegramLinkStartRequest,
    TelegramLinkStartResponse,
    TelegramOperationResponse,
)
from app.services.mappers import to_tg_due_job_response


class TelegramService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.registrations = RegistrationRepository(session)
        self.events = EventRepository(session)
        self.settings = TelegramSettingsRepository(session)
        self.jobs = TelegramJobRepository(session)
        self.answers = TelegramAttendanceAnswerRepository(session)
        self.users = UserRepository(session)

    def link_start(self, payload: TelegramLinkStartRequest) -> TelegramLinkStartResponse:
        normalized_username = payload.username.strip()
        if not normalized_username:
            return TelegramLinkStartResponse(linked=False)

        with self.session.begin():
            user = self.users.get_by_telegram_username(normalized_username)
            if user is None:
                return TelegramLinkStartResponse(linked=False)

            settings = self.settings.get_by_user_id(user.id)
            if settings is None:
                settings = UserTelegramSettings(
                    user_id=user.id,
                    telegram_user_id=payload.telegram_user_id,
                    telegram_chat_id=payload.chat_id,
                    reminder_24h_enabled=True,
                    reminder_1h_enabled=True,
                )
                self.session.add(settings)
            else:
                settings.telegram_user_id = payload.telegram_user_id
                settings.telegram_chat_id = payload.chat_id
                settings.reminder_24h_enabled = True
                settings.reminder_1h_enabled = True

            active_registrations = self.registrations.list_active_for_user(user.id)
            for registration in active_registrations:
                event = self.events.get_for_update(registration.event_id)
                if event is None:
                    continue
                self.sync_jobs_for_registration(event, registration)

        return TelegramLinkStartResponse(linked=True, user_id=user.id)

    def list_due_jobs(self, params: TelegramDueJobsQuery) -> list[TelegramDueJobResponse]:
        jobs = self.jobs.list_due(params)
        return [to_tg_due_job_response(job) for job in jobs]

    def claim_job(self, job_id: UUID, payload: TelegramClaimJobRequest) -> TelegramClaimJobResponse:
        with self.session.begin():
            job = self.jobs.get_by_id_for_update(job_id)
            if job is None:
                raise NotFoundError("Telegram job not found")

            if job.status != TelegramJobStatus.PENDING:
                return TelegramClaimJobResponse(claimed=False)

            job.status = TelegramJobStatus.CLAIMED
            job.claimed_by = payload.worker_id
            job.claimed_at = datetime.now(timezone.utc)

        return TelegramClaimJobResponse(claimed=True)

    def complete_job(self, job_id: UUID, payload: TelegramCompleteJobRequest) -> TelegramOperationResponse:
        with self.session.begin():
            job = self.jobs.get_by_id_for_update(job_id)
            if job is None:
                raise NotFoundError("Telegram job not found")

            if job.status in {TelegramJobStatus.SENT, TelegramJobStatus.CANCELLED}:
                return TelegramOperationResponse()

            job.status = TelegramJobStatus.SENT
            job.sent_at = payload.sent_at
            job.telegram_message_id = payload.telegram_message_id
            job.failed_at = None
            job.error = None
            job.cancelled_at = None

        return TelegramOperationResponse()

    def fail_job(self, job_id: UUID, payload: TelegramFailJobRequest) -> TelegramOperationResponse:
        with self.session.begin():
            job = self.jobs.get_by_id_for_update(job_id)
            if job is None:
                raise NotFoundError("Telegram job not found")

            if job.status in {TelegramJobStatus.SENT, TelegramJobStatus.CANCELLED, TelegramJobStatus.FAILED}:
                return TelegramOperationResponse()

            job.status = TelegramJobStatus.FAILED
            job.failed_at = payload.failed_at
            job.error = payload.error

        return TelegramOperationResponse()

    def save_attendance_answer(self, payload: TelegramAttendanceAnswerRequest) -> TelegramOperationResponse:
        with self.session.begin():
            job = self.jobs.get_by_request_id_for_update(payload.request_id)
            if job is None or job.kind != TelegramJobKind.ATTENDANCE_ASK_24H:
                raise NotFoundError("Attendance request not found")

            if job.event_id != payload.event_id or job.user_id != payload.user_id:
                raise ConflictError("Attendance answer does not match the original request")

            if job.telegram_user_id is not None and job.telegram_user_id != payload.telegram_user_id:
                raise ConflictError("Attendance answer does not match the original Telegram user")

            answer = self.answers.get_for_update(payload.request_id, payload.telegram_user_id)
            if answer is None:
                answer = TelegramAttendanceAnswer(
                    request_id=payload.request_id,
                    event_id=payload.event_id,
                    user_id=payload.user_id,
                    telegram_user_id=payload.telegram_user_id,
                    answer=payload.answer,
                    answered_at=payload.answered_at,
                )
                self.answers.add(answer)
            else:
                answer.event_id = payload.event_id
                answer.user_id = payload.user_id
                answer.answer = payload.answer
                answer.answered_at = payload.answered_at

        return TelegramOperationResponse()

    def sync_jobs_for_registration(self, event: Event, registration: EventRegistration) -> None:
        settings = self.settings.get_by_user_id(registration.user_id)
        existing_jobs = self.jobs.list_by_event_user(event.id, registration.user_id)
        desired_jobs = self._build_desired_jobs(event, registration, settings)
        self._apply_job_sync(existing_jobs, desired_jobs, event.id, registration.user_id)

    def sync_jobs_for_event(self, event: Event) -> None:
        registrations = self.registrations.list_active_for_event(event.id)
        settings_by_user = self.settings.get_by_user_ids([registration.user_id for registration in registrations])
        existing_jobs = self.jobs.list_by_event(event.id)
        jobs_by_user: dict[UUID, list[TelegramNotificationJob]] = defaultdict(list)
        for job in existing_jobs:
            jobs_by_user[job.user_id].append(job)

        active_user_ids = set()
        for registration in registrations:
            active_user_ids.add(registration.user_id)
            desired_jobs = self._build_desired_jobs(
                event,
                registration,
                settings_by_user.get(registration.user_id),
            )
            self._apply_job_sync(
                jobs_by_user.get(registration.user_id, []),
                desired_jobs,
                event.id,
                registration.user_id,
            )

        now = datetime.now(timezone.utc)
        for user_id, user_jobs in jobs_by_user.items():
            if user_id in active_user_ids:
                continue
            for job in user_jobs:
                self._cancel_job(job, now)

    def _build_desired_jobs(
        self,
        event: Event,
        registration: EventRegistration,
        settings: UserTelegramSettings | None,
    ) -> dict[TelegramJobKind, dict[str, object]]:
        now = datetime.now(timezone.utc)
        user = self.users.get_by_id(registration.user_id)
        telegram_username = (user.telegram or "").strip() if user is not None and user.telegram else ""
        has_username = bool(telegram_username)
        resolved_chat_id = (
            settings.telegram_chat_id
            if settings is not None and settings.telegram_chat_id is not None
            else (1 if has_username else None)
        )

        reminder_24h_enabled = True
        reminder_1h_enabled = True

        if (
            event.deleted_at is not None
            or event.status != EventStatus.PUBLISHED
            or registration.status != RegistrationStatus.REGISTERED
            or resolved_chat_id is None
        ):
            return {}

        desired_jobs: dict[TelegramJobKind, dict[str, object]] = {}
        if reminder_24h_enabled:
            scheduled_at = event.event_start_at - timedelta(hours=24)
            if scheduled_at > now:
                desired_jobs[TelegramJobKind.REMINDER_24H] = {
                    "scheduled_at": scheduled_at,
                    "telegram_chat_id": resolved_chat_id,
                    "telegram_user_id": settings.telegram_user_id if settings is not None else None,
                    "request_id": None,
                }

        if reminder_1h_enabled:
            scheduled_at = event.event_start_at - timedelta(hours=1)
            if scheduled_at > now:
                desired_jobs[TelegramJobKind.REMINDER_1H] = {
                    "scheduled_at": scheduled_at,
                    "telegram_chat_id": resolved_chat_id,
                    "telegram_user_id": settings.telegram_user_id if settings is not None else None,
                    "request_id": None,
                }

        if (
            event.attendance_ask_enabled
            and settings is not None
            and settings.telegram_user_id is not None
            and settings.telegram_chat_id is not None
        ):
            scheduled_at = event.event_start_at - timedelta(hours=24)
            if scheduled_at > now:
                desired_jobs[TelegramJobKind.ATTENDANCE_ASK_24H] = {
                    "scheduled_at": scheduled_at,
                    "telegram_chat_id": settings.telegram_chat_id,
                    "telegram_user_id": settings.telegram_user_id,
                    "request_id": uuid.uuid4(),
                }

        return desired_jobs

    def _apply_job_sync(
        self,
        existing_jobs: list[TelegramNotificationJob],
        desired_jobs: dict[TelegramJobKind, dict[str, object]],
        event_id: UUID,
        user_id: UUID,
    ) -> None:
        existing_by_kind = {job.kind: job for job in existing_jobs}
        now = datetime.now(timezone.utc)

        for kind, spec in desired_jobs.items():
            job = existing_by_kind.get(kind)
            if job is None:
                job = TelegramNotificationJob(
                    event_id=event_id,
                    user_id=user_id,
                    kind=kind,
                    status=TelegramJobStatus.PENDING,
                    scheduled_at=spec["scheduled_at"],
                    telegram_chat_id=spec["telegram_chat_id"],
                    telegram_user_id=spec["telegram_user_id"],
                    request_id=spec["request_id"],
                )
                self.jobs.add(job)
                continue

            if job.status == TelegramJobStatus.SENT:
                continue

            job.scheduled_at = spec["scheduled_at"]
            job.telegram_chat_id = spec["telegram_chat_id"]
            job.telegram_user_id = spec["telegram_user_id"]
            job.status = TelegramJobStatus.PENDING
            job.claimed_by = None
            job.claimed_at = None
            job.sent_at = None
            job.telegram_message_id = None
            job.failed_at = None
            job.error = None
            job.cancelled_at = None
            if kind == TelegramJobKind.ATTENDANCE_ASK_24H and job.request_id is None:
                job.request_id = spec["request_id"]
            if kind != TelegramJobKind.ATTENDANCE_ASK_24H:
                job.request_id = None

        for kind, job in existing_by_kind.items():
            if kind not in desired_jobs:
                self._cancel_job(job, now)

    @staticmethod
    def _cancel_job(job: TelegramNotificationJob, cancelled_at: datetime) -> None:
        if job.status in {TelegramJobStatus.SENT, TelegramJobStatus.CANCELLED}:
            return

        job.status = TelegramJobStatus.CANCELLED
        job.cancelled_at = cancelled_at
        job.claimed_by = None
        job.claimed_at = None
        job.failed_at = None
        job.error = None
