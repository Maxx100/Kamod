from __future__ import annotations

import os
import mimetypes
import json
import logging
from hashlib import sha256
from pathlib import Path
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import jwt
import uvicorn
from flask import Flask, redirect, render_template
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from starlette.middleware.wsgi import WSGIMiddleware


DATABASE_API_URL = os.getenv("DATABASE_API_URL", "http://database:5000").rstrip("/")
TGBOT_API_URL = os.getenv("TGBOT_API_URL", "http://tgbot:8890").rstrip("/")
WEBSITE_PORT = int(os.getenv("WEBSITE_PORT", "80"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_COVERS_DIR = STATIC_DIR / "img"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

JWT_SECRET = os.getenv("WEBSITE_JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("WEBSITE_JWT_ALGORITHM", "HS256")
JWT_EXPIRE_SECONDS = int(os.getenv("WEBSITE_JWT_EXPIRE_SECONDS", str(30 * 24 * 3600)))
MAX_EVENT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
YANDEX_MAPS_API_KEY = os.getenv("YANDEX_MAPS_API_KEY", "").strip()
EVENT_META_PREFIX = "KAMOD_META_V1:"

CATEGORY_TO_TAG = {
    "hackathon": "hackathon",
    "conference": "conference",
    "workshop": "workshop",
    "meetup": "meetup",
    "competition": "competition",
    "other": "other",
    "online": "online",
}

ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    middleName: str | None = None
    fullName: str | None = None
    email: EmailStr
    password: str = Field(min_length=8)
    workPlace: str | None = None
    university: str | None = None
    faculty: str | None = None
    course: str | None = None
    telegram: str | None = None

    @field_validator("middleName", "workPlace", "university", "faculty", "course", "telegram", mode="before")
    @classmethod
    def blank_optional_fields_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_name_fields(self) -> "RegisterRequest":
        if self.fullName:
            return self
        if self.firstName and self.lastName:
            return self
        raise ValueError("Provide fullName or both firstName and lastName")


class LoginRequest(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=8)


class UpdateProfileRequest(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    middleName: str | None = None
    fullName: str | None = None
    workPlace: str | None = None
    university: str | None = None
    faculty: str | None = None
    telegram: str | None = None

    @field_validator("firstName", "lastName", "middleName", "fullName", "workPlace", "university", "faculty", "telegram", mode="before")
    @classmethod
    def blank_profile_fields_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class TicketScanRequest(BaseModel):
    scanUrl: str = Field(min_length=1)


class EventRegisterRequest(BaseModel):
    ticketTitle: str | None = None


app = FastAPI(title="website-service", version="0.1.0")


frontend_app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=None)


@frontend_app.route("/")
def frontend_root():
    return redirect("/main")


@frontend_app.route("/main")
def frontend_main():
    return render_template("main.html", active_page="events", page_title="СТУДEVENTS — Мероприятия")


@frontend_app.route("/event")
def frontend_event():
    return render_template("event.html", active_page="events", page_title="СТУДEVENTS — Мероприятие")


@frontend_app.route("/create-event")
def frontend_create_event():
    return render_template("create_event.html", active_page="create", page_title="СТУДEVENTS — Создать мероприятие")


@frontend_app.route("/tickets")
def frontend_tickets():
    return render_template("tickets.html", active_page="tickets", page_title="СТУДEVENTS — Билеты")


@frontend_app.route("/profile")
def frontend_profile():
    return render_template("profile.html", active_page="profile", page_title="СТУДEVENTS — Профиль")


@frontend_app.route("/my-events")
def frontend_my_events():
    return render_template("my_events.html", active_page="my-events", page_title="СТУДEVENTS — Мои мероприятия")


@frontend_app.route("/ticket-scan")
def frontend_ticket_scan():
    return render_template("ticket_scan.html", active_page="", page_title="СТУДEVENTS — Проверка билета")


@frontend_app.route("/login")
def frontend_login():
    return render_template("login.html", active_page="", page_title="СТУДEVENTS — Вход")


@frontend_app.route("/register")
def frontend_register():
    return render_template("register.html", active_page="", page_title="СТУДEVENTS — Регистрация")


@frontend_app.route("/edit-event")
def frontend_edit_event():
    return render_template("edit_event.html", active_page="my-events", page_title="СТУДEVENTS — Редактирование")


@frontend_app.route("/index.html")
def frontend_index_html_redirect():
    return redirect("/main", code=307)


@frontend_app.route("/event.html")
def frontend_event_html_redirect():
    return redirect("/event", code=307)


@frontend_app.route("/create-event.html")
def frontend_create_event_html_redirect():
    return redirect("/create-event", code=307)


@frontend_app.route("/my-tickets.html")
def frontend_tickets_html_redirect():
    return redirect("/tickets", code=307)


@frontend_app.route("/profile.html")
def frontend_profile_html_redirect():
    return redirect("/profile", code=307)


@frontend_app.route("/my-events.html")
def frontend_my_events_html_redirect():
    return redirect("/my-events", code=307)


@frontend_app.route("/login.html")
def frontend_login_html_redirect():
    return redirect("/login", code=307)


@frontend_app.route("/register.html")
def frontend_register_html_redirect():
    return redirect("/register", code=307)


def _to_front_user(user: dict[str, Any]) -> dict[str, Any]:
    has_photo = bool(user.get("has_photo"))
    first_name, last_name, middle_name = _split_full_name(user.get("full_name"))
    return {
        "id": user["id"],
        "email": user["email"],
        "fullName": user["full_name"],
        "firstName": first_name,
        "lastName": last_name,
        "middleName": middle_name,
        "workPlace": user.get("work_place"),
        "university": user.get("university"),
        "faculty": user.get("faculty"),
        "telegram": user.get("telegram"),
        "hasPhoto": has_photo,
        "photoUrl": "/api/users/me/photo" if has_photo else None,
    }


def _normalize_error(payload: Any, fallback: str) -> dict[str, str]:
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or fallback
        return {"message": str(detail)}
    return {"message": fallback}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def _normalize_error_from_response(response: httpx.Response, fallback: str) -> dict[str, str]:
    payload = _safe_json(response)
    if payload is not None:
        return _normalize_error(payload, fallback)

    text_payload = response.text.strip()
    if text_payload:
        return {"message": text_payload}
    return {"message": fallback}


def _extract_scan_ids(scan_url: str) -> tuple[str, str]:
    parsed = urlparse(scan_url)
    query = parse_qs(parsed.query or "")

    event_id = (query.get("eventId") or query.get("event_id") or [""])[0]
    participant_user_id = (query.get("userId") or query.get("user_id") or [""])[0]

    if not event_id or not participant_user_id:
        raise ValueError("Некорректный билет: отсутствует eventId или userId")

    try:
        UUID(event_id)
        UUID(participant_user_id)
    except ValueError as exc:
        raise ValueError("Некорректный билет: неверный формат идентификаторов") from exc

    return event_id, participant_user_id


async def _find_event_participant(event_id: str, participant_user_id: str, user_id: str) -> dict[str, Any] | None:
    participants_response = await _database_request(
        "GET",
        f"/v1/events/{event_id}/participants",
        params={"limit": 100, "offset": 0, "status": "registered"},
        user_id=user_id,
    )
    if participants_response.status_code >= 400:
        return None

    items = (_safe_json(participants_response) or {}).get("items", [])
    for item in items:
        if str(item.get("user_id")) == str(participant_user_id):
            return item
    return None


def _issue_token(user_id: str) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=JWT_EXPIRE_SECONDS)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    return token


def _decode_user_id_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        UUID(sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc
    return sub


def _require_user_id(authorization: str | None = Header(default=None)) -> str:
    token = _parse_bearer_token(authorization)
    return _decode_user_id_from_token(token)


def _parse_event_datetime(raw_value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid eventDate") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    else:
        parsed = parsed.astimezone(MOSCOW_TZ)
    return parsed.astimezone(UTC)


def _split_full_name(full_name: str | None) -> tuple[str, str, str | None]:
    normalized = (full_name or "").strip()
    if not normalized:
        return "", "", None

    parts = [part for part in normalized.split() if part]
    if not parts:
        return "", "", None
    if len(parts) == 1:
        return parts[0], "", None
    if len(parts) == 2:
        return parts[1], parts[0], None

    first_name = parts[1]
    last_name = parts[0]
    middle_name = " ".join(parts[2:])
    return first_name, last_name, middle_name


def _compose_full_name(first_name: str | None, last_name: str | None, middle_name: str | None) -> str:
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    middle = (middle_name or "").strip()
    if not first or not last:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="firstName and lastName are required")
    return " ".join(part for part in [last, first, middle] if part)


def _normalize_event_format(raw_value: str) -> str:
    normalized = (raw_value or "").strip().lower()
    if normalized not in {"offline", "online"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid eventFormat")
    return normalized


def _parse_api_datetime(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _resolve_registration_window(
    event_start_at: datetime,
    current_registration_start_at: datetime | None = None,
    current_registration_end_at: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if (
        current_registration_start_at is not None
        and current_registration_end_at is not None
        and current_registration_start_at <= current_registration_end_at <= event_start_at
        and current_registration_end_at >= now
    ):
        return current_registration_start_at, current_registration_end_at

    registration_end_at = event_start_at - timedelta(minutes=1)
    registration_start_at = now

    if registration_end_at <= registration_start_at:
        registration_start_at = event_start_at - timedelta(days=7)
        if registration_start_at > registration_end_at:
            registration_start_at = registration_end_at

    return registration_start_at, registration_end_at


def _parse_price_minor(is_paid: bool, price: str | None) -> int:
    if not is_paid:
        return 0
    if price is None:
        return 0
    try:
        return max(int(price), 0) * 100
    except (TypeError, ValueError):
        return 0


def _normalize_address_value(value: str) -> str:
    return " ".join(value.strip().lower().split())


async def _fetch_yandex_address_suggestions(query: str, limit: int = 7) -> list[str]:
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        return []

    suggestions: list[str] = []

    suggest_params = {
        "text": normalized_query,
        "lang": "ru_RU",
        "types": "geo",
        "results": min(max(limit, 1), 10),
    }
    if YANDEX_MAPS_API_KEY:
        suggest_params["apikey"] = YANDEX_MAPS_API_KEY

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            suggest_response = await client.get(
                "https://suggest-maps.yandex.ru/v1/suggest",
                params=suggest_params,
            )

        if suggest_response.status_code < 400:
            payload = _safe_json(suggest_response) or {}
            rows = payload.get("results", [])
            for row in rows:
                title = str((row.get("title") or {}).get("text") or "").strip()
                subtitle = str((row.get("subtitle") or {}).get("text") or "").strip()
                value = ", ".join(part for part in [title, subtitle] if part)
                if value and value not in suggestions:
                    suggestions.append(value)
    except Exception:
        logger.exception("Yandex suggest request failed")

    if suggestions:
        return suggestions[:limit]

    if not YANDEX_MAPS_API_KEY:
        return await _fetch_fallback_address_suggestions(normalized_query, limit)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            geocode_response = await client.get(
                "https://geocode-maps.yandex.ru/1.x/",
                params={
                    "apikey": YANDEX_MAPS_API_KEY,
                    "format": "json",
                    "geocode": normalized_query,
                    "results": min(max(limit, 1), 10),
                    "lang": "ru_RU",
                },
            )
    except Exception:
        logger.exception("Yandex geocode request failed")
        return []

    if geocode_response.status_code >= 400:
        return await _fetch_fallback_address_suggestions(normalized_query, limit)

    payload = _safe_json(geocode_response) or {}
    members = (
        payload.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    for member in members:
        geo_object = member.get("GeoObject", {})
        text_value = (
            geo_object.get("metaDataProperty", {})
            .get("GeocoderMetaData", {})
            .get("text")
            or geo_object.get("name")
            or ""
        )
        text_value = str(text_value).strip()
        if text_value and text_value not in suggestions:
            suggestions.append(text_value)

    if suggestions:
        return suggestions[:limit]

    return await _fetch_fallback_address_suggestions(normalized_query, limit)


async def _fetch_fallback_address_suggestions(query: str, limit: int = 7) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": min(max(limit, 1), 10),
                    "addressdetails": 0,
                },
                headers={"User-Agent": "kamod-address-suggest/1.0"},
            )
    except Exception:
        logger.exception("Fallback address suggest request failed")
        return []

    if response.status_code >= 400:
        return []

    payload = _safe_json(response)
    if not isinstance(payload, list):
        return []

    items: list[str] = []
    for row in payload:
        value = str(row.get("display_name") or "").strip()
        if value and value not in items:
            items.append(value)
    return items[:limit]


async def _is_address_selected_and_valid(address: str) -> bool:
    suggestions = await _fetch_yandex_address_suggestions(address, limit=10)
    normalized_address = _normalize_address_value(address)
    return any(_normalize_address_value(item) == normalized_address for item in suggestions)


def _parse_ticket_items(raw_ticket_items: str | None) -> list[dict[str, Any]]:
    if raw_ticket_items is None:
        return []

    raw = raw_ticket_items.strip()
    if not raw:
        return []

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid ticketItems JSON") from exc

    if not isinstance(decoded, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ticketItems must be an array")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(decoded, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ticketItems[{index}] must be an object")

        title = str(item.get("title") or item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        raw_price = item.get("price", 0)
        try:
            price = int(raw_price)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ticketItems[{index}].price must be an integer") from exc

        if not title:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ticketItems[{index}].title is required")
        if price < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ticketItems[{index}].price must be >= 0")

        normalized.append(
            {
                "title": title,
                "description": description,
                "price": price,
            }
        )

    return normalized


def _extract_event_meta(raw_recurrence_rule: Any) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(raw_recurrence_rule, str) or not raw_recurrence_rule:
        return [], None

    if not raw_recurrence_rule.startswith(EVENT_META_PREFIX):
        return [], raw_recurrence_rule

    raw_payload = raw_recurrence_rule[len(EVENT_META_PREFIX):]
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Failed to parse event metadata recurrence_rule")
        return [], None

    if not isinstance(payload, dict):
        return [], None

    recurrence_rule = payload.get("recurrence_rule")
    recurrence_value = str(recurrence_rule).strip() if isinstance(recurrence_rule, str) else None
    tickets = payload.get("tickets")
    normalized_tickets = _parse_ticket_items(json.dumps(tickets)) if isinstance(tickets, list) else []
    return normalized_tickets, recurrence_value


def _encode_event_meta(
    *,
    tickets: list[dict[str, Any]],
    recurrence_rule: str | None,
) -> str | None:
    recurrence_value = recurrence_rule.strip() if isinstance(recurrence_rule, str) else None
    if not tickets:
        return recurrence_value or None

    payload = {
        "tickets": tickets,
        "recurrence_rule": recurrence_value,
    }
    return f"{EVENT_META_PREFIX}{json.dumps(payload, ensure_ascii=False)}"


def _ticket_price_minor(ticket_items: list[dict[str, Any]]) -> int:
    if not ticket_items:
        return 0
    min_price = min(max(int(item.get("price", 0)), 0) for item in ticket_items)
    return min_price * 100


def _build_front_event_payload(
    *,
    title: str,
    category: str,
    event_format: str,
    event_start_at: datetime,
    address: str,
    description: str,
    is_paid: bool,
    price: str | None,
    ticket_items_raw: str | None = None,
    existing_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_registration_start_at = _parse_api_datetime((existing_event or {}).get("registration_start_at"))
    current_registration_end_at = _parse_api_datetime((existing_event or {}).get("registration_end_at"))
    registration_start_at, registration_end_at = _resolve_registration_window(
        event_start_at,
        current_registration_start_at,
        current_registration_end_at,
    )

    resolved_tag = CATEGORY_TO_TAG.get(category, category or "other")
    tag_slugs: list[str] = []
    if resolved_tag:
        tag_slugs.append(resolved_tag)
    if event_format == "online":
        tag_slugs.append("online")
    tag_slugs = list(dict.fromkeys(tag_slugs))

    contacts = address.strip()
    if event_format == "online":
        contacts = contacts or "Онлайн"
    elif not contacts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Address is required for offline event")

    existing_tickets, existing_recurrence_rule = _extract_event_meta((existing_event or {}).get("recurrence_rule"))
    ticket_items = _parse_ticket_items(ticket_items_raw) if ticket_items_raw is not None else existing_tickets
    encoded_recurrence_rule = _encode_event_meta(
        tickets=ticket_items,
        recurrence_rule=existing_recurrence_rule,
    )

    return {
        "title": title,
        "description": description,
        "photo_url": (existing_event or {}).get("photo_url"),
        "tag_slugs": tag_slugs,
        "event_start_at": _to_utc_iso(event_start_at),
        "registration_start_at": _to_utc_iso(registration_start_at),
        "registration_end_at": _to_utc_iso(registration_end_at),
        "format": event_format,
        "price_minor": _ticket_price_minor(ticket_items) if ticket_items else _parse_price_minor(is_paid, price),
        "contacts": contacts,
        "recurrence_rule": encoded_recurrence_rule,
        "attendance_ask_enabled": (existing_event or {}).get("attendance_ask_enabled", True),
        "max_participants": (existing_event or {}).get("max_participants"),
        "duration_minutes": (existing_event or {}).get("duration_minutes", 120),
    }


def _map_event_from_db(event: dict[str, Any]) -> dict[str, Any]:
    ticket_items, _ = _extract_event_meta(event.get("recurrence_rule"))
    price_minor = int(event.get("price_minor") or 0)
    ticket_price_floor = min((int(item.get("price", 0)) for item in ticket_items), default=0)
    is_paid = any(int(item.get("price", 0)) > 0 for item in ticket_items) if ticket_items else price_minor > 0
    price = ticket_price_floor if ticket_items else price_minor // 100

    tag_slugs = event.get("tag_slugs") or []
    category = next((slug for slug in tag_slugs if slug != "online"), "other")
    if category not in CATEGORY_TO_TAG:
        category = "other"
    event_format = event.get("format") or ("online" if "online" in tag_slugs else "offline")

    creator = event.get("creator") or {}
    has_photo = bool(event.get("has_photo"))
    cover_url = f"/api/events/{event['id']}/image" if has_photo else (event.get("photo_url") or _pick_default_cover_url(str(event.get("id"))))
    address = event.get("contacts") or ("Онлайн" if event_format == "online" else "Адрес уточняется")
    return {
        "id": event["id"],
        "title": event["title"],
        "category": category,
        "status": event.get("status"),
        "registeredCount": int(event.get("registered_count") or 0),
        "format": event_format,
        "tags": [category, "online"] if event_format == "online" else [category],
        "eventDate": event["event_start_at"],
        "address": address,
        "description": event.get("description") or "",
        "coverUrl": cover_url,
        "isPaid": is_paid,
        "price": price,
        "tickets": ticket_items,
        "organizerId": event.get("created_by_user_id"),
        "organizer": {
            "id": creator.get("id"),
            "fullName": creator.get("full_name") or "Организатор",
            "workPlace": creator.get("work_place"),
            "university": creator.get("university"),
            "displayPlace": creator.get("work_place") or creator.get("university"),
            "telegram": creator.get("telegram"),
            "hasPhoto": bool(creator.get("has_photo")),
        },
    }


def _list_default_covers() -> list[str]:
    if not DEFAULT_COVERS_DIR.exists() or not DEFAULT_COVERS_DIR.is_dir():
        return []

    covers: list[str] = []
    for item in sorted(DEFAULT_COVERS_DIR.iterdir(), key=lambda path: path.name.lower()):
        if item.is_file() and item.suffix.lower() in ALLOWED_COVER_EXTENSIONS:
            covers.append(f"/img/{item.name}")
    return covers


def _pick_default_cover_url(seed: str | None) -> str | None:
    covers = _list_default_covers()
    if not covers:
        return None

    stable_seed = seed or "default"
    digest = sha256(stable_seed.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], byteorder="big") % len(covers)
    return covers[index]


def _pick_default_cover_file(seed: str | None) -> Path | None:
    cover_url = _pick_default_cover_url(seed)
    if not cover_url:
        return None

    filename = cover_url.rsplit("/", 1)[-1]
    cover_path = DEFAULT_COVERS_DIR / filename
    if not cover_path.exists() or not cover_path.is_file():
        return None
    return cover_path


async def _database_request(
    method: str,
    path: str,
    *,
    json_data: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> httpx.Response:
    headers: dict[str, str] = {}
    if user_id:
        headers["X-User-Id"] = user_id

    async with httpx.AsyncClient(base_url=DATABASE_API_URL, timeout=20.0) as client:
        response = await client.request(
            method,
            path,
            json=json_data,
            data=data,
            files=files,
            params=params,
            headers=headers,
        )
    return response


def _is_unknown_tags_error(response: httpx.Response) -> bool:
    if response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY:
        return False

    payload = _safe_json(response)
    if not isinstance(payload, dict):
        return False

    code = payload.get("code")
    detail = str(payload.get("detail") or "")
    return code == "unknown_tags" or "unknown" in detail.lower() and "tag" in detail.lower()


async def _database_event_write_with_tag_fallback(
    method: str,
    path: str,
    *,
    payload: dict[str, Any],
    user_id: str,
) -> httpx.Response:
    response = await _database_request(method, path, json_data=payload, user_id=user_id)
    if not _is_unknown_tags_error(response):
        return response

    fallback_payload = dict(payload)
    fallback_payload["tag_slugs"] = []
    return await _database_request(method, path, json_data=fallback_payload, user_id=user_id)


@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    db_ok = False
    tg_ok = False

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            db_response = await client.get(f"{DATABASE_API_URL}/health")
            db_ok = db_response.status_code == 200
        except Exception:
            db_ok = False

        try:
            tg_response = await client.get(f"{TGBOT_API_URL}/health")
            tg_ok = tg_response.status_code == 200
        except Exception:
            tg_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "tgbot": "ok" if tg_ok else "unavailable",
    }


@app.get("/api/default-covers")
async def default_covers() -> dict[str, list[str]]:
    return {"items": _list_default_covers()}


@app.get("/api/maps/address-suggest")
async def suggest_addresses(q: str = Query(default="", min_length=0, max_length=200)) -> dict[str, list[str]]:
    return {"items": await _fetch_yandex_address_suggestions(q, limit=7)}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> JSONResponse:
    full_name = payload.fullName or _compose_full_name(payload.firstName, payload.lastName, payload.middleName)
    db_payload = {
        "email": payload.email,
        "password": payload.password,
        "full_name": full_name,
        "work_place": payload.workPlace,
        "university": payload.university,
        "faculty": payload.faculty,
        "telegram": payload.telegram,
    }
    response = await _database_request("POST", "/v1/auth/register", json_data=db_payload)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Registration failed"))

    user = _to_front_user(_safe_json(response) or {})
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"user": user})


@app.post("/api/auth/login")
async def login(payload: LoginRequest) -> JSONResponse:
    response = await _database_request(
        "POST",
        "/v1/auth/login",
        json_data={"login": payload.login, "password": payload.password},
    )
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Login failed"))

    user = _to_front_user(_safe_json(response) or {})
    token = _issue_token(user["id"])
    return JSONResponse(status_code=200, content={"token": token, "user": user})


@app.get("/api/auth/me")
async def auth_me(user_id: str = Depends(_require_user_id)) -> JSONResponse:
    response = await _database_request("GET", f"/v1/users/{user_id}", user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to get user profile"))

    user = _to_front_user(_safe_json(response) or {})
    return JSONResponse(status_code=200, content=user)


@app.patch("/api/users/me")
async def update_my_profile(payload: UpdateProfileRequest, user_id: str = Depends(_require_user_id)) -> JSONResponse:
    db_payload: dict[str, Any] = {}

    if payload.fullName is not None:
        db_payload["full_name"] = payload.fullName
    elif payload.firstName is not None or payload.lastName is not None or payload.middleName is not None:
        current_user_response = await _database_request("GET", f"/v1/users/{user_id}", user_id=user_id)
        if current_user_response.status_code >= 400:
            return JSONResponse(
                status_code=current_user_response.status_code,
                content=_normalize_error_from_response(current_user_response, "Failed to get current profile"),
            )
        current_user = _safe_json(current_user_response) or {}
        current_first, current_last, current_middle = _split_full_name(current_user.get("full_name"))
        full_name = _compose_full_name(
            payload.firstName if payload.firstName is not None else current_first,
            payload.lastName if payload.lastName is not None else current_last,
            payload.middleName if payload.middleName is not None else current_middle,
        )
        db_payload["full_name"] = full_name

    if "workPlace" in payload.model_fields_set:
        db_payload["work_place"] = payload.workPlace
    if "university" in payload.model_fields_set:
        db_payload["university"] = payload.university
    if "faculty" in payload.model_fields_set:
        db_payload["faculty"] = payload.faculty
    if "telegram" in payload.model_fields_set:
        db_payload["telegram"] = payload.telegram

    if not db_payload:
        return JSONResponse(status_code=422, content={"message": "Нужно передать хотя бы одно поле"})

    response = await _database_request("PATCH", f"/v1/users/{user_id}", json_data=db_payload, user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Failed to update profile"),
        )

    user = _to_front_user(_safe_json(response) or {})
    return JSONResponse(status_code=200, content=user)


@app.post("/api/users/me/photo")
async def upload_my_profile_photo(
    photo: UploadFile = File(...),
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    photo_bytes = await photo.read()
    if not photo_bytes:
        return JSONResponse(status_code=422, content={"message": "Файл пустой"})
    if len(photo_bytes) > MAX_PROFILE_IMAGE_BYTES:
        return JSONResponse(status_code=413, content={"message": "Размер фото профиля должен быть не больше 5 МБ"})

    content_type = photo.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        return JSONResponse(status_code=422, content={"message": "Можно загружать только изображения"})

    response = await _database_request(
        "POST",
        f"/v1/users/{user_id}/photo",
        user_id=user_id,
        files={
            "photo": (
                photo.filename or "profile-photo.jpg",
                photo_bytes,
                content_type,
            )
        },
    )
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Не удалось сохранить фото профиля"),
        )

    payload = _safe_json(response) or {}
    return JSONResponse(
        status_code=200,
        content={
            "hasPhoto": bool(payload.get("has_photo")),
            "contentType": payload.get("content_type"),
            "sizeBytes": payload.get("size_bytes"),
        },
    )


@app.get("/api/users/me/photo", response_model=None)
async def get_my_profile_photo(user_id: str = Depends(_require_user_id)) -> Response:
    response = await _database_request("GET", f"/v1/users/{user_id}/photo", user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Фото профиля не найдено"),
        )

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type") or "application/octet-stream",
    )


@app.get("/api/users/{target_user_id}/photo", response_model=None)
async def get_user_photo(target_user_id: str) -> Response:
    response = await _database_request("GET", f"/v1/users/{target_user_id}/photo")
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Фото пользователя не найдено"),
        )

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type") or "application/octet-stream",
    )


@app.get("/api/events")
async def list_events(
    date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="dateFrom"),
    date_to: str | None = Query(default=None, alias="dateTo"),
    tags: list[str] | None = Query(default=None),
) -> JSONResponse:
    params: dict[str, Any] = {"limit": 100, "offset": 0}
    starts_from_dt: datetime | None = None
    starts_to_dt: datetime | None = None

    normalized_tags: list[str] = []
    if tags:
        normalized_tags.extend(tag.strip() for tag in tags if tag and tag.strip())
    if category:
        normalized_tags.append(CATEGORY_TO_TAG.get(category, category))
    normalized_tags = list(dict.fromkeys(normalized_tags))
    if normalized_tags:
        params["tags"] = normalized_tags

    if date:
        try:
            day = datetime.fromisoformat(date).date()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid date filter") from exc
        starts_from_dt = datetime.combine(day, time.min, tzinfo=MOSCOW_TZ).astimezone(UTC)
        starts_to_dt = datetime.combine(day, time.max, tzinfo=MOSCOW_TZ).astimezone(UTC)
        params["starts_from"] = starts_from_dt.isoformat().replace("+00:00", "Z")
        params["starts_to"] = starts_to_dt.isoformat().replace("+00:00", "Z")
    else:
        if date_from:
            try:
                from_day = datetime.fromisoformat(date_from).date()
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dateFrom filter") from exc
            starts_from_dt = datetime.combine(from_day, time.min, tzinfo=MOSCOW_TZ).astimezone(UTC)
            params["starts_from"] = starts_from_dt.isoformat().replace("+00:00", "Z")
        if date_to:
            try:
                to_day = datetime.fromisoformat(date_to).date()
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dateTo filter") from exc
            starts_to_dt = datetime.combine(to_day, time.max, tzinfo=MOSCOW_TZ).astimezone(UTC)
            params["starts_to"] = starts_to_dt.isoformat().replace("+00:00", "Z")

    response = await _database_request("GET", "/v1/events", params=params)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to load events"))

    payload = _safe_json(response) or {}
    items = payload.get("items", [])
    normalized = []
    for item in items:
        event_response = await _database_request("GET", f"/v1/events/{item['id']}")
        if event_response.status_code >= 400:
            continue
        normalized.append(_map_event_from_db(event_response.json()))

    if normalized_tags:
        normalized = [
            event
            for event in normalized
            if all(tag in (event.get("tags") or []) for tag in normalized_tags)
        ]

    if starts_from_dt is not None:
        normalized = [
            event
            for event in normalized
            if _parse_api_datetime(event.get("eventDate")) is not None
            and _parse_api_datetime(event.get("eventDate")) >= starts_from_dt
        ]

    if starts_to_dt is not None:
        normalized = [
            event
            for event in normalized
            if _parse_api_datetime(event.get("eventDate")) is not None
            and _parse_api_datetime(event.get("eventDate")) <= starts_to_dt
        ]

    return JSONResponse(status_code=200, content=normalized)


@app.get("/api/events/{event_id}")
async def get_event(event_id: str) -> JSONResponse:
    response = await _database_request("GET", f"/v1/events/{event_id}")
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Event not found"))
    return JSONResponse(status_code=200, content=_map_event_from_db(_safe_json(response) or {}))


@app.post("/api/events")
async def create_event(
    title: str = Form(...),
    category: str = Form(...),
    eventFormat: str = Form(...),
    eventDate: str = Form(...),
    address: str = Form(""),
    addressSelected: bool = Form(False),
    description: str = Form(...),
    isPaid: bool = Form(False),
    price: str | None = Form(None),
    ticketItems: str | None = Form(None),
    image: UploadFile | None = File(default=None),
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    event_start_at = _parse_event_datetime(eventDate)
    event_format = _normalize_event_format(eventFormat)

    if event_format == "offline":
        if not addressSelected:
            return JSONResponse(status_code=422, content={"message": "Выберите адрес из выпадающего списка"})
        if not await _is_address_selected_and_valid(address):
            return JSONResponse(status_code=422, content={"message": "Адрес не прошёл валидацию, выберите вариант из списка"})

    image_bytes: bytes | None = None
    image_content_type: str | None = None
    image_filename: str = "cover.jpg"
    if image is not None:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_EVENT_IMAGE_BYTES:
            return JSONResponse(status_code=413, content={"message": "Размер изображения должен быть не больше 10 МБ"})
        image_content_type = image.content_type or "application/octet-stream"
        if not image_content_type.startswith("image/"):
            return JSONResponse(status_code=422, content={"message": "Можно загружать только изображения"})
        if image.filename:
            image_filename = image.filename

    db_payload = _build_front_event_payload(
        title=title,
        category=category,
        event_format=event_format,
        event_start_at=event_start_at,
        address=address,
        description=description,
        is_paid=isPaid,
        price=price,
        ticket_items_raw=ticketItems,
    )

    response = await _database_event_write_with_tag_fallback(
        "POST",
        "/v1/events",
        payload=db_payload,
        user_id=user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to create event"))

    created_event = _safe_json(response) or {}
    event_id = created_event.get("id")

    if image_bytes is None and event_id is not None:
        default_cover_file = _pick_default_cover_file(str(event_id))
        if default_cover_file is not None:
            image_bytes = default_cover_file.read_bytes()
            image_content_type = mimetypes.guess_type(default_cover_file.name)[0] or "image/jpeg"
            image_filename = default_cover_file.name

    if image_bytes is not None and event_id is not None:
        photo_response = await _database_request(
            "POST",
            f"/v1/events/{event_id}/photo",
            files={
                "photo": (
                    image_filename,
                    image_bytes,
                    image_content_type or "application/octet-stream",
                )
            },
            user_id=user_id,
        )
        if photo_response.status_code >= 400:
            return JSONResponse(
                status_code=photo_response.status_code,
                content=_normalize_error_from_response(photo_response, "Не удалось сохранить изображение"),
            )

    if event_id is None:
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=_map_event_from_db(created_event))

    refreshed_event_response = await _database_request("GET", f"/v1/events/{event_id}")
    if refreshed_event_response.status_code >= 400:
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=_map_event_from_db(created_event))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_map_event_from_db(_safe_json(refreshed_event_response) or created_event),
    )


@app.patch("/api/events/{event_id}")
async def update_event(
    event_id: str,
    title: str = Form(...),
    category: str = Form(...),
    eventFormat: str = Form(...),
    eventDate: str = Form(...),
    address: str = Form(""),
    addressSelected: bool = Form(False),
    description: str = Form(...),
    isPaid: bool = Form(False),
    price: str | None = Form(None),
    ticketItems: str | None = Form(None),
    image: UploadFile | None = File(default=None),
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    existing_response = await _database_request("GET", f"/v1/events/{event_id}", user_id=user_id)
    if existing_response.status_code >= 400:
        return JSONResponse(
            status_code=existing_response.status_code,
            content=_normalize_error_from_response(existing_response, "Событие не найдено"),
        )

    existing_event = _safe_json(existing_response) or {}
    event_start_at = _parse_event_datetime(eventDate)
    event_format = _normalize_event_format(eventFormat)
    if event_format == "offline":
        if not addressSelected:
            return JSONResponse(status_code=422, content={"message": "Выберите адрес из выпадающего списка"})
        if not await _is_address_selected_and_valid(address):
            return JSONResponse(status_code=422, content={"message": "Адрес не прошёл валидацию, выберите вариант из списка"})

    db_payload = _build_front_event_payload(
        title=title,
        category=category,
        event_format=event_format,
        event_start_at=event_start_at,
        address=address,
        description=description,
        is_paid=isPaid,
        price=price,
        ticket_items_raw=ticketItems,
        existing_event=existing_event,
    )

    response = await _database_event_write_with_tag_fallback(
        "PATCH",
        f"/v1/events/{event_id}",
        payload=db_payload,
        user_id=user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Не удалось обновить мероприятие"),
        )

    if image is not None:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_EVENT_IMAGE_BYTES:
            return JSONResponse(status_code=413, content={"message": "Размер изображения должен быть не больше 10 МБ"})

        image_content_type = image.content_type or "application/octet-stream"
        if not image_content_type.startswith("image/"):
            return JSONResponse(status_code=422, content={"message": "Можно загружать только изображения"})

        photo_response = await _database_request(
            "POST",
            f"/v1/events/{event_id}/photo",
            files={
                "photo": (
                    image.filename or "cover.jpg",
                    image_bytes,
                    image_content_type,
                )
            },
            user_id=user_id,
        )
        if photo_response.status_code >= 400:
            return JSONResponse(
                status_code=photo_response.status_code,
                content=_normalize_error_from_response(photo_response, "Не удалось сохранить изображение"),
            )

    refreshed_event_response = await _database_request("GET", f"/v1/events/{event_id}")
    if refreshed_event_response.status_code >= 400:
        return JSONResponse(status_code=200, content=_map_event_from_db(_safe_json(response) or {}))

    return JSONResponse(
        status_code=200,
        content=_map_event_from_db(_safe_json(refreshed_event_response) or _safe_json(response) or {}),
    )


@app.post("/api/events/{event_id}/cancel")
async def cancel_event(event_id: str, user_id: str = Depends(_require_user_id)) -> JSONResponse:
    response = await _database_request("POST", f"/v1/events/{event_id}/cancel", user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Не удалось отменить мероприятие"),
        )

    payload = _safe_json(response) or {}
    return JSONResponse(status_code=200, content=_map_event_from_db(payload))


@app.get("/api/events/{event_id}/image")
async def get_event_image(event_id: str) -> Response:
    response = await _database_request("GET", f"/v1/events/{event_id}/photo")
    if response.status_code >= 400:
        raise HTTPException(status_code=404, detail="Image not found")

    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(content=response.content, media_type=content_type)


@app.post("/api/events/{event_id}/register")
async def register_for_event(
    event_id: str,
    payload: EventRegisterRequest | None = None,
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    event_response = await _database_request("GET", f"/v1/events/{event_id}")
    if event_response.status_code >= 400:
        return JSONResponse(status_code=event_response.status_code, content=_normalize_error_from_response(event_response, "Event not found"))

    event_payload = _safe_json(event_response) or {}
    ticket_items, _ = _extract_event_meta(event_payload.get("recurrence_rule"))
    selected_ticket_title = (payload.ticketTitle.strip() if payload and payload.ticketTitle else "")

    if ticket_items:
        if not selected_ticket_title:
            return JSONResponse(status_code=422, content={"message": "Выберите билет"})
        allowed_titles = {str(item.get("title") or "").strip() for item in ticket_items}
        if selected_ticket_title not in allowed_titles:
            return JSONResponse(status_code=422, content={"message": "Выбранный билет не найден"})

    response = await _database_request("POST", f"/v1/events/{event_id}/registrations", user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to register for event"))
    return JSONResponse(status_code=response.status_code, content={"ok": True})


@app.delete("/api/events/{event_id}/registration/{registration_id}")
async def cancel_registration(event_id: str, registration_id: str, user_id: str = Depends(_require_user_id)) -> JSONResponse:
    _ = registration_id
    response = await _database_request("DELETE", f"/v1/events/{event_id}/registrations/me", user_id=user_id)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to cancel registration"))
    return JSONResponse(status_code=200, content={"ok": True})


@app.get("/api/events/{event_id}/participants")
async def get_participants(event_id: str, user_id: str = Depends(_require_user_id)) -> JSONResponse:
    response = await _database_request(
        "GET",
        f"/v1/events/{event_id}/participants",
        params={"limit": 100, "offset": 0, "status": "registered"},
        user_id=user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to load participants"))

    items = (_safe_json(response) or {}).get("items", [])

    normalized = [
        {
            "userId": item.get("user_id"),
            "fullName": item.get("full_name") or "—",
            "university": item.get("university"),
            "workPlace": item.get("work_place"),
            "telegram": item.get("telegram"),
            "checkedIn": bool(item.get("checked_in_at")),
            "checkedInAt": item.get("checked_in_at"),
        }
        for item in items
    ]
    return JSONResponse(status_code=200, content=normalized)


@app.post("/api/events/{event_id}/participants/{participant_user_id}/check-in")
async def check_in_participant(
    event_id: str,
    participant_user_id: str,
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    response = await _database_request(
        "POST",
        f"/v1/events/{event_id}/participants/{participant_user_id}/check-in",
        user_id=user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Не удалось отметить участника"),
        )

    participant_payload = await _find_event_participant(event_id, participant_user_id, user_id)
    if participant_payload is None:
        return JSONResponse(status_code=404, content={"message": "Участник не найден"})

    check_in_payload = _safe_json(response) or {}
    return JSONResponse(
        status_code=200,
        content={
            "eventId": event_id,
            "userId": participant_user_id,
            "fullName": participant_payload.get("full_name") or "—",
            "telegram": participant_payload.get("telegram"),
            "university": participant_payload.get("university"),
            "workPlace": participant_payload.get("work_place"),
            "checkedInAt": check_in_payload.get("checked_in_at"),
        },
    )


@app.post("/api/tickets/scan-link")
async def scan_ticket_link(payload: TicketScanRequest, user_id: str = Depends(_require_user_id)) -> JSONResponse:
    logger.info("Scan link request received: user_id=%s", user_id)
    try:
        event_id, participant_user_id = _extract_scan_ids(payload.scanUrl)
    except ValueError as exc:
        logger.warning("Scan link parse failed: user_id=%s error=%s", user_id, exc)
        return JSONResponse(status_code=422, content={"message": str(exc)})

    event_response = await _database_request("GET", f"/v1/events/{event_id}", user_id=user_id)
    if event_response.status_code >= 400:
        logger.warning("Scan event fetch failed: event_id=%s user_id=%s", event_id, user_id)
        return JSONResponse(
            status_code=event_response.status_code,
            content=_normalize_error_from_response(event_response, "Мероприятие не найдено"),
        )

    event_payload = _safe_json(event_response) or {}
    if str(event_payload.get("created_by_user_id")) != str(user_id):
        logger.warning("Scan forbidden: event_id=%s user_id=%s", event_id, user_id)
        return JSONResponse(status_code=403, content={"message": "Только организатор может сканировать билеты"})

    check_response = await _database_request(
        "POST",
        f"/v1/events/{event_id}/participants/{participant_user_id}/check-in",
        user_id=user_id,
    )
    if check_response.status_code >= 400:
        logger.warning(
            "Scan check-in failed: event_id=%s participant_user_id=%s user_id=%s",
            event_id,
            participant_user_id,
            user_id,
        )
        return JSONResponse(
            status_code=check_response.status_code,
            content=_normalize_error_from_response(check_response, "Не удалось проверить билет"),
        )

    participant_payload = await _find_event_participant(event_id, participant_user_id, user_id)
    if participant_payload is None:
        logger.warning("Scan participant lookup failed: event_id=%s participant_user_id=%s", event_id, participant_user_id)
        return JSONResponse(status_code=404, content={"message": "Участник не найден"})

    check_payload = _safe_json(check_response) or {}

    return JSONResponse(
        status_code=200,
        content={
            "event": {
                "id": event_id,
                "title": event_payload.get("title"),
            },
            "participant": {
                "id": participant_user_id,
                "fullName": participant_payload.get("full_name") or "—",
                "telegram": participant_payload.get("telegram"),
                "university": participant_payload.get("university"),
                "workPlace": participant_payload.get("work_place"),
                "checkedInAt": check_payload.get("checked_in_at"),
            },
        },
    )


@app.get("/api/users/{user_id}/registrations")
async def get_user_registrations(user_id: str, current_user_id: str = Depends(_require_user_id)) -> JSONResponse:
    if user_id != current_user_id:
        return JSONResponse(status_code=403, content={"message": "Недостаточно прав"})

    response = await _database_request(
        "GET",
        f"/v1/users/{user_id}/registered-events",
        params={"limit": 100, "offset": 0, "status": "registered"},
        user_id=current_user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to load registrations"))

    registrations = []
    for row in (_safe_json(response) or {}).get("items", []):
        event_response = await _database_request("GET", f"/v1/events/{row['id']}")
        if event_response.status_code >= 400:
            continue
        registrations.append(
            {
                "id": row["id"],
                "registeredAt": row.get("registered_at"),
                "event": _map_event_from_db(event_response.json()),
            }
        )

    return JSONResponse(status_code=200, content=registrations)


@app.get("/api/users/{user_id}/created-events")
async def get_created_events(user_id: str, current_user_id: str = Depends(_require_user_id)) -> JSONResponse:
    if user_id != current_user_id:
        return JSONResponse(status_code=403, content={"message": "Недостаточно прав"})

    response = await _database_request(
        "GET",
        f"/v1/users/{user_id}/created-events",
        params={"limit": 100, "offset": 0},
        user_id=current_user_id,
    )
    if response.status_code >= 400:
        return JSONResponse(
            status_code=response.status_code,
            content=_normalize_error_from_response(response, "Failed to load created events"),
        )

    events = []
    for row in (_safe_json(response) or {}).get("items", []):
        event_response = await _database_request("GET", f"/v1/events/{row['id']}")
        if event_response.status_code >= 400:
            continue
        events.append(_map_event_from_db(event_response.json()))

    return JSONResponse(status_code=200, content=events)


@app.get("/api/tg/profile")
async def tg_profile() -> JSONResponse:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{TGBOT_API_URL}/demo/profile")
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to load Telegram profile"))
    return JSONResponse(status_code=200, content=_safe_json(response) or {})


@app.post("/api/tg/demo/send")
async def tg_demo_send(payload: dict[str, Any], user_id: str = Depends(_require_user_id)) -> JSONResponse:
    _ = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{TGBOT_API_URL}/demo/send", json=payload)
    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=_normalize_error_from_response(response, "Failed to send Telegram message"))
    return JSONResponse(status_code=200, content=_safe_json(response) or {})


app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")
app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")
app.mount("/img", StaticFiles(directory=STATIC_DIR / "img"), name="img")
app.mount("/", WSGIMiddleware(frontend_app))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=WEBSITE_PORT, reload=False)
