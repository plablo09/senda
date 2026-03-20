# Senda — Agent & Developer Guidelines

## Project Overview

Senda is an interactive geographic and statistical education platform. Teachers create
Quarto-based lessons through a block editor; students run Python/R code server-side
(geopandas, sf, GDAL) in isolated Docker containers.

## Language Rules

- **User-facing UI (teacher and student)**: Spanish. All labels, buttons, error messages,
  toast notifications, and form fields must be in Spanish.
- **Code, comments, commit messages, documentation**: English.
- **API route names**: Spanish nouns (e.g., `/documentos`, `/retroalimentacion`, `/ejecutar`).

## Repository Structure

```
api/           FastAPI backend + Celery workers
frontend/      React + Vite teacher web app (Spanish UI)
_extensions/   Custom Quarto extension (senda-live)
docker/        Dockerfiles for all services
nginx/         Nginx config (dev + prod)
docs/plans/    Architecture plans
```

## Branch Naming

- `feat/<description>` — new features
- `fix/<description>` — bug fixes
- `refactor/<description>` — refactoring
- `chore/<description>` — tooling/infra

## Common Commands

```bash
make up          # Start full docker-compose stack
make down        # Stop stack
make test        # Run unit tests (no Docker needed)
make test-int    # Run integration tests (needs docker compose up)
make lint        # Lint Python + TypeScript
make fmt         # Auto-format Python + TypeScript
make shell-api   # Bash shell in api container
make shell-db    # psql shell
make logs        # Follow api + worker logs
```

## LLM Configuration

The feedback service uses LiteLLM. Set these env vars to switch providers:

| Variable | Local default | Example (production) |
|---|---|---|
| `LLM_MODEL` | `ollama/llama3.2` | `anthropic/claude-haiku-4-5-20251001` |
| `LLM_API_BASE` | `http://ollama:11434` | (empty) |
| `LLM_API_KEY` | (empty) | `sk-ant-...` |

Supported providers: Ollama, Anthropic, OpenAI, Groq, Gemini, Azure. See LiteLLM docs.

## Testing Strategy

- **Unit tests** (`api/tests/unit/`): pure functions only, no Docker, run fast with pytest
- **Integration tests** (`api/tests/integration/`): need full docker-compose stack running
- `qmd_serializer.py` is TDD — write tests first

## Key Architectural Constraints

- The deployment target only needs Docker + Docker Compose. No Python/R/Node/Quarto on the host.
- GDAL, geopandas, sf run inside Docker containers — never install them on the host.
- API keys must never appear in rendered student HTML.
- All user-facing text must be in Spanish.
- `.qmd` files are always derived from the JSON AST — never edit them directly.
