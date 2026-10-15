# Порты и ключ берутся из .env (если он есть), иначе значения по умолчанию.
-include .env

API_PORT ?= 8000
API_KEY ?= dev-secret-key
RABBITMQ_MANAGEMENT_PORT ?= 15672
WEBHOOK_MOCK_PORT ?= 8090

COMPOSE := docker compose
APP_DIRS := app tools migrations tests

.DEFAULT_GOAL := help
.PHONY: help env install lint format typecheck check test test-unit test-e2e \
        up down restart rebuild ps logs migrate revision downgrade \
        queues dlq webhooks clean

help: ## Показать список команд
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# --- Разработка ---

env: ## Создать .env из .env.example (если его ещё нет)
	@test -f .env && echo ".env уже существует" || (cp .env.example .env && echo ".env создан")

install: ## Установить зависимости (uv)
	uv sync

lint: ## Проверить код ruff (линтер + форматирование)
	uv run ruff check .
	uv run ruff format --check .

format: ## Отформатировать код и исправить автоисправимое
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Проверить типы mypy
	uv run mypy $(APP_DIRS)

check: lint typecheck test-unit ## Линтер, типы и unit-тесты

test: test-unit test-e2e ## Все тесты (e2e требуют запущенного стека)

test-unit: ## Unit-тесты (без инфраструктуры)
	API_KEY=test uv run pytest tests/unit

test-e2e: ## Сквозные тесты против запущенного docker compose
	API_KEY=$(API_KEY) E2E_API_KEY=$(API_KEY) E2E_API_URL=http://localhost:$(API_PORT) uv run pytest tests/e2e

# --- Docker ---

up: ## Собрать и запустить все сервисы
	$(COMPOSE) up -d --build

down: ## Остановить сервисы
	$(COMPOSE) down

restart: ## Перезапустить сервисы приложения без пересборки
	$(COMPOSE) restart api outbox-relay consumer

rebuild: ## Пересобрать образ и перезапустить сервисы приложения
	$(COMPOSE) up -d --build api outbox-relay consumer webhook-mock

ps: ## Состояние сервисов
	$(COMPOSE) ps -a

logs: ## Логи сервисов приложения (make logs s=consumer — одного сервиса)
	$(COMPOSE) logs -f --tail 100 $(or $(s),api outbox-relay consumer)

clean: ## Остановить сервисы и удалить тома (БД и очереди)
	$(COMPOSE) down -v

# --- Миграции ---

migrate: ## Применить миграции
	$(COMPOSE) run --rm migrations alembic upgrade head

revision: ## Создать миграцию: make revision m="add column"
	@test -n "$(m)" || (echo "Укажите описание: make revision m=\"...\"" && exit 1)
	$(COMPOSE) run --rm --user $(shell id -u):$(shell id -g) -v $(CURDIR)/migrations:/srv/migrations \
	  migrations alembic revision --autogenerate -m "$(m)"

downgrade: ## Откатить последнюю миграцию
	$(COMPOSE) run --rm migrations alembic downgrade -1

# --- Диагностика ---

queues: ## Очереди RabbitMQ и число сообщений в них
	$(COMPOSE) exec rabbitmq rabbitmqctl list_queues name messages consumers

dlq: ## Сообщения в DLQ (без извлечения)
	@curl -s -u guest:guest -H "content-type: application/json" \
	  -d '{"count":50,"ackmode":"ack_requeue_true","encoding":"auto"}' \
	  http://localhost:$(RABBITMQ_MANAGEMENT_PORT)/api/queues/%2F/payments.new.dlq/get \
	  | python3 -m json.tool

webhooks: ## Webhook, полученные webhook-mock
	@curl -s http://localhost:$(WEBHOOK_MOCK_PORT)/received | python3 -m json.tool
