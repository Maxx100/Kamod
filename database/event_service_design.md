# Event Service Design

## 1. Сущности

### User
- `id: uuid`
- `email: citext`, уникальный
- `password_hash: text`
- `full_name: text`
- `university: text | null`
- `faculty: text | null`
- `telegram: text | null`
- `is_active: bool`
- `deleted_at, created_at, updated_at`

### Event
- `id: uuid`
- `created_by_user_id: uuid -> users.id`
- `title: text`
- `description: text`
- `photo_url: text | null`
- `contacts: text`
- `format: offline | online`
- `status: published | cancelled | completed`
- `price_minor: bigint`
- `event_start_at: timestamptz`
- `registration_start_at: timestamptz`
- `registration_end_at: timestamptz`
- `duration_minutes: int`
- `max_participants: int | null`
- `recurrence_rule: text | null`
- `cancelled_at, completed_at, deleted_at, created_at, updated_at`

### Tag
- `id: uuid`
- `slug: text`, уникальный
- `name: text`
- `group_code: text | null`
- `is_active: bool`
- `created_at, updated_at`

### EventTag
- связь many-to-many между `events` и `tags`

### EventRegistration
- `id: uuid`
- `event_id: uuid -> events.id`
- `user_id: uuid -> users.id`
- `status: registered | cancelled`
- `registered_at`
- `cancelled_at | null`
- `created_at, updated_at`

## 2. Связи

- `users 1 -> N events`: один пользователь может создать много событий.
- `events N <-> N tags`: одно событие имеет много тегов, один тег может использоваться у многих событий.
- `users N <-> N events` через `event_registrations`: пользователь может регистрироваться на много событий, событие может иметь много участников.
- В таблице регистраций действует `UNIQUE (event_id, user_id)`: одновременно второй активной регистрации не будет, а повторная регистрация после отмены делается через изменение статуса существующей записи.

## 3. PostgreSQL-схема

- Готовый DDL: [event_service_schema.sql](/home/alexander/Projects/Kamod/database/event_service_schema.sql)
- Для временных полей используется `timestamptz`.
- Для PK выбран `UUID`: это удобнее для микросервисной архитектуры, интеграций и безопасного внешнего API.
- `deleted_at` используется как soft delete для сущностей, которые нельзя физически удалять.

## 4. Ограничения и индексы

### Primary Keys
- `users.id`
- `events.id`
- `tags.id`
- `event_registrations.id`
- `event_tags (event_id, tag_id)`

### Foreign Keys
- `events.created_by_user_id -> users.id`
- `event_tags.event_id -> events.id`
- `event_tags.tag_id -> tags.id`
- `event_registrations.event_id -> events.id`
- `event_registrations.user_id -> users.id`

### Unique
- `users.email`
- `tags.slug`
- `event_registrations (event_id, user_id)`

### Check
- обязательные текстовые поля не пустые после `btrim(...)`
- `price_minor >= 0`
- `duration_minutes > 0`
- `max_participants IS NULL OR max_participants > 0`
- `registration_start_at <= registration_end_at <= event_start_at`
- консистентность `status` и `cancelled_at/completed_at`
- базовая валидация `telegram`
- формат `tags.slug`

### Индексы
- публичная выдача событий: `(event_start_at, id)` для `published` и не удаленных
- события пользователя: `(created_by_user_id, created_at desc)`
- фильтрация по статусу: `(status, event_start_at desc)`
- фильтрация по формату: `(format, event_start_at, id)` для `published`
- фильтрация по тегам: `(tag_id, event_id)` в `event_tags`
- участники события: `event_registrations(event_id, created_at)` partial для `status='registered'`
- события пользователя по регистрациям: `event_registrations(user_id, created_at desc)` partial для `status='registered'`

## 5. Решения по неоднозначным местам

### Tags / filters
- Основная модель: справочник `tags` + таблица связи `event_tags`.
- Почему: это лучше масштабируется, чем `enum`, не требует миграции на каждую новую категорию и лучше подходит для фильтрации, аналитики и moderation.
- При этом структурные фильтры (`format`, бесплатность через `price_minor = 0`) остаются отдельными полями и не дублируются тегами.

### Photo
- Основной вариант: хранить в БД только `photo_url`.
- Почему: для production не стоит хранить бинарные файлы в PostgreSQL для такой задачи; правильнее хранить объект в S3/MinIO/CDN и ссылку или storage key в БД.
- Альтернатива: `photo_storage_key` вместо URL, если media layer появится сразу.

### Recurrence
- Основной вариант: `recurrence_rule: text | null` в формате RRULE.
- Почему: это минимально-достаточный и расширяемый формат без взрыва схемы.
- На текущем этапе каждое событие считается отдельной registerable-сущностью; полноценные серии/инстансы можно позже вынести в `event_series` и `event_occurrences`.

### University / faculty
- Пока как свободный текст в `users`.
- Почему: это не ядро доменной модели, и отдельные справочники сейчас добавят сложности больше, чем пользы.
- Альтернатива: выделить `universities` и `faculties`, когда появятся фильтры, антидублирование и отчетность по этим полям.

## 6. API-контракты

Во всех write-операциях пользователь определяется из access token, а не из request body.

### POST /v1/auth/register
Request:
```json
{
  "email": "student@example.com",
  "password": "StrongPassword123",
  "full_name": "Иван Иванов",
  "university": "МГУ",
  "faculty": "ВМК",
  "telegram": "@ivan_ivanov"
}
```
Response `201 Created`:
```json
{
  "id": "uuid",
  "email": "student@example.com",
  "full_name": "Иван Иванов",
  "university": "МГУ",
  "faculty": "ВМК",
  "telegram": "@ivan_ivanov",
  "is_active": true,
  "created_at": "2026-03-21T12:00:00Z",
  "updated_at": "2026-03-21T12:00:00Z"
}
```
Errors:
- `409`: email уже занят
- `422`: невалидный email / слабый пароль / плохой telegram

### GET /v1/users/{user_id}
Response `200 OK`:
```json
{
  "id": "uuid",
  "email": "student@example.com",
  "full_name": "Иван Иванов",
  "university": "МГУ",
  "faculty": "ВМК",
  "telegram": "@ivan_ivanov",
  "is_active": true,
  "created_at": "2026-03-21T12:00:00Z",
  "updated_at": "2026-03-21T12:00:00Z"
}
```
Errors:
- `404`: пользователь не найден
- `403`: нет прав на просмотр приватного профиля

### POST /v1/events
Request:
```json
{
  "title": "AI Hackathon 2026",
  "description": "Командный хакатон для студентов",
  "photo_url": "https://cdn.example.com/events/ai-hackathon.jpg",
  "tag_slugs": ["hackathon", "it", "free"],
  "event_start_at": "2026-04-10T10:00:00Z",
  "registration_start_at": "2026-03-25T10:00:00Z",
  "registration_end_at": "2026-04-08T23:59:59Z",
  "format": "offline",
  "price_minor": 0,
  "contacts": "tg: @hack_org, email: hack@example.com",
  "recurrence_rule": null,
  "max_participants": 150,
  "duration_minutes": 480
}
```
Response `201 Created`: объект события с `id`, `status`, `creator`, `tags`, audit-полями.
Errors:
- `422`: плохие даты / отрицательная цена / неизвестный тег

### PATCH /v1/events/{event_id}
Request: частичный JSON, поля те же, что у создания.
Правило: если `tag_slugs` передан, это полная замена набора тегов.
Response `200 OK`: обновленный объект события.
Errors:
- `404`: событие не найдено
- `403`: редактирует не создатель
- `409`: нельзя редактировать `cancelled` или `completed`
- `422`: нарушены временные или числовые ограничения

### POST /v1/events/{event_id}/cancel
Request body: пустой.
Response `200 OK`: событие со `status = "cancelled"` и `cancelled_at`.
Errors:
- `404`, `403`
- `409`: уже cancelled/completed

### POST /v1/events/{event_id}/complete
Request body: пустой.
Response `200 OK`: событие со `status = "completed"` и `completed_at`.
Errors:
- `404`, `403`
- `409`: уже cancelled/completed

### GET /v1/events
Query params:
- `limit`, `offset`
- `status`
- `created_by_user_id`
- `tag`
- `format`
- `is_free`
- `starts_from`
- `starts_to`
- `registration_open`
Response `200 OK`:
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "AI Hackathon 2026",
      "format": "offline",
      "status": "published",
      "price_minor": 0,
      "event_start_at": "2026-04-10T10:00:00Z",
      "max_participants": 150,
      "registered_count": 42,
      "tag_slugs": ["hackathon", "it", "free"]
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```
Notes:
- публичный список по умолчанию возвращает только `published` и не удаленные события

### GET /v1/events/{event_id}
Response `200 OK`: полная карточка события с creator summary, tags, `registered_count`, `is_registration_open`.
Errors:
- `404`: событие не найдено или скрыто

### POST /v1/events/{event_id}/registrations
Request body: пустой.
Response:
- `201 Created`, если регистрация создана впервые
- `200 OK`, если была `cancelled` и стала снова `registered`
```json
{
  "id": "uuid",
  "event_id": "uuid",
  "user_id": "uuid",
  "status": "registered",
  "registered_at": "2026-03-30T12:00:00Z",
  "created_at": "2026-03-30T12:00:00Z",
  "updated_at": "2026-03-30T12:00:00Z"
}
```
Errors:
- `404`: событие не найдено
- `409`: уже зарегистрирован
- `409`: регистрация закрыта / событие отменено / лимит мест исчерпан

### DELETE /v1/events/{event_id}/registrations/me
Response `204 No Content`.
Errors:
- `404`: активной регистрации нет
- `409`: событие уже завершено и отмена недоступна по бизнес-правилу

### GET /v1/events/{event_id}/participants
Query params:
- `limit`, `offset`
- `status=registered|cancelled` по умолчанию `registered`
Response `200 OK`:
```json
{
  "items": [
    {
      "user_id": "uuid",
      "full_name": "Иван Иванов",
      "telegram": "@ivan_ivanov",
      "status": "registered",
      "registered_at": "2026-03-30T12:00:00Z"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```
Errors:
- `404`: событие не найдено
- `403`: доступ только создателю события или администратору

### GET /v1/users/{user_id}/registered-events
Query params:
- `limit`, `offset`
- `status=registered|cancelled`
Response `200 OK`: список событий пользователя через `event_registrations`.
Errors:
- `404`: пользователь не найден
- `403`: доступ только самому пользователю или внутреннему сервису

### GET /v1/users/{user_id}/created-events
Query params:
- `limit`, `offset`
- `status`
Response `200 OK`: список событий, созданных пользователем.
Errors:
- `404`: пользователь не найден

## 7. Что валидировать в БД, а что в приложении

### В БД
- PK/FK/UNIQUE
- soft delete поля
- базовые `CHECK` на числа, пустые строки, порядок дат
- консистентность статусов и timestamp-полей
- уникальность `email`, `tag.slug`, `(event_id, user_id)`

### В приложении
- хэширование пароля и проверка сложности пароля
- синтаксис email и нормализация входных данных
- права доступа
- допустимые переходы статусов
- правило "нельзя зарегистрироваться до/после окна регистрации"
- правило "нельзя зарегистрироваться на cancelled event"
- правило лимита участников
- валидация того, что `photo_url` реально доступен или принадлежит вашему storage
- глубокая валидация `recurrence_rule`

### Практический production-подход для регистрации
- Проверки окна регистрации, статуса события и лимита мест делать в одной транзакции.
- Перед вставкой/обновлением регистрации блокировать строку события через `SELECT ... FOR UPDATE`.
- После блокировки считать активные регистрации по partial index или позже перейти на денормализованный счетчик, если нагрузка вырастет.

### Рекомендация для микросервисов
- Если другие сервисы должны реагировать на создание/отмену события или регистрацию, добавьте transactional outbox отдельной таблицей, а не публикуйте события напрямую из кода после commit.
