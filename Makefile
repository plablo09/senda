.PHONY: up down build test test-int lint fmt fmt-check shell-api shell-db logs logs-llm smoke-test

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
	docker compose run --rm -e PYTHONPATH=/app api pytest tests/unit/ -v

test-int:
	docker compose run --rm -e PYTHONPATH=/app api pytest tests/integration/ -v

smoke-test: up-d
	sleep 5
	docker compose run --rm api pytest tests/integration/ -v
	docker compose down

# ── Linting & Formatting ──────────────────────────────────────────────────────

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm api black --check .

fmt:
	docker compose run --rm api ruff check --fix .
	docker compose run --rm api black .

fmt-check:
	docker compose run --rm api ruff check .
	docker compose run --rm api black --check .

# ── Utilities ─────────────────────────────────────────────────────────────────

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec db psql -U senda senda

logs:
	docker compose logs -f api worker

logs-llm:
	docker compose logs -f ollama
