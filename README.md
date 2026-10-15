# Асинхронный сервис процессинга платежей

Микросервис асинхронного процессинга платежей. Принимает запрос на оплату, проводит его через эмулятор платёжного шлюза и сообщает клиенту результат через webhook.

**Стек:** FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL, RabbitMQ (FastStream), Alembic, punq, Docker.

## Быстрый старт

```bash
cp .env.example .env          # при необходимости поменяйте порты
docker compose up -d --build  # или: make env up
```

| Сервис | Назначение | Адрес на хосте |
|---|---|---|
| `api` | HTTP API, Swagger: `/docs` | http://localhost:8000 |
| `outbox-relay` | Переносит события из таблицы `outbox` в RabbitMQ | — |
| `consumer` | Обрабатывает `payments.new`: шлюз → статус → webhook | — |
| `migrations` | `alembic upgrade head`, завершается после применения | — |
| `postgres` | БД | localhost:5432 |
| `rabbitmq` | Брокер, UI management (`guest`/`guest`) | http://localhost:15672 |
| `webhook-mock` | Тестовый получатель webhook | http://localhost:8090 |

Все запросы к `/api/v1/*` требуют заголовок `X-API-Key` (по умолчанию `dev-secret-key`, переменная `API_KEY`).

## Примеры

**Создать платёж**

```bash
curl -i -X POST http://localhost:8000/api/v1/payments \
  -H 'X-API-Key: dev-secret-key' \
  -H 'Idempotency-Key: order-42' \
  -H 'Content-Type: application/json' \
  -d '{
        "amount": "1500.00",
        "currency": "RUB",
        "description": "Order #42",
        "metadata": {"order_id": 42},
        "webhook_url": "http://webhook-mock:8080/webhook"
      }'
```
```
HTTP/1.1 202 Accepted

{"payment_id":"3b4b5621-…","status":"pending","created_at":"2026-10-15T07:10:00.453633Z"}
```

**Получить платёж**

```bash
curl http://localhost:8000/api/v1/payments/<payment_id> -H 'X-API-Key: dev-secret-key'
```
```json
{
  "payment_id": "3b4b5621-…",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Order #42",
  "metadata": {"order_id": 42},
  "status": "succeeded",
  "idempotency_key": "order-42",
  "webhook_url": "http://webhook-mock:8080/webhook",
  "created_at": "2026-10-15T07:10:00.453633Z",
  "processed_at": "2026-10-15T07:10:05.835346Z"
}
```

**Посмотреть пришедшие webhook:** `make webhooks` или `curl http://localhost:8090/received`

Эндпоинты `webhook-mock` (внутри сети compose — `http://webhook-mock:8080`):

| Путь | Ответ |
|---|---|
| `POST /webhook` | всегда 200 |
| `POST /webhook/fail` | всегда 500 — сообщение исчерпает попытки и уйдёт в DLQ |
| `POST /webhook/flaky/{n}` | первые `n` вызовов на платёж — 500, затем 200 |
| `GET /received` | последние 100 полученных webhook |

Тело webhook:

```json
{"event": "payment.succeeded", "payment_id": "…", "status": "succeeded", "amount": "1500.00",
 "currency": "RUB", "description": "Order #42", "metadata": {"order_id": 42},
 "created_at": "…", "processed_at": "…"}
```

**Ошибки** возвращаются в едином формате:

```json
{"error": {"code": "idempotency_key_conflict", "message": "…"}}
```

| Код | Когда |
|---|---|
| 401 | Нет или неверный `X-API-Key` |
| 404 | Платёж не найден |
| 409 | `Idempotency-Key` уже использован с другим телом запроса (`idempotency_key_conflict`); редкий сбой при гонке запросов с одним ключом (`idempotent_payment_not_found`) — запрос можно безопасно повторить |
| 422 | Невалидное тело, нет `Idempotency-Key` |

## Архитектура

```
        POST /payments                                 ┌──────────────┐
client ────────────────▶ api ──── 1 транзакция ──────▶ │  PostgreSQL  │
                                  payments + outbox    │              │
                                                       └──────┬───────┘
                                                              │ SELECT … FOR UPDATE SKIP LOCKED
                                                        outbox-relay
                                                              │ publish (publisher confirms)
                                                              ▼
                                                  RabbitMQ: payments → payments.new
                                                              │
                                                          consumer ── шлюз (2–5 с, 90/10)
                                                              │      └─ UPDATE status
                                                              ▼
                                                     POST webhook_url
```

### Структура кода

```
app/
  main.py                  # сборка FastAPI: /api/v1, роутеры, обработчики ошибок
  config.py                # Settings (pydantic-settings), get_settings()
  common/                  # generate_uuid, utcnow, настройка логирования
  di/container.py          # composition root на punq: порт → адаптер
  api/
    exception_handlers.py  # рендеринг ответа об ошибке
    exception_statuses.py  # доменное исключение → HTTP-код
    auth/dependencies.py   # проверка X-API-Key
    payment/methods.py     # ручки
    payment/schemas.py     # схемы запроса и ответа
  domain/                  # ничего не знает про HTTP, БД, брокер и логирование
    entities/              # Payment, OutboxEvent: фабрики и инварианты
    use_cases/             # Command + UseCase (+ Result): CreatePayment, GetPayment,
                           #   ProcessPayment, PublishOutbox
    repositories/          # порты хранилищ (ABC) и UnitOfWork (только транзакция)
    services/              # порты: PaymentGateway, WebhookNotifier, EventPublisher
    exceptions/            # доменные исключения (dataclass) по подобластям
  infrastructure/          # адаптеры портов
    database.py            # engine, session factory, SessionContext (сессия текущей транзакции)
    models/                # ORM-модели + from_entity()/to_entity()
    repositories/          # SQLAlchemy-репозитории и UnitOfWork
    messaging/             # брокер, топология, publisher, контракт сообщения
    gateway/emulator.py    # эмулятор платёжного шлюза
    webhook/http_notifier.py
  workers/
    outbox_relay.py        # процесс relay
    consumer.py            # процесс consumer (retry, DLQ, логирование исходов)
migrations/                # Alembic
tools/webhook_mock/        # тестовый получатель webhook
tests/unit                 # use cases и сущности на in-memory fakes
tests/e2e                  # сквозные тесты против docker compose
Makefile                   # частые команды (make help)
```

Зависимости направлены внутрь: `api`, `workers` → `domain` ← `infrastructure`. Use cases зависят только от абстракций (`UnitOfWork`, `PaymentRepository`, `PaymentGateway`, …), реализации подставляет `di/container.py`. Поэтому use cases покрыты unit-тестами на in-memory fake-реализациях, без БД и брокера.

### Соглашения

**Use case** — `@dataclass(frozen=True, slots=True)`, зависимости — его поля. Вход — `Command`, выход — сущность или `Result`:

```python
@dataclass(frozen=True, slots=True)
class CreatePaymentUseCase:
    uow: UnitOfWork
    payments: PaymentRepository
    outbox: OutboxRepository

    async def execute(self, command: CreatePaymentCommand) -> CreatePaymentResult:
        async with self.uow:
            ...
            await self.payments.add(payment)
            await self.outbox.add(OutboxEvent.payment_created(payment))
            await self.uow.commit()
```

**Репозитории и транзакция.** Репозитории внедряются в use case напрямую, `UnitOfWork` отвечает только за транзакцию (`async with uow`, `commit`). Общую сессию хранит `SessionContext` в `ContextVar`: UoW открывает её при входе в `async with`, репозитории берут её оттуда. Каждый HTTP-запрос и каждое сообщение из очереди обрабатывается в своей asyncio-задаче и видит только свою сессию, поэтому UoW и репозитории — синглтоны в DI-контейнере. Обращение к репозиторию вне `async with uow` и вложенные транзакции дают явную ошибку.

**Чтение по id:** `PaymentRepository.try_get()` возвращает `Payment | None`, `get()` бросает `PaymentNotFoundError`.

**Доменные исключения** — `@dataclass(eq=False)` от `DomainError`: данные ошибки в полях, машиночитаемый `code` (`ClassVar`) и текст `message`. В HTTP-статус их переводит таблица `api/exception_statuses.py`, ответ рендерит `api/exception_handlers.py`.

**Логирование — в транспортном слое.** Domain не логирует: use case возвращает результат, а воркер решает, что записать. `ProcessPaymentUseCase` возвращает `ProcessPaymentResult` с исходом:

| Исход | Значение | Уровень лога |
|---|---|---|
| `CHARGED` | списание проведено этим вызовом | INFO |
| `ALREADY_PROCESSED` | статус уже был итоговым (повторная доставка) — только повтор webhook | INFO |
| `CONCURRENTLY_PROCESSED` | шлюз вызван, но параллельный обработчик сохранил результат раньше; наш отброшен | WARNING |

`PublishOutboxUseCase` возвращает `PublishOutboxResult(published, error)`: число опубликованных событий и ошибку, на которой пачка прервалась.

## Гарантии доставки

### Outbox pattern

`CreatePaymentUseCase` пишет платёж и событие `payment.created` в таблицу `outbox` **в одной транзакции**. API в брокер не публикует, поэтому платёж без события (или событие без платежа) невозможен.

`outbox-relay` в цикле:
1. выбирает пачку неопубликованных событий через `FOR UPDATE SKIP LOCKED`, так что можно запускать несколько relay;
2. публикует каждое в RabbitMQ и ждёт publisher confirm. Неподтверждённая или несмаршрутизированная публикация считается ошибкой;
3. проставляет `published_at` и коммитит.

Если брокер недоступен, события ждут в таблице и уходят после восстановления (проверено остановкой контейнера `rabbitmq`). Гарантия **at-least-once**: падение между публикацией и commit даст повтор, который consumer переживает благодаря идемпотентности.

### Идемпотентность

- **API.** На `idempotency_key` стоит `UNIQUE`, рядом хранится `request_hash` (SHA-256 нормализованного тела).
  - Повтор с тем же ключом и тем же телом возвращает **тот же** платёж (`202`, заголовок `Idempotent-Replayed: true`).
  - Тот же ключ с другим телом возвращает `409 Conflict`, а не молча отдаёт чужой платёж.
  - Гонку параллельных запросов закрывает уникальный индекс: проигравший получает `DuplicateIdempotencyKeyError` из UoW и возвращает платёж победителя (10 параллельных запросов → 1 платёж, 1 событие).
- **Consumer.** Шлюз вызывается только для платежа в статусе `pending`. Результат записывается под `SELECT … FOR UPDATE` с повторной проверкой статуса. При повторной доставке сообщения повторяется только отправка webhook (исход `ALREADY_PROCESSED`), повторного списания не будет. Статус сохраняется до отправки webhook, поэтому retry после сбоя webhook не проводит платёж заново.

`request_hash` — осознанное расширение ТЗ: без него переиспользование ключа для другого платежа осталось бы незамеченным.

### Retry и Dead Letter Queue

```
payments (direct) ──payments.new──▶ [payments.new] ──▶ consumer
                                         │ reject (сбой самой переотправки / битое сообщение)
payments.retry (direct)                  ▼
  ├─▶ [payments.new.retry.2000ms] ┐   payments.dlx (direct) ──▶ [payments.new.dlq]
  └─▶ [payments.new.retry.4000ms] ┘
        │ TTL истёк → dead-letter обратно в payments.new
```

- Технический сбой при обработке (webhook не 2xx или таймаут, ошибка БД и т. п.) → consumer публикует сообщение в retry-очередь с номером попытки в заголовке `x-attempt` и подтверждает исходное. По истечении TTL RabbitMQ возвращает сообщение в `payments.new`.
- Задержка растёт экспоненциально: `RETRY_BASE_DELAY · 2ⁿ`, по умолчанию 2 с, затем 4 с.
- Под каждую задержку своя retry-очередь с `x-message-ttl` на уровне очереди. RabbitMQ снимает просроченные сообщения только с головы очереди, поэтому при разных TTL в одной очереди сообщение с длинной задержкой задержало бы короткие за ним.
- Имя retry-очереди содержит задержку (`payments.new.retry.2000ms`). При смене `RETRY_BASE_DELAY` создаётся новая очередь, а не возникает конфликт аргументов с уже объявленной (`PRECONDITION_FAILED`).
- После `RETRY_MAX_ATTEMPTS` попыток (по умолчанию **3 попытки всего**) сообщение уходит в `payments.new.dlq` с заголовками `x-attempt` и `x-last-error`.
- Неисправимые ошибки (платёж не найден) уходят в DLQ сразу. Сообщение, которое не удалось разобрать, или упавшая переотправка приводят к `reject`, и сообщение попадает в DLQ через `x-dead-letter-exchange` основной очереди, не теряясь.
- Ответ шлюза `failed` (10 %) — штатный бизнес-результат, а не ошибка: статус `failed` сохраняется, клиент получает webhook, ретрая нет.
- Топологию (exchanges, очереди, привязки) идемпотентно объявляют при старте и `consumer`, и `outbox-relay` (`infrastructure/messaging/topology.py`). Relay не должен публиковать, пока у exchange нет очереди: иначе сообщение некуда смаршрутизировать.

**Демонстрация:**

```bash
# webhook сначала отвечает 500, потом 200 → успех со 2-й попытки
curl -X POST http://localhost:8000/api/v1/payments -H 'X-API-Key: dev-secret-key' \
  -H 'Idempotency-Key: flaky-1' -H 'Content-Type: application/json' \
  -d '{"amount":"10.00","currency":"USD","description":"retry demo","webhook_url":"http://webhook-mock:8080/webhook/flaky/1"}'

# webhook всегда 500 → 3 попытки → DLQ
curl -X POST http://localhost:8000/api/v1/payments -H 'X-API-Key: dev-secret-key' \
  -H 'Idempotency-Key: fail-1' -H 'Content-Type: application/json' \
  -d '{"amount":"10.00","currency":"USD","description":"dlq demo","webhook_url":"http://webhook-mock:8080/webhook/fail"}'

make logs s=consumer   # docker compose logs -f consumer
make queues            # очереди и число сообщений
make dlq               # содержимое DLQ с заголовками x-attempt и x-last-error
```

Пример лога consumer для `flaky/1`:

```
INFO    Processing payment 55de88fc-… (attempt 1)
WARNING Attempt 1 failed (WebhookDeliveryError(reason='… returned HTTP 500')), retrying via payments.new.retry.2000ms
INFO    Processing payment 55de88fc-… (attempt 2)
INFO    Payment 55de88fc-… was already succeeded, webhook re-delivered
```

## Конфигурация

Переменные окружения (см. `.env.example` и `app/config.py`):

| Переменная | По умолчанию | Описание |
|---|---|---|
| `API_KEY` | — (обязательна) | Ключ для `X-API-Key` |
| `DATABASE_URL` | `postgresql+asyncpg://…` | Подключение к PostgreSQL |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Подключение к RabbitMQ |
| `GATEWAY_MIN_DELAY` / `GATEWAY_MAX_DELAY` | `2` / `5` | Задержка эмулятора шлюза, с |
| `GATEWAY_SUCCESS_RATE` | `0.9` | Доля успешных списаний |
| `RETRY_MAX_ATTEMPTS` | `3` | Всего попыток обработки сообщения |
| `RETRY_BASE_DELAY` | `2` | Базовая задержка retry, с (удваивается) |
| `WEBHOOK_TIMEOUT` | `5` | Таймаут запроса webhook, с |
| `OUTBOX_POLL_INTERVAL` | `1` | Пауза relay, когда событий нет, с |
| `OUTBOX_BATCH_SIZE` | `100` | Размер пачки relay |
| `CONSUMER_PREFETCH` | `10` | Prefetch consumer'а |

## Разработка и тесты

Частые команды собраны в `Makefile` (`make` без аргументов покажет список). Порты и API-ключ берутся из `.env`.

```bash
make env          # создать .env из .env.example
make install      # uv sync
make up           # собрать и запустить стек
make check        # ruff + mypy + unit-тесты
make test-e2e     # сквозные тесты против запущенного стека
make logs s=consumer
make queues       # очереди RabbitMQ;  make dlq — содержимое DLQ
make webhooks     # что получил webhook-mock
make revision m="add column"   # новая миграция (autogenerate)
make clean        # остановить стек и удалить тома
```

Unit-тесты используют in-memory fakes, которые повторяют контракт `UnitOfWork`: изменения видны только после `commit()`, а обращение к репозиторию вне транзакции — ошибка.

Сквозные тесты (`tests/e2e`) пропускаются, если не задан `E2E_API_URL`. Ключ API для них берётся из `E2E_API_KEY` (по умолчанию `dev-secret-key`). Платежи в них отправляют webhook на `webhook-mock`.

Без make:

```bash
uv sync
uv run ruff check . && uv run mypy app tools migrations tests
API_KEY=test uv run pytest tests/unit                                   # без инфраструктуры
E2E_API_URL=http://localhost:8000 uv run pytest tests/e2e               # против docker compose
```

## Принятые решения и отступления от ТЗ

- **`outbox-relay` и `webhook-mock` — дополнительные сервисы** в compose (тот же образ). Relay вынесен из API, чтобы API оставался stateless и масштабировался независимо. Mock нужен для демонстрации webhook, retry и DLQ.
- **`/health` без `X-API-Key`.** Это служебный эндпоинт для healthcheck. Все эндпоинты API (`/api/v1/*`) защищены.
- **«3 попытки»** трактуются как 3 попытки обработки всего (1 + 2 повтора), после чего сообщение уходит в DLQ. Значение настраивается.
- **Webhook доставляется at-least-once.** Получатель может отсекать дубли по заголовку `X-Payment-Id`.
