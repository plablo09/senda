---
status: complete
priority: p1
issue_id: "001"
tags: [code-review, python, celery, imports]
dependencies: []
---

# Worker startup crash: import path inconsistency + wrong task symbol name

## Problem Statement

Two related bugs that together completely disable the render pipeline:

1. `celery_app.py` uses bare module imports (`from config import settings`, `include=["tasks.render_task"]`) while every other file uses `from api.X import ...`. The Dockerfile.worker CMD is `celery -A api.celery_app` — running from repo root where `api` is a package. The bare `from config import settings` raises `ModuleNotFoundError` at worker startup.

2. `documentos.py` does `from api.tasks.render_task import render_task` but the actual Celery task is named `render_documento` (decorated with `@celery_app.task`). The try/except silently sets `render_task = None`, so **renders are never dispatched** — no error, no log, just silent no-ops forever.

## Findings

- `api/celery_app.py:3` — `from config import settings` (bare, incompatible with `api.*` package layout)
- `api/celery_app.py:9` — `include=["tasks.render_task"]` (should be `["api.tasks.render_task"]`)
- `api/celery_app.py:21` — `"task": "tasks.render_task.cleanup_stale_containers"` (should be `api.tasks.*`)
- `api/tasks/render_task.py:3` — `from celery_app import celery_app` (bare)
- `api/tasks/render_task.py:11-16` — all inner imports are bare (`from database import ...`, etc.)
- `api/routers/documentos.py:14-17` — imports `render_task` symbol that doesn't exist; try/except hides it
- `api/routers/documentos.py:79` — calls `render_task.delay(...)` which is always `None`

## Proposed Solutions

### Option A: Fix all imports to use `api.*` prefix (recommended)
Update `celery_app.py` and `render_task.py` to use `from api.config import settings`, `include=["api.tasks.render_task"]`, etc. The Dockerfile.worker CMD `celery -A api.celery_app` is already correct.

Fix the symbol name in `documentos.py`: `from api.tasks.render_task import render_documento` and call `render_documento.delay(str(doc.id))`.

Remove the try/except wrapper — if this import fails it's a hard misconfiguration, not graceful degradation.

- **Pros:** Consistent with rest of codebase; no PYTHONPATH tricks needed
- **Cons:** Minor — none
- **Effort:** Small
- **Risk:** Low

### Option B: Use PYTHONPATH=/app/api and keep bare imports
Set `PYTHONPATH=/app/api` in Dockerfile.worker ENV and document the divergence.

- **Pros:** No import changes needed
- **Cons:** Inconsistent, confusing, fragile
- **Effort:** Small
- **Risk:** Medium (confusion for future contributors)

## Recommended Action

Option A.

## Technical Details

- **Affected files:** `api/celery_app.py`, `api/tasks/render_task.py`, `api/routers/documentos.py`
- **Verified:** render pipeline has been silently disabled since the first commit

## Acceptance Criteria

- [ ] `docker compose logs worker` shows Celery startup with no `ModuleNotFoundError`
- [ ] Creating a document via `POST /documentos` with an AST triggers the render task (visible in `docker compose logs worker`)
- [ ] `render_documento.delay()` is called in `documentos.py`, not `render_task.delay()`
- [ ] All imports in `celery_app.py` and `render_task.py` use `api.*` prefix

## Work Log

- 2026-03-20: Identified by kieran-python-reviewer and architecture-strategist
- 2026-03-20: Fixed — `celery_app.py` and `render_task.py` updated to `api.*` imports; `documentos.py` try/except removed, symbol corrected to `render_documento`. Verified: task received and executed, estado_render transitions correctly.
