---
review_agents:
  - compound-engineering:review:kieran-python-reviewer
  - compound-engineering:review:security-sentinel
  - compound-engineering:review:performance-oracle
  - compound-engineering:review:architecture-strategist
  - compound-engineering:review:code-simplicity-reviewer
---

## Project Review Context

Senda is a greenfield FastAPI + Celery + PostgreSQL application for interactive geographic/statistical education.

Key conventions:
- Python 3.12, FastAPI async, SQLAlchemy 2.0 async (asyncpg)
- UI strings must be in Spanish; code and doc strings in English
- Docker-based server-side code execution (no WASM/Pyodide)
- Celery + Redis for async render pipeline
- LiteLLM abstraction for LLM provider (Ollama locally)
- All execution containers run as non-root user `estudiante`
- Phase 2 auth is implemented on feat/phase-2-authentication (JWT cookies, registro/login/logout/refresh, Usuario + SesionRefresh models)
