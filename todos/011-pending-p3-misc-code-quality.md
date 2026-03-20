---
status: pending
priority: p3
issue_id: "011"
tags: [code-review, python, quality, types]
dependencies: [001]
---

# Misc code quality: datetime.utcnow, type hints, imports, hardcoded version

## Problem Statement

A collection of small issues flagged by multiple reviewers that are easy to fix in one pass.

## Findings

### 1. datetime.utcnow deprecated in Python 3.12
- `api/models/documento.py:26,31,33` — `default=datetime.utcnow`, `onupdate=datetime.utcnow`
- Fix: `from datetime import UTC` and use `datetime.now(UTC)` or `server_default=func.now()`

### 2. ensure_bucket_exists() swallows all exceptions with bare except
- `api/services/storage.py:19-22` — catches all exceptions including network/auth failures
- Fix: catch only `botocore.exceptions.ClientError` and check `error["Code"] in ("404", "NoSuchBucket")`

### 3. Missing type hints on public functions
- `api/services/qmd_serializer.py:7,19,23,46` — all four public functions
- `api/services/storage.py:6,16,24` — `get_s3_client()`, `ensure_bucket_exists()`, `upload_html()`

### 4. import shutil inside function body
- `api/services/renderer.py:21` — move to module-level imports

### 5. Double asyncio import in render_task.py
- `api/tasks/render_task.py:2,10` — `import asyncio` at module level AND inside function

### 6. Imports inside inner function (_run)
- `api/tasks/render_task.py:11-16` — all DB/service imports inside `_run()`, invisible to static analysis
- Fix: move to module top-level after fixing import paths (todo 001)

### 7. Hardcoded version in health endpoint
- `api/routers/health.py:10` — `"version": "0.1.0"` will drift from pyproject.toml
- Fix: `from importlib.metadata import version; version("senda-api")`

### 8. OutputChunk.tipo should be Literal type
- `api/services/execution_pool.py:13` — `tipo: str` should be `Literal["stdout","stderr","imagen","error","fin"]`

### 9. create_tables on every startup conflicts with Alembic
- `api/main.py:17-18` — `Base.metadata.create_all()` on every startup is dev-only
- Fix: gate behind `settings.auto_create_tables: bool = True` (default True for dev, False for prod)

### 10. DocumentoUpdate PUT accepts empty body
- `api/schemas/documento.py:14-16` + `api/routers/documentos.py:54-81`
- Fix: validate that at least one field is non-None, or rename to PATCH

### 11. Default secret_key is a committed plaintext value
- `api/config.py:16` — `secret_key: str = "dev-secret-change-in-production"`
- Fix: raise `ValueError` at startup if value matches the known-unsafe default and `ENV != "development"`

## Proposed Solutions

Single PR fixing all of the above in one pass — they're all mechanical changes.

## Acceptance Criteria

- [ ] `datetime.now(UTC)` used everywhere (no DeprecationWarning on Python 3.12)
- [ ] `ensure_bucket_exists()` raises on non-404 storage errors
- [ ] All public functions in qmd_serializer.py and storage.py have type hints
- [ ] `import shutil` at module level in renderer.py
- [ ] Single `import asyncio` at top of render_task.py
- [ ] Health endpoint reads version from package metadata
- [ ] `OutputChunk.tipo` is `Literal[...]`
- [ ] PUT /documentos/{id} with `{}` body returns 422 Unprocessable Entity

## Work Log

- 2026-03-20: Identified by kieran-python-reviewer (P1-4, P1-5, P2-7, P2-8, P2-9, P3-1 through P3-5), code-simplicity-reviewer
