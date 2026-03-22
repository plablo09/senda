---
title: "Phase 3 LLM Student Guidance — pre-merge review cluster (async lifecycle, security, data integrity)"
category: "security-issues"
date: "2026-03-22"
tags:
  - async-lifecycle
  - fastapi
  - asyncsession
  - redis
  - litellm
  - xss-prevention
  - input-validation
  - session-management
  - concurrency-control
  - javascript
symptoms:
  - "Background DB logging silently fails — use-after-close on FastAPI request-scoped AsyncSession inside asyncio.create_task"
  - "LLM API calls hang indefinitely when Gemini is slow (no timeout set)"
  - "All students behind a school NAT share one rate-limit counter (IP fallback for session_id)"
  - "Feedback div renders nothing — getEditorValue() called with no args, editorContainer is undefined"
  - "Redis connection pool created and destroyed on every API request"
  - "User-controlled string injected directly into Redis key (colon injection risk)"
  - "innerHTML used for LLM output even though escapeHtml() edge cases could allow XSS"
  - "Rate-limit counter resets every time student closes a tab (sessionStorage)"
  - "referencia_concepto present in LLM prompt and schema but never returned to client"
  - "Unbounded concurrent LLM calls exhaust provider quota under class-size load"
  - "documento_id NOT NULL blocks logging when no document context exists"
components:
  - "api/routers/retroalimentacion.py"
  - "api/services/llm_feedback.py"
  - "api/services/feedback_rate_limiter.py"
  - "api/schemas/retroalimentacion.py"
  - "api/models/ejecucion_error.py"
  - "_extensions/senda/live/senda-live.js"
---

# Phase 3 LLM Student Guidance — pre-merge review cluster

A multi-agent code review before the Phase 3 PR identified 12 issues (5 critical, 6 high, 1 model). All were fixed in one commit. This document captures the root causes by cluster so the patterns are not repeated.

## Root Cause Analysis

The issues fell into five clusters, each caused by a boundary not enforced at implementation time.

### Cluster 1 — Async lifecycle: request-scoped resource crossing task boundary (C1)

FastAPI closes `AsyncSession` objects managed by `Depends(get_db)` when the route handler returns. Passing that session into `asyncio.create_task()` means the background task runs against an already-closed session.

```python
# ❌ Bad: db is closed before the task runs
asyncio.create_task(
    _log_error(
        db=db,           # FastAPI closes this on route return
        ejercicio_id=...,
    )
)
```

Fix: `_log_error` opens its own `AsyncSessionLocal()` session. The route handler passes only serialized data (strings), not the dependency-injected session.

```python
# ✅ Good: task is self-contained
async def _log_error(documento_id, ejercicio_id, session_id, error_tipo, error_output):
    try:
        async with AsyncSessionLocal() as db:
            db.add(EjecucionError(...))
            await db.commit()
    except Exception as exc:
        logger.warning("Error logging ejecucion_error: %s", exc)
```

**Rule:** Any function passed to `asyncio.create_task()` must own every resource it touches. Never pass a `db`, `request`, or `response` object through a task boundary.

---

### Cluster 2 — External API safety: no timeout, no concurrency cap (C2, H6)

`litellm.acompletion()` had no timeout. A slow Gemini response would hold an asyncio worker indefinitely. With no semaphore, 30 students submitting simultaneously would fire 30 concurrent LLM calls.

```python
# ❌ Bad
response = await litellm.acompletion(**kwargs)

# ✅ Good
_LLM_SEMAPHORE = asyncio.Semaphore(6)

async with _LLM_SEMAPHORE:
    response = await asyncio.wait_for(
        litellm.acompletion(**kwargs),
        timeout=15.0,
    )
```

The semaphore value (6) should be set based on provider rate limits and available workers.

---

### Cluster 3 — Redis: pool churn, key injection, missing TTL (H1, H2, H4)

Three separate Redis issues compounded each other:

**H1 — Per-request pool:** `aioredis.from_url()` creates a connection pool. Calling `aclose()` in `finally` destroys the entire pool, not just the connection. This means pool setup overhead on every API call.

```python
# ❌ Bad: creates and destroys pool per request
redis_client = aioredis.from_url(settings.redis_url)
try:
    ...
finally:
    await redis_client.aclose()

# ✅ Good: module-level lazy singleton
_redis_client: aioredis.Redis | None = None

def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url)
    return _redis_client
```

Tests: patch `api.services.feedback_rate_limiter._get_redis`, not `aioredis.from_url`. The `_make_redis_mock()` helper does not need `aclose` mocked since we no longer call it.

**H2 — Key injection:** `f"feedback:{session_id}:{ejercicio_id}"` inserts user-controlled strings literally. A session_id containing `:` corrupts the key structure.

```python
# ✅ Good: hash both components
import hashlib

def _make_key(session_id: str, ejercicio_id: str) -> str:
    sid = hashlib.sha256(session_id.encode()).hexdigest()[:32]
    eid = hashlib.sha256(ejercicio_id.encode()).hexdigest()[:16]
    return f"feedback:{sid}:{eid}"
```

Tests that assert the exact key string must be updated to use `ANY` for the key argument:
```python
from unittest.mock import ANY
redis_mock.hincrby.assert_called_once_with(ANY, "attempts_since_feedback", 1)
```

**H4 — No TTL:** Redis hashes with no `EXPIRE` accumulate forever. Add after every `hset`:
```python
await redis.expire(key, 7 * 86400)  # 7 days
```

---

### Cluster 4 — Session identity: IP fallback and tab-scoped storage (C4, H4 JS side)

`session_id or request.client.host` collapses every student behind a school's NAT onto the same rate-limit counter (the entire class gets one feedback budget). Fix: make `session_id` required in `FeedbackRequest`; the browser always generates one via `crypto.randomUUID()`.

`sessionStorage` resets when the student closes the tab — their rate-limit counter restarts. The rate-limit state is in Redis (server-side, TTL-bound); the browser UUID just needs to persist across tab reloads. Use `localStorage`.

```javascript
// ❌ Bad
let id = sessionStorage.getItem('senda_session_id');

// ✅ Good
let id = localStorage.getItem('senda_session_id');
```

**Decision guide:**
- `localStorage` — UUID, UI preferences, non-sensitive state that should survive tab close
- `sessionStorage` — truly ephemeral per-tab state (e.g., unsaved draft)
- Neither — anything sensitive (tokens, keys); use httpOnly cookies

---

### Cluster 5 — JavaScript: closure bug and innerHTML XSS (C5, H3)

**C5 — Closure bug:** `getEditorValue` requires an `editorDiv` argument, but `editorDiv` is not in scope inside `ejecutarCodigo`. Passing the bare function reference means `getCode()` is called with no args → `editorContainer` is `undefined` → `getEditorValue` returns `''`.

```javascript
// ❌ Bad: getEditorValue not in scope of ejecutarCodigo
solicitarRetroalimentacion(exerciseId, contenido, getEditorValue, feedbackDiv);

// ✅ Good: code is already captured as a local variable in ejecutarCodigo
solicitarRetroalimentacion(exerciseId, contenido, () => code, feedbackDiv);
```

Rule: when passing a callback that needs a variable from the calling scope, always wrap in an arrow function or `.bind()`. Bare function references only work if the function is self-contained.

**H3 — innerHTML XSS:** Even with `escapeHtml()`, `innerHTML` assignment is risky — edge cases in the escape function or future changes to what gets inserted can reintroduce XSS. Use DOM API throughout.

```javascript
// ❌ Bad (still risky even with escapeHtml)
feedbackDiv.innerHTML = `<strong>Retroalimentación:</strong> ${escapeHtml(data.retroalimentacion)}`;

// ✅ Good: DOM API, no parsing
feedbackDiv.replaceChildren();
const label = document.createElement('strong');
label.textContent = 'Retroalimentación: ';
feedbackDiv.appendChild(label);
feedbackDiv.appendChild(document.createTextNode(data.retroalimentacion));
```

---

### Cluster 6 — Schema gaps: payload limits, missing field, nullable mismatch (C3, H5, M1)

**C3:** String fields from user input had no `max_length`. In Pydantic v2, add `Field(max_length=N)`.

```python
class FeedbackRequest(BaseModel):
    codigo_estudiante: str = Field(max_length=10000)
    error_output: str = Field(max_length=5000)
    session_id: str  # required — no default
```

**H5:** `referencia_concepto` existed in the LLM system prompt and the response JSON schema but was never extracted from `data` or added to `FeedbackResponse`. Trace every field from LLM prompt through the return type to the API response.

```python
# Return type updated: tuple[str, str | None, bool, str | None]
referencia_concepto = data.get("referencia_concepto")
return diagnostico, pregunta_guia, mostrar_pista, referencia_concepto
```

**M1:** `documento_id` was `nullable=False` but no document context exists at the feedback router layer. If a column can legitimately be absent at the point of insertion, it must be nullable.

---

## Prevention Strategies

### Before writing any `asyncio.create_task()`

- [ ] Does the function receive any FastAPI dependency (`AsyncSession`, `Request`, `Response`)? If yes: make it self-contained instead.
- [ ] Does the task have a timeout on every external call?
- [ ] Does the task have a top-level `try/except` with `logger.warning`?
- [ ] Is there an integration test that verifies the task works *after* the route handler returns?

### Before integrating any external API (LLM, payment, storage)

- [ ] Every `await external_call(...)` is wrapped in `asyncio.wait_for(..., timeout=N)`
- [ ] A module-level `asyncio.Semaphore(N)` caps concurrent calls; N is documented
- [ ] Every field in the API response is traced to a return statement or logged
- [ ] Input fields sent to the API have `max_length`/`max_tokens` constraints at the Pydantic layer
- [ ] Fallback behavior is defined for timeout and API error cases

### Redis key design

- [ ] No user-controlled value appears raw in a key name — hash it
- [ ] Every key that grows unbounded has an `EXPIRE` / TTL
- [ ] The Redis client is a module-level singleton, not created per request
- [ ] Tests patch the client accessor (`_get_redis`), not `aioredis.from_url`

### JavaScript

- [ ] `localStorage` vs `sessionStorage` choice is documented in a comment
- [ ] `innerHTML` is banned for any content that includes server or user data — use DOM API
- [ ] Callbacks passed to other functions are arrow functions if they need outer-scope variables
- [ ] Every `() => someVar` closure: verify `someVar` is in scope at the time the callback fires

### Pre-PR triggers — request extra review if any of these appear

- `asyncio.create_task(f(db=...))` — async task receiving a dependency-injected resource
- `await some_client.method(...)` without `asyncio.wait_for` or `timeout=` kwarg
- `f"prefix:{user_input}"` used as a Redis, cache, or storage key
- `element.innerHTML =` where the RHS is not a hardcoded string literal
- `sessionStorage` used for a UUID or identity token
- `Field(...)` missing on a user-supplied string field in a Pydantic model

---

## Related Documents

- [`docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md`](../runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md) — FastAPI async pitfalls discovered during Phase 2/3 implementation; Pitfall 2 covers `asyncio.to_thread` for sync calls; Pitfall 5 covers input sanitization guards
- [`docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md`](fastapi-upload-qmd-websocket-security-cluster.md) — Phase 2 security cluster; covers async boto3 blocking, iframe XSS, Redis pub/sub ordering, WebSocket races. Note: the "Fixes pending" status in that document now refers to work completed in Phase 3.
- [`docs/solutions/integration-issues/blocknote-047-typescript-integration-pitfalls.md`](../integration-issues/blocknote-047-typescript-integration-pitfalls.md) — Pitfall 6 covers closure/state management patterns in async JavaScript; relevant to C5

## PR Reference

[PR #3 — feat(phase-3): LLM Student Guidance](https://github.com/plablo09/senda/pull/3)
Commit: `fix(security): address 12 review findings before merge`
