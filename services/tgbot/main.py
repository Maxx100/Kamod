import asyncio
import contextlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx
import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.log_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class SendNotificationRequest(BaseModel):
    chat_id: int
    text: str = Field(min_length=1, max_length=4096)


class AttendanceNotificationRequest(BaseModel):
    chat_id: int
    event_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    question: str = "Планируешь прийти?"
    request_id: str | None = None


class DemoSendRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class DemoAttendanceRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    question: str = "Планируешь прийти?"
    request_id: str | None = None


class AttendanceContext(BaseModel):
    event_id: str
    user_id: str | None = None


class AttendanceAnswer(BaseModel):
    request_id: str
    event_id: str
    user_id: str
    telegram_user_id: int
    answer: str


class DueJob(BaseModel):
    job_id: str
    event_id: str
    user_id: str
    chat_id: int
    telegram_username: str | None = None
    kind: str
    scheduled_at: datetime
    title: str
    starts_at: datetime
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str


def _read_parse_mode(raw_mode: str) -> ParseMode:
    normalized = raw_mode.strip().upper()
    if normalized == "MARKDOWNV2":
        return ParseMode.MARKDOWN_V2
    if normalized == "MARKDOWN":
        return ParseMode.MARKDOWN
    return ParseMode.HTML


def _read_default_chat_id(raw_chat_id: str | None) -> int | None:
    if not raw_chat_id:
        return None
    try:
        return int(raw_chat_id)
    except ValueError:
        logger.warning("TG_DEFAULT_CHAT_ID is not a number: %s", raw_chat_id)
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc_iso(dt: datetime) -> str:
    utc_value = dt.astimezone(timezone.utc).replace(microsecond=0)
    return utc_value.isoformat().replace("+00:00", "Z")


BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TG_BOT_TOKEN is required")

BOT_PORT = int(os.getenv("TG_BOT_PORT", "8890"))
PARSE_MODE = _read_parse_mode(os.getenv("TG_BOT_PARSE_MODE", "HTML"))
DEFAULT_CHAT_ID = _read_default_chat_id(os.getenv("TG_DEFAULT_CHAT_ID"))
DEFAULT_USERNAME = os.getenv("TG_DEFAULT_USERNAME", "")

TG_DB_BASE_URL = os.getenv("TG_DB_BASE_URL", "").rstrip("/")
TG_DB_POLL_SECONDS = int(os.getenv("TG_DB_POLL_SECONDS", "3600"))
TG_DB_DUE_LIMIT = int(os.getenv("TG_DB_DUE_LIMIT", "500"))
TG_DB_TIMEOUT_SECONDS = float(os.getenv("TG_DB_TIMEOUT_SECONDS", "10"))
TG_WORKER_ID = os.getenv("TG_WORKER_ID", "tgbot-1")
TG_DB_API_KEY = os.getenv("TG_DB_API_KEY", "")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=PARSE_MODE))
dp = Dispatcher()
polling_task: asyncio.Task | None = None
db_polling_task: asyncio.Task | None = None
db_client: httpx.AsyncClient | None = None

attendance_answers: Dict[str, List[AttendanceAnswer]] = {}
attendance_requests: Dict[str, AttendanceContext] = {}


async def _db_link_start(telegram_user_id: int, chat_id: int, username: str) -> bool:
    if not TG_DB_BASE_URL or db_client is None:
        return False

    payload = {
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "username": username,
    }

    response = await db_client.post("/v1/tg/link-start", json=payload)
    if response.status_code >= 400:
        logger.warning("Failed to link telegram start: status=%s", response.status_code)
        return False

    data = response.json()
    return bool(data.get("linked"))


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    linked = False
    username = message.from_user.username if message.from_user else None
    if username:
        try:
            linked = await _db_link_start(
                telegram_user_id=message.from_user.id,
                chat_id=message.chat.id,
                username=username,
            )
        except Exception:
            logger.exception("Failed to process /start link flow")

    linked_status = "Профиль успешно привязан ✅" if linked else "Профиль не найден по нику, проверь Telegram в профиле на сайте"
    await message.answer(
        "Бот подключен.\n"
        f"Твой chat_id: <code>{message.chat.id}</code>\n"
        f"{linked_status}\n"
        "Теперь можно получать уведомления."
    )


async def _submit_attendance_answer(
    request_id: str,
    event_id: str,
    user_id: str | None,
    telegram_user_id: int,
    answer: str,
) -> None:
    if not TG_DB_BASE_URL or db_client is None or user_id is None:
        return

    payload = {
        "request_id": request_id,
        "event_id": event_id,
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "answer": answer,
        "answered_at": _as_utc_iso(_utcnow()),
    }

    response = await db_client.post("/v1/tg/attendance/answer", json=payload)
    response.raise_for_status()


@dp.callback_query(F.data.startswith("att:"))
async def attendance_callback(query: CallbackQuery) -> None:
    if query.data is None:
        return

    _, request_id, answer = query.data.split(":", maxsplit=2)
    context = attendance_requests.get(request_id, AttendanceContext(event_id="unknown"))

    attendance_answer = AttendanceAnswer(
        request_id=request_id,
        event_id=context.event_id,
        user_id=context.user_id or str(query.from_user.id),
        telegram_user_id=query.from_user.id,
        answer=answer,
    )
    attendance_answers.setdefault(request_id, []).append(attendance_answer)

    try:
        await _submit_attendance_answer(
            request_id=request_id,
            event_id=context.event_id,
            user_id=context.user_id,
            telegram_user_id=query.from_user.id,
            answer=answer,
        )
    except Exception:
        logger.exception(
            "Failed to submit attendance answer to DB: request_id=%s tg_user=%s",
            request_id,
            query.from_user.id,
        )

    answer_text = "Приду" if answer == "yes" else "Не приду"
    await query.answer(f"Ответ принят: {answer_text}")

    if query.message:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.reply(
            f"Спасибо! Зафиксировал твой ответ: <b>{answer_text}</b>"
        )

    logger.info(
        "Attendance answer: request_id=%s user_id=%s event_id=%s answer=%s",
        request_id,
        query.from_user.id,
        context.event_id,
        answer,
    )


async def _polling_worker() -> None:
    while True:
        try:
            logger.info("Telegram polling started")
            await dp.start_polling(bot)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Polling failed, retrying in 5 seconds")
            await asyncio.sleep(5)


async def _send_text(chat_id: int, text: str) -> int:
    message = await bot.send_message(chat_id=chat_id, text=text)
    return int(message.message_id)


def _normalize_telegram_username(username: str | None) -> str | None:
    if not username:
        return None
    value = username.strip()
    if not value:
        return None
    if not value.startswith("@"):
        value = f"@{value}"
    return value


async def _can_send_to_recipient(recipient: int | str) -> bool:
    try:
        await bot.get_chat(chat_id=recipient)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


async def _send_text_to_due_job_recipient(job: DueJob, text: str) -> int:
    recipients: list[int | str] = [job.chat_id]
    username = _normalize_telegram_username(job.telegram_username)
    if username:
        recipients.append(username)

    last_error: Exception | None = None
    for recipient in recipients:
        can_send = await _can_send_to_recipient(recipient)
        if not can_send:
            logger.warning(
                "Recipient is not reachable for due job: job_id=%s recipient=%s",
                job.job_id,
                recipient,
            )
            continue

        try:
            message = await bot.send_message(chat_id=recipient, text=text)
            logger.info(
                "Reminder sent: job_id=%s recipient=%s",
                job.job_id,
                recipient,
            )
            return int(message.message_id)
        except Exception as exc:
            last_error = exc
            logger.exception(
                "Failed to send reminder to recipient: job_id=%s recipient=%s",
                job.job_id,
                recipient,
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("No reachable Telegram recipient (chat_id/username)")


async def _send_attendance(
    chat_id: int,
    event_id: str,
    title: str,
    question: str,
    request_id: str | None,
    user_id: str | None = None,
) -> tuple[str, int]:
    rid = request_id or str(uuid.uuid4())
    attendance_requests[rid] = AttendanceContext(event_id=event_id, user_id=user_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Приду", callback_data=f"att:{rid}:yes"),
                InlineKeyboardButton(text="Не приду", callback_data=f"att:{rid}:no"),
            ]
        ]
    )

    text = (
        f"<b>{title}</b>\n"
        f"Событие ID: <code>{event_id}</code>\n\n"
        f"{question}"
    )

    message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    logger.info(
        "Attendance question sent: request_id=%s event_id=%s chat_id=%s",
        rid,
        event_id,
        chat_id,
    )

    return rid, int(message.message_id)


async def _db_claim_job(job_id: str) -> bool:
    if db_client is None:
        return False

    response = await db_client.post(f"/v1/tg/jobs/{job_id}/claim", json={"worker_id": TG_WORKER_ID})
    response.raise_for_status()
    data = response.json()
    return bool(data.get("claimed"))


async def _db_complete_job(job_id: str, telegram_message_id: int) -> None:
    if db_client is None:
        return

    payload = {
        "sent_at": _as_utc_iso(_utcnow()),
        "telegram_message_id": telegram_message_id,
    }
    response = await db_client.post(f"/v1/tg/jobs/{job_id}/complete", json=payload)
    response.raise_for_status()


async def _db_fail_job(job_id: str, error: str) -> None:
    if db_client is None:
        return

    payload = {
        "failed_at": _as_utc_iso(_utcnow()),
        "error": error[:500],
    }
    response = await db_client.post(f"/v1/tg/jobs/{job_id}/fail", json=payload)
    response.raise_for_status()


async def _db_fetch_due_jobs(from_dt: datetime, to_dt: datetime) -> list[DueJob]:
    if db_client is None:
        return []

    response = await db_client.get(
        "/v1/tg/jobs/due",
        params={
            "from": _as_utc_iso(from_dt),
            "to": _as_utc_iso(to_dt),
            "limit": TG_DB_DUE_LIMIT,
        },
    )
    response.raise_for_status()

    rows = response.json()
    jobs: list[DueJob] = []
    for row in rows:
        try:
            jobs.append(DueJob.model_validate(row))
        except Exception:
            logger.exception("Invalid due job payload: %s", row)
    return jobs


def _build_job_text(job: DueJob) -> str:
    starts_at = _as_utc_iso(job.starts_at)
    if job.kind == "reminder_24h":
        return f"Напоминание: до мероприятия «{job.title}» осталось 24 часа.\nСтарт: {starts_at}"
    if job.kind == "reminder_1h":
        return f"Напоминание: мероприятие «{job.title}» начнётся через час.\nСтарт: {starts_at}"
    return f"<b>{job.title}</b>\nСтарт: {starts_at}\n\nПланируешь прийти?"


async def _process_due_job(job: DueJob) -> None:
    claimed = await _db_claim_job(job.job_id)
    if not claimed:
        return

    try:
        if job.kind == "attendance_ask_24h":
            request_id, message_id = await _send_attendance(
                chat_id=job.chat_id,
                event_id=job.event_id,
                title=job.title,
                question="Планируешь прийти?",
                request_id=job.request_id,
                user_id=job.user_id,
            )
            if not job.request_id:
                logger.warning("attendance_ask_24h without request_id, generated=%s", request_id)
        else:
            message_id = await _send_text_to_due_job_recipient(job=job, text=_build_job_text(job))

        await _db_complete_job(job.job_id, telegram_message_id=message_id)
    except Exception as exc:
        logger.exception("Failed to process due job: job_id=%s", job.job_id)
        with contextlib.suppress(Exception):
            await _db_fail_job(job.job_id, error=str(exc))


async def _db_polling_worker() -> None:
    if not TG_DB_BASE_URL:
        logger.info("DB polling is disabled: TG_DB_BASE_URL is not set")
        return

    last_check_time = _utcnow() - timedelta(seconds=TG_DB_POLL_SECONDS)
    logger.info("DB polling started: every %s seconds", TG_DB_POLL_SECONDS)

    while True:
        now = _utcnow()
        try:
            due_jobs = await _db_fetch_due_jobs(from_dt=last_check_time, to_dt=now)
            logger.info(
                "DB due check: from=%s to=%s jobs=%s",
                _as_utc_iso(last_check_time),
                _as_utc_iso(now),
                len(due_jobs),
            )

            for job in due_jobs:
                await _process_due_job(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DB polling iteration failed")

        last_check_time = now
        await asyncio.sleep(TG_DB_POLL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global polling_task, db_polling_task, db_client

    headers = {}
    if TG_DB_API_KEY:
        headers["Authorization"] = f"Bearer {TG_DB_API_KEY}"

    if TG_DB_BASE_URL:
        db_client = httpx.AsyncClient(
            base_url=TG_DB_BASE_URL,
            timeout=TG_DB_TIMEOUT_SECONDS,
            headers=headers,
        )

    polling_task = asyncio.create_task(_polling_worker())
    db_polling_task = asyncio.create_task(_db_polling_worker())
    yield

    if polling_task:
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task

    if db_polling_task:
        db_polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await db_polling_task

    if db_client:
        await db_client.aclose()

    await bot.session.close()


app = FastAPI(title="tgbot-service", lifespan=lifespan)


def _require_default_chat_id() -> int:
    if DEFAULT_CHAT_ID is None:
        raise HTTPException(
            status_code=400,
            detail="TG_DEFAULT_CHAT_ID is not set. Configure it in services/tgbot/.env",
        )
    return DEFAULT_CHAT_ID


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/demo/profile")
async def demo_profile() -> dict:
    return {
        "default_chat_id": DEFAULT_CHAT_ID,
        "default_username": DEFAULT_USERNAME,
        "db_polling_enabled": bool(TG_DB_BASE_URL),
    }


@app.post("/notifications/send")
async def send_notification(payload: SendNotificationRequest) -> dict:
    await bot.send_message(chat_id=payload.chat_id, text=payload.text)
    logger.info("Notification sent: chat_id=%s", payload.chat_id)
    return {"ok": True}


@app.post("/notifications/attendance")
async def send_attendance_question(payload: AttendanceNotificationRequest) -> dict:
    request_id, _ = await _send_attendance(
        chat_id=payload.chat_id,
        event_id=payload.event_id,
        title=payload.title,
        question=payload.question,
        request_id=payload.request_id,
    )
    return {"ok": True, "request_id": request_id}


@app.post("/demo/send")
async def demo_send(payload: DemoSendRequest) -> dict:
    chat_id = _require_default_chat_id()
    await bot.send_message(chat_id=chat_id, text=payload.text)
    logger.info("Demo notification sent: chat_id=%s", chat_id)
    return {"ok": True, "chat_id": chat_id}


@app.post("/demo/attendance")
async def demo_attendance(payload: DemoAttendanceRequest) -> dict:
    chat_id = _require_default_chat_id()
    request_id, _ = await _send_attendance(
        chat_id=chat_id,
        event_id=payload.event_id,
        title=payload.title,
        question=payload.question,
        request_id=payload.request_id,
    )
    return {"ok": True, "request_id": request_id, "chat_id": chat_id}


@app.get("/attendance/{request_id}")
async def get_attendance(request_id: str) -> dict:
    if request_id not in attendance_requests:
        raise HTTPException(status_code=404, detail="request_id not found")

    answers = [answer.model_dump() for answer in attendance_answers.get(request_id, [])]
    return {"request_id": request_id, "answers": answers}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=BOT_PORT, reload=False)
