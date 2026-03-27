---
status: pending
priority: p3
issue_id: "046"
tags: [code-review, type-safety, render-task]
dependencies: []
---

# Type `_publish_render_status` `status` Parameter as `EstadoRender`

## Problem Statement

`api/tasks/render_task.py:18` defines `_publish_render_status(documento_id: str, status: str, ...)`. The `status` parameter accepts any string, but it should only accept the four values in `EstadoRender = Literal["pendiente", "procesando", "listo", "fallido"]`. The Literal type already exists in `api/schemas/documento.py`. A typo like `"fallado"` would be silently published to Redis and cause downstream listeners to receive an unknown state.

## Findings

- `api/tasks/render_task.py:18` — `status: str` — untyped, accepts any string
- `api/schemas/documento.py:10` — `EstadoRender = Literal["pendiente", "procesando", "listo", "fallido"]` — already defined
- All callers of `_publish_render_status` in the file use string literals — a type annotation would catch any future typos at check time
- Confirmed by: kieran-python-reviewer (medium)

## Proposed Solutions

### Option 1: Import and use `EstadoRender` (Recommended)

Add `from api.schemas.documento import EstadoRender` to `render_task.py` and change the signature to `status: EstadoRender`.

**Effort:** 5 minutes
**Risk:** None

## Technical Details

**Affected files:**
- `api/tasks/render_task.py:18` — change `status: str` to `status: EstadoRender`
- `api/tasks/render_task.py` — add import of `EstadoRender`

## Acceptance Criteria

- [ ] `_publish_render_status` uses `status: EstadoRender`
- [ ] `EstadoRender` imported from `api.schemas.documento`
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
