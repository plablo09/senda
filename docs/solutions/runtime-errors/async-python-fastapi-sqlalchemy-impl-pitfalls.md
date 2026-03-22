---
title: "Implementation Pitfalls Discovered During Phase 2 Security Fixes"
category: runtime-errors
date: 2026-03-21
tags:
  - sqlalchemy
  - asyncio
  - fastapi
  - websocket
  - python
  - datetime
  - testing
  - qmd
  - storage
problem_type: silent_failure
components:
  - api/models/documento.py
  - api/models/dataset.py
  - api/routers/datasets.py
  - api/ws/render_status.py
  - api/services/qmd_serializer.py
  - api/tests/unit/test_qmd_serializer.py
---

# Implementation Pitfalls Discovered During Phase 2 Security Fixes

Five non-obvious traps hit while applying the Phase 2 security fixes (commit `8acee72`). These are not the original security issues — those are documented in `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md`. These are the **implementation-time surprises**: code that looks correct, compiles cleanly, passes type checking, and may even pass tests — but is subtly wrong at runtime.

---

## Pitfall 1 — SQLAlchemy `default=` evaluates at import time if given a value, not a callable

**Severity:** Silent data corruption — no error, no warning, wrong timestamps on every row.

### The trap

Replacing the deprecated `datetime.utcnow` (no parens) with `datetime.now(UTC)` (requires parens because `now()` needs a `tz` argument) looks like a mechanical substitution. It is not.

`datetime.utcnow` without parens is a **method reference** — SQLAlchemy calls it per row-insert.
`datetime.now(UTC)` with parens is a **datetime value** — evaluated once at class definition time, frozen forever.

```python
# Wrong 1 — deprecated, produces naive datetimes:
created_at = mapped_column(DateTime, default=datetime.utcnow)

# Wrong 2 — compiles fine, type-checks fine, silently wrong:
# evaluates ONCE at module import; every row gets the same timestamp
created_at = mapped_column(DateTime(timezone=True), default=datetime.now(UTC))

# Correct — lambda makes it a callable; called fresh per row-insert:
created_at = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
updated_at = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC),
    onupdate=lambda: datetime.now(UTC),
)
```

### Detection

```bash
# Any default= with datetime.now() directly (no lambda) — frozen value:
grep -rn "default=datetime\.now\b" --include="*.py"

# Also catch other frozen-value defaults (uuid4(), etc.):
grep -rn "default=[a-zA-Z_]*\.[a-zA-Z_]*(" --include="*.py" | grep -v "lambda"
```

### Test strategy

Insert two rows in separate statements and assert their `created_at` values differ:

```python
row1 = MyModel(); session.add(row1); session.flush()
row2 = MyModel(); session.add(row2); session.flush()
assert row1.created_at != row2.created_at  # fails immediately if default is frozen
```

### Rule of thumb

If it has parentheses after it in the `default=` slot, it has already been called — wrap in a lambda or remove the parens.

---

## Pitfall 2 — `asyncio.to_thread()` is cleaner than `run_in_executor` for Python 3.9+

### The context

When wrapping sync boto3 calls (Issue 1 in the security cluster doc), the plan documentation showed `loop.run_in_executor(None, func, *args)`. In practice, Python 3.9+ provides a simpler API.

```python
# Old pattern — requires obtaining the event loop first:
loop = asyncio.get_event_loop()
url = await loop.run_in_executor(None, upload_dataset, dataset_id, filename, content, mimetype)

# Python 3.9+ — args passed directly, no loop reference needed:
url = await asyncio.to_thread(upload_dataset, dataset_id, filename, content, mimetype)

# For keyword args, use functools.partial:
import functools
await asyncio.to_thread(functools.partial(some_func, key=value))
```

`asyncio.to_thread` uses `asyncio.get_running_loop()` internally — always the correct running loop, never a stale or wrong loop reference.

**Important distinction:** Celery workers run in a synchronous context. Call sync boto3 directly from Celery tasks. Only async FastAPI route handlers need the thread wrapper.

### Detection

```bash
grep -rn "run_in_executor" --include="*.py"
grep -rn "get_event_loop\(\)" --include="*.py"
```

### Rule of thumb

Reach for `asyncio.to_thread(fn, *args)` first; only use `run_in_executor` when you need a custom executor (e.g., `ProcessPoolExecutor`).

---

## Pitfall 3 — FastAPI WebSocket UUID path params: validate at the boundary, stringify immediately

### The mechanism

FastAPI validates WebSocket path parameters using the same type coercion as HTTP routes. Declaring `documento_id: uuid.UUID` causes FastAPI to reject malformed values before the handler body runs — identical to HTTP path params.

The trap: the `uuid.UUID` object that arrives in the handler body should be converted to `str` on the first line. Using it directly in f-strings technically works (UUID's `__str__` returns the standard format), but it's fragile: any API that expects `bytes` or a plain `str` (e.g., Redis `subscribe`) will raise a confusing type error without a clear call stack.

```python
# Fragile — UUID object used in string ops without explicit cast:
@router.websocket("/ws/documentos/{documento_id}/estado")
async def render_status(websocket: WebSocket, documento_id: uuid.UUID):
    await pubsub.subscribe(f"render:{documento_id}")     # works by accident
    await pubsub.unsubscribe(f"render:{documento_id}")   # str() scattered

# Correct — capture str once, use everywhere:
@router.websocket("/ws/documentos/{documento_id}/estado")
async def render_status(websocket: WebSocket, documento_id: uuid.UUID):
    doc_id = str(documento_id)   # UUID validation already done by FastAPI
    await pubsub.subscribe(f"render:{doc_id}")
    # ... use doc_id throughout the handler
    await pubsub.unsubscribe(f"render:{doc_id}")
```

### Detection

```bash
# UUID-typed param used in string operation without explicit str() cast:
grep -n ": uuid.UUID" --include="*.py" -r -A10 | grep -v "str(" | grep "f\""
```

### Rule of thumb

FastAPI validates UUIDs for free; it does not stringify them for free. Pin `x = str(uuid_param)` on the first line of every UUID-param handler.

---

## Pitfall 4 — Test assertions on fence delimiter syntax break when the delimiter changes

### What happened

Switching QMD exercise code fences from backticks (` ``` `) to tildes (`~~~~~`) — to prevent user-authored code from closing the fence — broke 8 test assertions that checked for the exact string ` ```{python} `. The fix required:

1. Bulk `sed` to update all exercise-related assertions (`\`\`\`` → `~~~~~`)
2. A targeted revert for `TestSerializeCargadorDatos` (that serializer generates server-controlled code, not user content, so it intentionally kept backtick fences)

The root cause: tests asserted implementation-detail syntax (which fence character) rather than semantic outcome (is the right code present with the right language tag?).

```python
# Brittle — breaks if fence style changes for any reason:
assert "```{python}" in result
assert result.count("```{python}") == 2

# Resilient — asserts semantic outcome:
assert "{python}" in result          # language marker present
assert "x = ____" in result          # user code included
assert result.count("{python}") == 2 # correct block count

# If the delimiter itself IS the spec (e.g., tilde fences required for security),
# document it explicitly and add a comment:
assert "~~~~~{python}" in result, "Must use tilde fences (user code cannot close them)"
```

### The asymmetry to preserve

Two serializers intentionally use different fence characters after the fix:
- `serialize_exercise` — tilde fences (`~~~~~`) because starter/solution code is user-authored
- `serialize_cargador_datos` — backtick fences (` ``` `) because the data-loading code is server-generated

If you bulk-update test assertions in one direction, `cargadorDatos` tests will wrongly fail. The distinction is semantic and must be tracked in both the implementation and the tests.

See `api/tests/unit/test_qmd_serializer.py`:
- Lines 132–191: exercise assertions → `~~~~~{python}`
- Lines 482–487: cargadorDatos assertions → ` ```{python} ` / ` ```{r} `

### Rule of thumb

Test what the output means, not which character it starts with — unless the delimiter is the security spec, in which case document that constraint explicitly in the test assertion comment.

---

## Pitfall 5 — `startswith` guard before URL prefix stripping converts silent wrong-key into an observable warning

### The silent failure mode

```python
# Before — looks correct at a glance; silently wrong if URL doesn't match:
prefix = f"{settings.storage_public_endpoint}/{settings.storage_bucket}/"
key = dataset.url[len(prefix):]   # returns full URL if prefix doesn't match
try:
    delete_object(key)
except Exception:
    pass  # swallows all evidence
```

If `storage_public_endpoint` changes between write (row created) and delete (row removed) — for example, during a dev-to-staging migration — `key` is the full URL string. `delete_object` fails or deletes nothing, the exception is swallowed, and no log entry exists. The MinIO object leaks silently.

### The fix pattern

```python
# After — `startswith` guard makes the mismatch observable:
prefix = f"{settings.storage_public_endpoint}/{settings.storage_bucket}/"
if dataset.url.startswith(prefix):
    key = dataset.url[len(prefix):]
    try:
        await asyncio.to_thread(delete_object, key)
    except Exception:
        logger.warning(
            "Storage delete failed (id=%s, key=%s)", dataset_id, key, exc_info=True
        )
else:
    logger.warning(
        "URL prefix mismatch; skipping delete (id=%s, url=%s)", dataset_id, dataset.url
    )
```

The `startswith` guard converts a silent data-loss bug into a logged warning diagnosable from log output alone — no debugger, no tracing required.

### Detection

```bash
# Slice/strip operations without a preceding guard:
grep -rn "\[len(.*prefix.*)\:\]" --include="*.py"
grep -rn "\.removeprefix(" --include="*.py"
```

### Test strategy

Add a negative-path unit test for every prefix-stripping function:

```python
def test_url_prefix_mismatch_logs_warning(caplog):
    # URL stored with old endpoint, settings now have new endpoint
    dataset.url = "http://old-host:9000/bucket/datasets/abc/file.csv"
    # settings.storage_public_endpoint = "http://new-host:9000"
    with caplog.at_level(logging.WARNING):
        await eliminar_dataset(dataset.id, db)
    assert "URL prefix mismatch" in caplog.text
    assert "skipping delete" in caplog.text
```

### Rule of thumb

Strip only what you've confirmed is there — `assert s.startswith(prefix)` or `if not s.startswith(prefix): warn(...)` before every `removeprefix` / `[len(prefix):]`.

---

## Prevention Checklist

- [ ] Every `mapped_column(..., default=...)` uses a callable reference or a `lambda`, never a pre-evaluated expression with `()`
- [ ] Sync I/O in async routes uses `asyncio.to_thread()` (Python 3.9+); `run_in_executor` only when a custom executor is needed
- [ ] UUID-typed path params captured as `str` on the first line of the handler body
- [ ] QMD/Quarto test assertions assert semantic properties (language tag, code content, block count), not fence delimiter characters — unless the delimiter is the security spec, in which case the assertion has an explanatory comment
- [ ] Every URL prefix strip is preceded by a `startswith` guard with an observable `else` branch (warning log or raised error)

---

## Cross-references

- `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md` — the original security problems these fixes addressed; Pitfalls 1, 2, and 5 are implementation notes for Issues 1, (datetime bonus), and 2 respectively
