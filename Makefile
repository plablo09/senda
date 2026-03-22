.PHONY: up down build test test-int lint fmt shell-api shell-db logs logs-llm smoke-test migrate migrate-down revision migrate-check migrate-current

# ── Stack ─────────────────────────────────────────────────────────────────────

up:
	docker compose up --build

up-d:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	docker compose run --rm -e PYTHONPATH=/app api pytest api/tests/unit/ -v

test-int:
	docker compose run --rm -e PYTHONPATH=/app api pytest api/tests/integration/ -v

smoke-test: up-d
	sleep 5
	docker compose run --rm -e PYTHONPATH=/app api pytest api/tests/integration/ -v
	docker compose down

# ── Linting & Formatting ──────────────────────────────────────────────────────

lint:
	docker compose run --rm api ruff check api/
	docker compose run --rm api black --check api/

fmt:
	docker compose run --rm api ruff check --fix api/
	docker compose run --rm api black api/

# ── Utilities ─────────────────────────────────────────────────────────────────

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec db psql -U senda senda

logs:
	docker compose logs -f api worker

logs-llm:
	docker compose logs -f ollama

# ── Migrations ────────────────────────────────────────────────────────────────

migrate:
	docker compose run --rm migrator

migrate-down:
	docker compose run --rm -e PYTHONPATH=/app api alembic downgrade -1

migrate-check:
	docker compose run --rm -e PYTHONPATH=/app api alembic check

migrate-current:
	docker compose run --rm -e PYTHONPATH=/app api alembic current

revision:
	docker compose run --rm -e PYTHONPATH=/app api alembic revision --autogenerate -m "$(MSG)"
