from __future__ import annotations

import os
import mimetypes
from hashlib import sha256
from pathlib import Path
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

import httpx
import jwt
import uvicorn
from flask import Flask, redirect, render_template
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.middleware.wsgi import WSGIMiddleware


DATABASE_API_URL = os.getenv("DATABASE_API_URL", "http://database:5000").rstrip("/")
TGBOT_API_URL = os.getenv("TGBOT_API_URL", "http://tgbot:8890").rstrip("/")
WEBSITE_PORT = int(os.getenv("WEBSITE_PORT", "3001"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_COVERS_DIR = STATIC_DIR / "img"

JWT_SECRET = os.getenv("WEBSITE_JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("WEBSITE_JWT_ALGORITHM", "HS256")
JWT_EXPIRE_SECONDS = int(os.getenv("WEBSITE_JWT_EXPIRE_SECONDS", str(30 * 24 * 3600)))
MAX_EVENT_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024

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


class RegisterRequest(BaseModel):
    fullName: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    university: str | None = None
    faculty: str | None = None
    course: str | None = None
    telegram: str | None = None

    @field_validator("university", "faculty", "course", "telegram", mode="before")
    @classmethod
    def blank_optional_fields_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class LoginRequest(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=8)


class UpdateProfileRequest(BaseModel):
    fullName: str | None = None
    university: str | None = None
    faculty: str | None = None
    telegram: str | None = None

    @field_validator("university", "faculty", "telegram", mode="before")
    @classmethod
    def blank_profile_fields_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


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
    return {
        "id": user["id"],
        "email": user["email"],
        "fullName": user["full_name"],
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
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed


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
    if (
        current_registration_start_at is not None
        and current_registration_end_at is not None
        and current_registration_start_at <= current_registration_end_at <= event_start_at
    ):
        return current_registration_start_at, current_registration_end_at

    registration_end_at = event_start_at - timedelta(minutes=1)
    registration_start_at = datetime.now(UTC)

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

    return {
        "title": title,
        "description": description,
        "photo_url": (existing_event or {}).get("photo_url"),
        "tag_slugs": tag_slugs,
        "event_start_at": _to_utc_iso(event_start_at),
        "registration_start_at": _to_utc_iso(registration_start_at),
        "registration_end_at": _to_utc_iso(registration_end_at),
        "format": event_format,
        "price_minor": _parse_price_minor(is_paid, price),
        "contacts": contacts,
        "recurrence_rule": (existing_event or {}).get("recurrence_rule"),
        "attendance_ask_enabled": (existing_event or {}).get("attendance_ask_enabled", True),
        "max_participants": (existing_event or {}).get("max_participants"),
        "duration_minutes": (existing_event or {}).get("duration_minutes", 120),
    }


def _map_event_from_db(event: dict[str, Any]) -> dict[str, Any]:
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
        "isPaid": int(event.get("price_minor") or 0) > 0,
        "price": int(event.get("price_minor") or 0) // 100,
        "organizerId": event.get("created_by_user_id"),
        "organizer": {
            "id": creator.get("id"),
            "fullName": creator.get("full_name") or "Организатор",
            "university": creator.get("university") or "—",
            "telegram": creator.get("telegram"),
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


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> JSONResponse:
    db_payload = {
        "email": payload.email,
        "password": payload.password,
        "full_name": payload.fullName,
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
    if payload.university is not None:
        db_payload["university"] = payload.university
    if payload.faculty is not None:
        db_payload["faculty"] = payload.faculty
    if payload.telegram is not None:
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
        starts_from_dt = datetime.combine(day, time.min, tzinfo=UTC)
        starts_to_dt = datetime.combine(day, time.max, tzinfo=UTC)
        params["starts_from"] = starts_from_dt.isoformat().replace("+00:00", "Z")
        params["starts_to"] = starts_to_dt.isoformat().replace("+00:00", "Z")
    else:
        if date_from:
            try:
                from_day = datetime.fromisoformat(date_from).date()
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dateFrom filter") from exc
            starts_from_dt = datetime.combine(from_day, time.min, tzinfo=UTC)
            params["starts_from"] = starts_from_dt.isoformat().replace("+00:00", "Z")
        if date_to:
            try:
                to_day = datetime.fromisoformat(date_to).date()
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dateTo filter") from exc
            starts_to_dt = datetime.combine(to_day, time.max, tzinfo=UTC)
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
    description: str = Form(...),
    isPaid: bool = Form(False),
    price: str | None = Form(None),
    image: UploadFile | None = File(default=None),
    user_id: str = Depends(_require_user_id),
) -> JSONResponse:
    event_start_at = _parse_event_datetime(eventDate)
    event_format = _normalize_event_format(eventFormat)

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
    description: str = Form(...),
    isPaid: bool = Form(False),
    price: str | None = Form(None),
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
    db_payload = _build_front_event_payload(
        title=title,
        category=category,
        event_format=event_format,
        event_start_at=event_start_at,
        address=address,
        description=description,
        is_paid=isPaid,
        price=price,
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


@app.get("/api/events/{event_id}/image")
async def get_event_image(event_id: str) -> Response:
    response = await _database_request("GET", f"/v1/events/{event_id}/photo")
    if response.status_code >= 400:
        raise HTTPException(status_code=404, detail="Image not found")

    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(content=response.content, media_type=content_type)


@app.post("/api/events/{event_id}/register")
async def register_for_event(event_id: str, user_id: str = Depends(_require_user_id)) -> JSONResponse:
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
            "university": "—",
            "telegram": item.get("telegram"),
        }
        for item in items
    ]
    return JSONResponse(status_code=200, content=normalized)


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
