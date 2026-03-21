# tgbot service

Telegram-микросервис для уведомлений и attendance-опросов.

## Env

Скопируйте `.env.example` в `.env` и заполните:

- `TG_BOT_TOKEN` - токен бота из BotFather
- `TG_BOT_PORT` - порт API (по умолчанию `8890`)
- `TG_BOT_PARSE_MODE` - `HTML`, `MARKDOWN`, `MARKDOWNV2`
- `TG_DEFAULT_CHAT_ID` - chat id получателя по умолчанию (для demo)
- `TG_DEFAULT_USERNAME` - username получателя по умолчанию (опционально)
- `TG_DB_BASE_URL` - base URL DB-сервиса (например, `http://database:6677`)
- `TG_DB_POLL_SECONDS` - период проверки due jobs (по ТЗ: `3600`)
- `TG_DB_DUE_LIMIT` - лимит задач за одну проверку
- `TG_DB_TIMEOUT_SECONDS` - timeout HTTP к DB-сервису
- `TG_WORKER_ID` - id воркера бота для `claim`
- `TG_DB_API_KEY` - опциональный Bearer token для DB-сервиса
- `LOG_LEVEL` - `INFO`/`DEBUG` и т.д.

## Как работает интеграция с DB

Фоновый worker раз в `TG_DB_POLL_SECONDS`:

1. Запрашивает `GET /v1/tg/jobs/due?from=...&to=...&limit=...`
2. Для каждой задачи делает `POST /v1/tg/jobs/{job_id}/claim`
3. Если `claimed=true`, отправляет сообщение в Telegram
4. При успехе вызывает `POST /v1/tg/jobs/{job_id}/complete`
5. При ошибке вызывает `POST /v1/tg/jobs/{job_id}/fail`

Для `attendance_ask_24h` кнопки `Приду/Не приду` содержат `request_id`.
При клике бот вызывает `POST /v1/tg/attendance/answer`.

## API

### Health

`GET /health`

### Проверить demo-профиль

`GET /demo/profile`

### Demo: отправить текст в чат по умолчанию

`POST /demo/send`

```json
{
  "text": "Напоминание: мероприятие начнется через час"
}
```

### Demo: отправить attendance-вопрос в чат по умолчанию

`POST /demo/attendance`

```json
{
  "event_id": "evt_42",
  "title": "Воркшоп по Python",
  "question": "Подтверди, пожалуйста, участие"
}
```

### Отправить текст по явному chat_id

`POST /notifications/send`

```json
{
  "chat_id": 123456789,
  "text": "Напоминание: мероприятие начнется через час"
}
```

### Отправить attendance-вопрос по явному chat_id

`POST /notifications/attendance`

```json
{
  "chat_id": 123456789,
  "event_id": "evt_42",
  "title": "Воркшоп по Python",
  "question": "Подтверди, пожалуйста, участие"
}
```

### Локально посмотреть собранные ответы

`GET /attendance/{request_id}`
