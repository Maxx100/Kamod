# Event Service

FastAPI-сервис для пользователей, событий, регистраций и Telegram-уведомлений.

## Что здесь лежит

- HTTP API на FastAPI
- SQLAlchemy 2.0 модели
- Alembic миграции
- PostgreSQL как основная БД

Source of truth по схеме БД: Alembic миграции в `alembic/versions`.

## Основные сущности

### User

- `id`
- `email`
- `password_hash`
- `full_name`
- `university`
- `faculty`
- `telegram`
- `is_active`
- `deleted_at`, `created_at`, `updated_at`

Пароль хранится только как хэш.

### Event

- `id`
- `created_by_user_id`
- `title`
- `description`
- `photo_url`
- `contacts`
- `format`
- `status`
- `price_minor`
- `event_start_at`
- `registration_start_at`
- `registration_end_at`
- `duration_minutes`
- `max_participants`
- `recurrence_rule`
- `attendance_ask_enabled`
- `cancelled_at`, `completed_at`, `deleted_at`, `created_at`, `updated_at`

### Tag

- `id`
- `slug`
- `name`
- `group_code`
- `is_active`

### EventRegistration

- `id`
- `event_id`
- `user_id`
- `status`
- `registered_at`
- `cancelled_at`

Повторная регистрация на то же событие не создает вторую запись: действует `UNIQUE (event_id, user_id)`.

### UserTelegramSettings

- `user_id`
- `telegram_user_id`
- `telegram_chat_id`
- `reminder_24h_enabled`
- `reminder_1h_enabled`

### TelegramNotificationJob

Очередь задач для внешнего Telegram-микросервиса.

- `id`
- `event_id`
- `user_id`
- `telegram_user_id`
- `telegram_chat_id`
- `kind`
- `status`
- `scheduled_at`
- `request_id`
- `claimed_by`
- `claimed_at`
- `sent_at`
- `telegram_message_id`
- `failed_at`
- `error`
- `cancelled_at`

`kind`:

- `reminder_24h`
- `reminder_1h`
- `attendance_ask_24h`

### TelegramAttendanceAnswer

- `id`
- `request_id`
- `event_id`
- `user_id`
- `telegram_user_id`
- `answer`
- `answered_at`

Уникальность ответа: `(request_id, telegram_user_id)`.

## API

### Основные группы

- `/v1/auth` — регистрация пользователя
- `/v1/users` — профиль, созданные события, зарегистрированные события
- `/v1/events` — создание, редактирование, отмена, завершение, список, карточка события, регистрации
- `/v1/tg` — контракты для Telegram-микросервиса

### Telegram API

- `GET /v1/tg/jobs/due?from=<ISO_UTC>&to=<ISO_UTC>&limit=500`
- `POST /v1/tg/jobs/{job_id}/claim`
- `POST /v1/tg/jobs/{job_id}/complete`
- `POST /v1/tg/jobs/{job_id}/fail`
- `POST /v1/tg/attendance/answer`

Ожидаемая схема работы Telegram-воркера:

1. Раз в час опрашивает `jobs/due`
2. На каждую задачу делает `claim`
3. Если `claimed=false`, задачу уже взял другой воркер
4. Если сообщение отправилось, вызывает `complete`
5. Если отправка не удалась, вызывает `fail`
6. Для attendance-кнопок отправляет `attendance/answer`

### Временная аутентификация

Для защищенных endpoint-ов пока используется header `X-User-Id`.

Это временная заглушка до отдельного auth-сервиса.

## Локальный запуск

### 1. Подготовить env

Скопируйте:

- `.env.example` -> `.env`
- `services/database/.env.example` -> `services/database/.env`

Заполнять реальные секреты нужно только в локальных `.env`.

### 2. Где лежат данные

Живая PostgreSQL data dir:

- `data/postgres`

SQL-бэкапы:

- `data/backups`

### 3. Запуск

Пример через compose:

```bash
docker compose up -d postgres
docker compose up -d database
```

`database` контейнер теперь сам применяет `alembic upgrade head` при старте.

### 4. Документация API

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`
- `http://localhost:8000/openapi.json`

## Миграции

Ключевые миграции:

- `alembic/versions/0001_create_event_service_schema.py`
- `alembic/versions/0002_add_telegram_notification_jobs.py`

### Как ускорить создание миграций

Для типовых изменений схемы можно использовать автогенерацию:

```bash
docker compose exec database alembic revision --autogenerate -m "your_message"
```

Дальше обязательно проверьте файл миграции вручную (особенно для rename/удалений и data-migration).

## Примечания

- Фото события хранится как `photo_url`
- Теги реализованы через справочник `tags` и связь `event_tags`
- Повторяемость события хранится как `recurrence_rule`
- Для пользователей и событий используется soft delete
