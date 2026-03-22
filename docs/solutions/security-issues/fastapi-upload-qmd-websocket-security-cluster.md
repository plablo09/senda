---
title: "Security Anti-pattern Cluster: Async FastAPI, File Upload, QMD Serialization, iframe Sandbox, WebSocket"
category: security-issues
date: 2026-03-21
tags:
  - fastapi
  - async
  - boto3
  - minio
  - path-traversal
  - rce
  - qmd
  - quarto
  - iframe-sandbox
  - websocket
  - redis
  - pub-sub
  - sqlalchemy
  - timezone
  - celery
problem_type: security_vulnerability_cluster
components:
  - api/routers/datasets.py
  - api/services/storage.py
  - api/services/qmd_serializer.py
  - api/tasks/render_task.py
  - api/ws/render_status.py
  - api/models/documento.py
  - api/models/dataset.py
  - frontend/src/pages/Editor.tsx
  - frontend/src/hooks/useRenderStatus.ts
  - nginx/dev.conf
severity: high
status: fixed
---

# Security Anti-pattern Cluster: Async FastAPI + File Upload + QMD + WebSocket

Six security and correctness issues found during code review of Phase 2 (block editor implementation). None were individually exotic — each is a well-known pattern violation. They cluster around three subsystems: file upload, QMD code generation, and real-time status delivery.

**Fixed** — all issues were applied before merging Phase 2 (commit `fix(security): address 8 review findings before merge`, 2026-03-21). See also: [`phase-3-llm-guidance-pre-merge-review-fixes.md`](phase-3-llm-guidance-pre-merge-review-fixes.md) for the analogous Phase 3 cluster.

**Related plan:** `docs/plans/2026-03-20-002-feat-block-editor-teacher-authoring-plan.md`

---

## Issue 1 — Sync boto3 blocks the async event loop

**Severity:** High — correctness under concurrency, not just performance
**Files:** `api/services/storage.py` (all functions), `api/routers/datasets.py:36,68`

### Problem

`upload_dataset()` and `delete_object()` use the synchronous `boto3` client. They are called directly from `async def` FastAPI route handlers. Boto3's socket I/O blocks the event loop thread for the duration of the S3 round-trip (typically 10–500 ms, unbounded under load). While blocked, **every other request on that worker is frozen** — including WebSocket heartbeats and health checks.

```python
# Wrong — blocks event loop:
async def subir_dataset(...):
    url = upload_dataset(dataset_id, filename, content, mimetype)  # sync boto3!
```

Note: sync boto3 used from Celery workers (synchronous context) is correct and should remain unchanged.

### Fix

```python
import asyncio

async def subir_dataset(...):
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(
        None, upload_dataset, dataset_id, filename, content, mimetype
    )
    # or: await asyncio.to_thread(upload_dataset, ...)
```

Apply the same pattern to `delete_object` calls from async routes.

Long-term alternative: replace boto3 with `aiobotocore` for routes called from async context.

### Detection

```bash
# Find boto3 usage in the same files that contain async def
grep -rn "import boto3\|boto3\.client\|boto3\.resource" --include="*.py" -l \
  | xargs grep -l "async def"
```

---

## Issue 2 — Raw user filename injected into MinIO object key (path traversal)

**Severity:** High — cross-resource overwrite
**Files:** `api/services/storage.py:40`, `api/routers/datasets.py:36`

### Problem

```python
# storage.py:40
key = f"datasets/{dataset_id}/{filename}"
```

`filename` comes from `file.filename` — the `Content-Disposition` header of the multipart body, which is fully attacker-controlled. A crafted filename can traverse out of the intended prefix:

- `../../documentos/some-uuid/index.html` → overwrites another document's rendered HTML
- `../datasets/other-uuid/data.csv` → overwrites another dataset's file

The reconstructed key is also used for deletion (fragile prefix-strip pattern), so a bad key silently deletes the wrong object or fails silently behind a bare `except: pass`.

### Fix

```python
import pathlib, re

def sanitize_filename(filename: str) -> str:
    # Take basename only (strips any directory components)
    name = pathlib.Path(filename).name
    # Allow only safe characters
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name or "file"

# storage.py upload_dataset:
safe_name = sanitize_filename(filename)
key = f"datasets/{dataset_id}/{safe_name}"
```

Store the original `filename` in the DB column for display only. The storage key is derived only from the sanitized name.

---

## Issue 3 — QMD serializer injects unsanitized user content → RCE in Quarto worker

**Severity:** Critical — arbitrary code execution in the render worker
**Files:** `api/services/qmd_serializer.py` (multiple functions)

### Problem

User-controlled strings are interpolated directly into QMD code fences and Python/R cell source. This is **code injection at the source level**, not an XSS-style issue:

```python
# serialize_cargador_datos — double-quote closes the string literal:
f'{variable_name} = pd.read_csv("{url}")'
# A url containing `"` → closes string → injects arbitrary Python

# serialize_exercise — newline in exercise_id injects QMD cell options:
f"# exercise_id: {exercise_id}"
# A \n in exercise_id → injects arbitrary #| directives

# Any code block — triple backticks close the fence early:
# A ``` in starter_code or solution_code terminates the fence
```

The Quarto worker (`subprocess.run(["quarto", "render", ...])`) executes the generated `.qmd` file as-is. The worker runs inside Docker but has access to MinIO credentials, Redis URL, and DB URL from its environment. Without authentication, this endpoint is reachable by anyone.

### Fix

Validate at each injection boundary:

```python
import re

def validate_identifier(name: str) -> str:
    """Ensure name is a valid Python/R identifier before injecting into code."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return name

def escape_string_literal(s: str) -> str:
    """Escape for use inside a double-quoted Python/R string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

def strip_newlines(s: str) -> str:
    """For single-line fields (IDs, titles) that must not contain newlines."""
    return s.replace("\n", " ").replace("\r", " ")

# Usage in serialize_cargador_datos:
safe_var = validate_identifier(variable_name)
safe_url = escape_string_literal(url)
f'{safe_var} = pd.read_csv("{safe_url}")'

# Usage in serialize_exercise:
safe_id = strip_newlines(exercise_id)
f"# exercise_id: {safe_id}"
```

For code blocks (`starter_code`, `solution_code`), use a longer fence delimiter that can't be closed by user content:

```python
# Use ~~~~~ instead of ``` — user content cannot contain 5 tildes
f"~~~~~{{python}}\n{starter_code}\n~~~~~"
```

Longer-term: validate all user fields at the API boundary (Pydantic) so invalid content is rejected before it reaches the serializer.

---

## Issue 4 — iframe `allow-scripts` + `allow-same-origin` defeats sandbox entirely

**Severity:** High — XSS containment failure
**File:** `frontend/src/pages/Editor.tsx:412`

### Problem

```tsx
<iframe
  src={previewSrc}
  sandbox="allow-scripts allow-same-origin allow-forms"
  ...
/>
```

The combination of `allow-scripts` AND `allow-same-origin` is a well-documented footgun: a script inside the iframe can access `window.parent`, read the parent's cookies and localStorage, and remove or rewrite the sandbox attribute from inside the frame. **The sandbox provides zero protection in this configuration.**

This means any XSS in the Quarto-rendered HTML (e.g., from injected LaTeX, malicious code block output, or a stored XSS via dataset filename) escapes the iframe and runs in the full application origin.

Each flag alone is safe; their combination is not.

### Fix

```tsx
// Remove allow-same-origin:
<iframe
  src={previewSrc}
  sandbox="allow-scripts allow-forms"
  title="Vista previa"
/>
```

The preview iframe does not need same-origin access. If the iframe needs to communicate with the parent (e.g., for resize messages), use `postMessage` — which works without `allow-same-origin`.

### Detection

```bash
grep -rn "sandbox=" --include="*.tsx" --include="*.html" \
  | grep "allow-scripts" | grep "allow-same-origin"
```

---

## Issue 5 — Redis pub/sub published before `session.commit()` (state inconsistency)

**Severity:** Medium — distributed state inconsistency
**File:** `api/tasks/render_task.py` (reset_stale_procesando function)

### Problem

```python
# reset_stale_procesando — wrong ordering:
for doc in stale:
    doc.estado_render = "fallido"
    _publish_render_status(doc.id, "fallido", ...)  # ← published BEFORE commit
await session.commit()  # if this fails, DB is still "procesando" but clients saw "fallido"
```

If `session.commit()` raises an exception, the DB row is never updated but connected WebSocket clients have already received the terminal status. The UI shows "fallido" permanently; the DB shows "procesando". There is no retry trigger — the document is stuck.

Note: the main `render_documento` task already gets this right (publish follows commit on lines 66 and 72). The beat task introduced the regression.

### Fix

Publish in a second pass, after commit succeeds:

```python
# Correct ordering:
for doc in stale:
    doc.estado_render = "fallido"
await session.commit()  # commit first
for doc in stale:       # then notify
    _publish_render_status(doc.id, "fallido", None, None)
```

**Rule:** External systems learn about state changes only after the DB has durably recorded them. This applies to Redis, Celery tasks, WebSocket emits, and email sends alike.

---

## Issue 6 — WebSocket race window: render completes before subscription

**Severity:** Low-Medium — UI hang under race condition
**File:** `frontend/src/hooks/useRenderStatus.ts`

### Problem

Timeline of the race:
1. User saves document → API sets `estado = procesando` → Celery task enqueued
2. Client opens WebSocket to `/ws/documentos/{id}/estado`
3. Celery finishes quickly → publishes `render:{id}` to Redis
4. Server-side WebSocket handler subscribes to Redis **after** step 3
5. The pub/sub message is missed; no future message will arrive
6. WebSocket stays open (server's `pubsub.listen()` blocks), `onclose` never fires
7. Polling fallback never starts (only triggered on error/close)
8. UI hangs indefinitely

### Fix

Add a client-side timeout that starts polling if no WS message arrives within a reasonable window:

```typescript
// useRenderStatus.ts
const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// After constructing the WebSocket:
timeoutRef.current = setTimeout(() => {
  if (!isTerminalRef.current) startPolling();
}, 20_000); // 20s covers typical render latency

// Inside stopAll():
if (timeoutRef.current) {
  clearTimeout(timeoutRef.current);
  timeoutRef.current = null;
}
```

Server-side fix (closes the race entirely): after subscribing to Redis, do one synchronous DB read. If the document is already in a terminal state, send the cached status immediately and close.

---

## Bonus: Datetime timezone correctness

**Files:** `api/models/documento.py`, `api/models/dataset.py`

Two related issues that interact with the stale-task beat:

```python
# documento.py — both wrong:
created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # deprecated + naive
updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# dataset.py — correct (use as reference):
created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
```

`reset_stale_procesando` computes `cutoff = datetime.now(UTC)` (timezone-aware) and compares against `Documento.updated_at` (naive). This works on UTC-configured servers but breaks on any non-UTC host.

Fix:

```python
# Both models:
from datetime import datetime, UTC

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC),
    onupdate=lambda: datetime.now(UTC),
    nullable=False
)
```

Detection:

```bash
grep -rn "DateTime()" --include="*.py"          # bare DateTime, no timezone=True
grep -rn "datetime\.utcnow" --include="*.py"    # deprecated
```

---

## Prevention Checklist

**File upload**
- [ ] User-supplied filenames sanitized with `pathlib.Path(f).name` + character allowlist before use in storage keys
- [ ] `client_max_body_size` set in nginx before the upload endpoint (`52m` for a 50 MB limit)
- [ ] Size check happens at the streaming boundary, not after full read into memory

**Async routes**
- [ ] No `boto3` (sync) client called from `async def` without `run_in_executor` or `asyncio.to_thread`
- [ ] CI runs with `PYTHONASYNCIODEBUG=1` to surface slow callbacks (>100 ms)

**QMD / code generation**
- [ ] All user strings validated or escaped before interpolation into QMD templates
- [ ] Identifiers validated against `[a-zA-Z_][a-zA-Z0-9_]*`
- [ ] String literals escaped (`"` → `\"`, `\n` → `\\n`)
- [ ] Code block fences use `~~~~~` (5 tildes) to prevent user content from closing them
- [ ] Quarto worker runs with network isolation and read-only root filesystem

**iframe**
- [ ] No iframe has both `allow-scripts` and `allow-same-origin` in its sandbox attribute
- [ ] Linting rule or DOM test asserts this combination never appears

**Event ordering**
- [ ] Redis publish / WebSocket emit / task dispatch always follows `session.commit()`, never precedes it
- [ ] State machine transitions: DB first, external notification second

**WebSocket**
- [ ] Every WS subscription has a client-side timeout with a defined fallback (polling or error state)
- [ ] Server-side: after subscribing to pub/sub, do one DB read to catch already-terminal state

**Datetime**
- [ ] All `DateTime` columns use `DateTime(timezone=True)`
- [ ] No `datetime.utcnow` — use `datetime.now(UTC)` everywhere
- [ ] Pre-commit hook flags `utcnow` usage
