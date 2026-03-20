---
status: complete
priority: p1
issue_id: "003"
tags: [code-review, python, celery, sqlalchemy, correctness]
dependencies: [001]
---

# render_documento: retry fires after finally-commit marks document as "fallido"

## Problem Statement

`render_documento` calls `raise self.retry(exc=exc)` inside `except Exception`, but the `finally` block runs immediately after, committing `estado_render = "fallido"` and `error_render = ...` to the database **before Celery re-enqueues the task**. On the retry, the task fetches the document and finds it already marked `"fallido"`, then immediately overwrites it with `"procesando"` — but the final state after all retries is that the document is marked `"fallido"` from the first failure, not the last.

More critically: the retry mechanism is broken because it signals "try again" but has already written the terminal failure state.

## Findings

```python
# api/tasks/render_task.py:46-56
except Exception as exc:
    doc.estado_render = "fallido"      # ← writes terminal state
    doc.error_render = f"Error inesperado: {exc}"
    raise self.retry(exc=exc)          # ← then asks Celery to retry
finally:
    await session.commit()             # ← commits "fallido" before retry runs
```

## Proposed Solutions

### Option A: Separate transient from terminal failure (recommended)
Distinguish between retryable and terminal failures. On `self.retry()`, do NOT commit the failed state — let the task restart fresh. Only commit `"fallido"` when retries are exhausted.

```python
except RenderError as exc:
    # Permanent failure — commit terminal state
    doc.estado_render = "fallido"
    doc.error_render = str(exc)
    await session.commit()
except Exception as exc:
    # Transient failure — reset to "pendiente" so retry starts clean
    doc.estado_render = "pendiente"
    doc.error_render = None
    await session.commit()
    raise self.retry(exc=exc)
```

Use `bind=True` with `self.request.retries` to write `"fallido"` only when `self.request.retries >= self.max_retries`.

- **Pros:** State machine is correct; retries actually retry
- **Cons:** Requires careful handling of `max_retries` check
- **Effort:** Small
- **Risk:** Low

### Option B: Remove retries for Phase 1
Set `max_retries=0` (or remove `bind=True`). Render failures always write `"fallido"`. Retries can be added when the task is more mature.

- **Pros:** Eliminates the broken retry logic entirely
- **Cons:** No retry on transient failures (DB flap, MinIO timeout)
- **Effort:** Tiny
- **Risk:** Low

## Recommended Action

Option A — correct state machine is worth the small extra code.

## Technical Details

- **Affected files:** `api/tasks/render_task.py:46-56`

## Acceptance Criteria

- [ ] A document that fails on attempt 1 and succeeds on attempt 2 ends up with `estado_render = "listo"`
- [ ] A document that fails all retries ends up with `estado_render = "fallido"` and a populated `error_render`
- [ ] `estado_render` is never `"fallido"` while a retry is still pending

## Work Log

- 2026-03-20: Identified by kieran-python-reviewer (P1-2) and performance-oracle (P2-B)
