---
title: "Live-test session: 6 bugs fixed across Celery/asyncio, Quarto extension resolution, MinIO policy, and BlockNote editor round-trip"
category: integration-issues
date: "2026-03-27"
tags:
  - celery
  - asyncio
  - event-loop
  - nullpool
  - quarto
  - minio
  - bucket-policy
  - docker
  - fastapi
  - asyncpg
  - blocknote
  - editor-serialization
components:
  - api/tasks/render_task.py
  - api/database.py
  - docker/Dockerfile.worker
  - _extensions/senda/
  - api/services/storage.py
  - frontend/src/editor/serializer.ts
  - frontend/src/editor/SendaEditor.tsx
  - frontend/src/pages/Editor.tsx
problem_type: "Multi-layer integration failure spanning async runtime isolation, static asset packaging, object storage permissions, and editor state hydration"
symptoms:
  - "Celery render tasks completed in ~0.3s and reported success but documents were marked estado_render=fallido — RuntimeError: Future attached to a different loop from shared asyncpg pool"
  - "Quarto render exited non-zero with no stderr (--quiet swallows it) because _extensions/ was absent from the worker Docker image"
  - "Quarto render failed with 'Unable to read the extension senda' even after copying _extensions/ — files were nested at _extensions/senda/live/ instead of _extensions/senda/"
  - "Rendered HTML artifact URL stored in DB but browser received 403 Forbidden — MinIO bucket created without a public-read policy"
  - "Bucket policy application crashed with KeyError whose message was the beginning of the policy JSON — str.format() interpreted JSON braces as format placeholders"
  - "BlockNote editor displayed blank content when loading an existing document — Editor.tsx ignored doc.ast and astToBlockNote() did not exist"
outcome: resolved
---

# Live-Test Session: Six Bugs Fixed

All six bugs were found during the first live-test run of the full stack. They share a common theme: **assumptions about environment or data that were never validated at the integration seam between components**. Each bug occurred at a boundary — between the asyncio event loop and a connection pool, between a Docker build context and a runtime file path, between a Quarto naming convention and a directory layout, between an object store and its default access policy, between Python string formatting and JSON syntax, and between a fetch result and a UI component's initialization path.

---

## Root Cause Analysis

Every bug was silent in isolation:

- The Celery task reported Celery-level success (`succeeded`) but the broad `except Exception` inside committed `estado_render = "fallido"` — no unhandled exception, no Celery retry, no obvious error in worker logs.
- Missing `_extensions/` produced no build error; the image built cleanly and the worker started. The failure only surfaced when a render was triggered.
- The wrong extension depth caused `quarto render --quiet` to exit non-zero with empty stderr — the `RenderError` message was the fallback string `"Quarto render failed"`.
- `create_bucket()` with no policy returned 200. The 403 only appeared when a browser tried to load the artifact.
- `str.format()` on a JSON template only crashed when a render was actually triggered post-bucket-creation-fix.
- `obtener(id)` returned 200 with the full document including `ast`. The editor simply ignored it.

---

## Investigation

1. **Celery event loop**: Worker logs showed tasks completing in 0.3s — far too fast for a real Quarto render. DB query revealed `error_render = NULL` wasn't being set. Added logging to catch the `RuntimeError`, traced to `api/database.py`'s module-level engine.
2. **Missing `_extensions/`**: `docker compose exec worker ls /app/_extensions/` → `ls: cannot access '/app/_extensions/'`. Cross-referenced against `COPY` directives in `Dockerfile.worker`.
3. **Extension depth**: Ran `quarto render` manually inside the container without `--quiet`. Error: `Unable to read the extension 'senda'`. Tested empirically: flat `_extensions/senda/_extension.yml` worked; `_extensions/senda/live/_extension.yml` did not.
4. **MinIO 403**: Checked DB — `url_artefacto` was set and the file existed in MinIO. Ran `mc anonymous get local/senda-documentos` → `private`.
5. **Format crash**: After adding `put_bucket_policy`, renders failed with `error_render = "Error inesperado: '\\n  \"Version\"'"`. Recognized the `'\\n  "Version"'` as a `KeyError` repr matching the first bytes of the policy JSON string.
6. **Blank editor**: Read `Editor.tsx` load effect — `doc` was fetched, `setTitulo(doc.titulo)` called, `doc.ast` never used. `SendaEditor` always received `initialContent={undefined}`.

---

## Solutions

### Bug 1: Celery worker "Future attached to a different loop"

**File**: `api/tasks/render_task.py`

`api/database.py` creates a module-level `create_async_engine(...)` with an asyncpg connection pool. Pool entries hold futures bound to the event loop current at creation time. Celery workers call `asyncio.run(_run())` per task — each call creates and destroys an event loop. Using the shared pool inside the new loop raises:

```
RuntimeError: Task ... got Future ... attached to a different loop
```

Fix: create a `NullPool` engine fresh inside each `_run()` coroutine; dispose it in `finally`. Remove the `AsyncSessionLocal` import from the task module entirely.

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

def _make_engine():
    """NullPool: no connection reuse across asyncio.run() calls."""
    return create_async_engine(settings.database_url, poolclass=NullPool)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def render_documento(self, documento_id: str):
    async def _run():
        engine = _make_engine()
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                # ... all DB work ...
        finally:
            await engine.dispose()
    asyncio.run(_run())
```

---

### Bug 2: Worker Docker image missing `_extensions/`

**File**: `docker/Dockerfile.worker`

`Dockerfile.worker` only had `COPY api/ api/`. The `_extensions/` directory containing the custom Quarto format was never included in the image. Any render attempt inside the container would fail because the extension did not exist at runtime.

```dockerfile
COPY api/ api/
COPY _extensions/ _extensions/   # added
RUN pip install --no-cache-dir "./api[dev]"
```

---

### Bug 3: Quarto extension directory too deeply nested

**Files**: contents of `_extensions/senda/`

Quarto resolves `format: senda-html` by looking for extension id `senda` at `_extensions/senda/_extension.yml`. Files were nested one level deeper at `_extensions/senda/live/_extension.yml`. Quarto found `_extensions/senda/` but no `_extension.yml` directly inside it.

Empirical investigation:
```bash
# FAILS — extra live/ level
_extensions/senda/live/_extension.yml  →  ERROR: Unable to read the extension 'senda'

# Also FAILS — extension id would be 'live', format would be 'live-html'
_extensions/live/_extension.yml

# WORKS — flat, matches format name prefix at exactly one level deep
_extensions/senda/_extension.yml  →  format: senda-html ✓
```

Fix: moved all files from `_extensions/senda/live/` up to `_extensions/senda/` (git rename, no content changes).

---

### Bug 4: MinIO bucket not publicly readable → 403

**File**: `api/services/storage.py`

`ensure_bucket_exists()` called `create_bucket()` but never set a bucket policy. MinIO's default access level is private. All GETs from unauthenticated browsers returned 403.

Fix combined with Bug 5 (see below):

```python
import json

def ensure_bucket_exists() -> None:
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.storage_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=settings.storage_bucket)
        else:
            raise
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{settings.storage_bucket}/*"],
        }],
    })
    client.put_bucket_policy(Bucket=settings.storage_bucket, Policy=policy)
```

---

### Bug 5: Bucket policy `str.format()` crash on JSON braces

**File**: `api/services/storage.py`

The initial attempt used a multiline template string with `.format(bucket=...)`:

```python
_PUBLIC_READ_POLICY = """{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", ...}]
}"""
Policy=_PUBLIC_READ_POLICY.format(bucket=settings.storage_bucket)
# KeyError: '\n  "Version"...'
```

Python's `str.format()` scans for `{...}` pairs without understanding JSON. The opening `{` of the JSON object is treated as a format placeholder; the first `}` closes it; the resulting field name (the substring between them) is looked up in kwargs and raises `KeyError`. The `str(KeyError)` repr starts with the first bytes of the JSON — `'\n  "Version"'` — which is exactly what appeared in `error_render`.

Fix: build the structure as a Python dict and serialize with `json.dumps()` (shown in Bug 4 above). No format placeholders, no ambiguous braces.

---

### Bug 6: Editor shows empty content on load (missing AST round-trip)

**Files**: `frontend/src/editor/serializer.ts`, `frontend/src/editor/Editor.tsx`, `frontend/src/editor/SendaEditor.tsx`

`Editor.tsx` called `obtener(id)` and used only `doc.titulo`. `doc.ast` was silently discarded. `SendaEditor` always rendered with `initialContent={undefined}` → blank editor every time. There was no inverse of `blockNoteToAST`.

**`astToBlockNote()` added to `serializer.ts`**:

```typescript
type PartialEditorBlock = Record<string, any>;

function astBlockToEditorBlock(block: ASTBlock): PartialEditorBlock | null {
  switch (block.type) {
    case "text": {
      const headingMatch = block.text.match(/^(#{1,6}) (.*)$/);
      if (headingMatch) {
        return {
          type: "heading",
          props: { level: headingMatch[1].length },
          content: [{ type: "text", text: headingMatch[2], styles: {} }],
        };
      }
      return {
        type: "paragraph",
        content: block.text ? [{ type: "text", text: block.text, styles: {} }] : [],
      };
    }
    case "exercise":
      return {
        type: "ejercicio",
        props: {
          exerciseId: block.attrs.exerciseId,
          language: block.attrs.language,
          caption: block.attrs.caption,
          starterCode: block.attrs.starterCode,
          solutionCode: block.attrs.solutionCode,
          hints: JSON.stringify(block.attrs.hints), // BlockNote stores hints as JSON string
        },
      };
    case "nota":
      return { type: "nota", props: { ...block.attrs } };
    case "ecuacion":
      return { type: "ecuacion", props: { ...block.attrs } };
    case "cargadorDatos":
      return { type: "cargadorDatos", props: { ...block.attrs } };
    default:
      return null;
  }
}

export function astToBlockNote(ast: DocumentAST): PartialEditorBlock[] {
  return ast.blocks
    .map(astBlockToEditorBlock)
    .filter((b): b is PartialEditorBlock => b !== null);
}
```

**`Editor.tsx` load effect**:

```typescript
obtener(id).then((doc) => {
  setTitulo(doc.titulo);
  if (doc.ast) {
    setInitialBlocks(astToBlockNote(doc.ast)); // was: doc.ast ignored entirely
  }
})
```

**`Editor.tsx` render** — `key` forces remount when navigating between documents; `useCreateBlockNote` only reads `initialContent` at construction time:

```tsx
<SendaEditor key={id ?? "new"} initialContent={initialBlocks} onChange={handleBlocksChange} />
```

---

## Key Technical Insights

**1. `asyncio.run()` is not safe with module-level connection pools.** Every call creates a new event loop and destroys the old one. Any object that internally holds futures — including SQLAlchemy's asyncpg pool — becomes invalid across calls. The correct pattern for Celery tasks: create and dispose the engine inside the `async def` function passed to `asyncio.run()`, using `NullPool` to prevent connection caching.

**2. Docker `COPY` directives are explicit; nothing is inferred.** A file required at runtime that lives outside the copied directory is silently absent in the image. There is no build-time warning. Audit every runtime dependency — not just Python packages — against the `COPY` lines in each Dockerfile.

**3. Quarto extension resolution is position-sensitive, not recursive.** The extension id in `format: <id>-<format>` maps to `_extensions/<id>/_extension.yml` at exactly that depth. An extra subdirectory level breaks resolution completely with no fallback. If the file is not at the expected path, Quarto reports the extension as unreadable.

**4. Object storage defaults are private; policy setup is part of initialization.** Neither AWS S3 nor MinIO will serve objects publicly without an explicit bucket policy. `create_bucket()` succeeds silently and every subsequent write succeeds — the failure only surfaces on read. Public-read policy setup must be treated as part of bucket initialization in the same function call, not a separate step.

**5. Python's `str.format()` is not JSON-aware.** It interprets every `{...}` pair as a format placeholder regardless of context. Build JSON payloads with `json.dumps()` from a Python dict — no format placeholders, no ambiguous braces. If interpolation is needed, keep it in an f-string on only the leaf value (e.g., the `Resource` field's ARN string).

**6. React constructor hooks do not re-run on prop changes.** `useCreateBlockNote` (and similar initializing hooks) reads `initialContent` once at mount. Updating the prop after mount has no effect. Use a `key` prop tied to the document identity to force unmount and remount when the user navigates to a different document.

**7. Serialization round-trips must be designed as a pair.** The system had `blockNoteToAST` but no `astToBlockNote`. The asymmetry was invisible because the save path worked and no error was thrown on load — the data was simply discarded. Any serialization format used for persistence needs both directions implemented and tested together.

---

## Prevention Strategies

### Async resource lifecycle

- Never initialize asyncpg pools, aioredis clients, or any asyncio-bound resource at module level in Celery task modules. Flag `create_async_engine()` at module scope in `tasks/` as a lint violation.
- Test: invoke the same task function twice via `asyncio.run()` in the same process; assert no `Future attached to a different loop`.

### Dockerfile completeness

- After any structural change to the repo (new top-level directory, new asset directory), update all Dockerfiles in the same PR.
- Add a CI smoke step: build the worker image and run `quarto render smoke.qmd` inside the container; assert exit code 0.

### Quarto extension layout

- The invariant: extension files live at exactly `_extensions/<vendor>/<name>/`, matching `format: <vendor>-<name>` in the QMD. No deeper nesting allowed.
- Add a CI job that renders a minimal `.qmd` with the custom format and asserts exit 0. Catches both missing files and wrong depth.

### Object storage initialization

- `ensure_bucket_exists()` is incomplete without the policy call. Treat create + policy as one atomic operation; surface policy failures loudly.
- Integration test: call `ensure_bucket_exists()`, upload a file, perform an unauthenticated HTTP GET on the public URL; assert 200.

### String templating

- Never use `str.format()` or `%` formatting on JSON payloads. Build dicts and call `json.dumps()`.
- Grep-based pre-commit hook: flag `.format(` calls on any variable named `policy`, `payload`, or `template`.

### Frontend state hydration

- Every write path (UI → AST → API) must have a corresponding read path (API → AST → UI) implemented in the same PR.
- PR template checklist: "If this PR persists structured data, does it also hydrate that data back into the UI component?"
- Test: create a document, reload, assert editor content matches what was saved.

---

## Live-Test Checklist

Before calling any feature "working" in the full stack:

1. **Worker cold start** — restart the worker container and trigger the task; confirm completion without event-loop errors.
2. **Worker image from scratch** — `docker build --no-cache` on the worker Dockerfile; exec in and verify all required asset directories are present.
3. **Quarto render inside container** — exec into the worker and run `quarto render <test.qmd>` manually; assert exit 0.
4. **Unauthenticated artifact access** — open the artifact URL in an incognito window (no auth cookies); assert HTTP 200.
5. **Bucket policy** — run `mc anonymous get <alias>/<bucket>`; confirm `download` or `public`.
6. **Round-trip document hydration** — create a document with multiple block types, navigate away, return; verify content matches.
7. **New document blank state** — open a brand-new document URL; confirm the editor mounts empty without errors.
8. **Concurrent tasks** — trigger two renders simultaneously; confirm both complete without cross-contamination.
9. **Service startup from scratch** — `docker compose down && docker compose up`; confirm bucket policy, migrations, and any seed data re-apply automatically.
10. **Failure surfaces in logs** — break one dependency (wrong credentials, missing extension); confirm the error is diagnosable from logs, not a silent hang or generic 500.
11. **API contract on missing fields** — submit requests with optional fields omitted; confirm no 500 from `.format()` crashes or `None` attribute access.
12. **Task retry behavior** — simulate a transient failure mid-task; confirm retry does not leak connections.

---

## Test Cases to Add

**Celery / asyncio**
- `test_task_runs_twice_same_process` — call task function via `asyncio.run()` twice in sequence; assert no `Future attached to a different loop`.
- `test_no_module_level_pool` — import the tasks module; assert no `asyncpg.Pool` instance exists at module scope.

**Docker image contents**
- CI step: `docker run --rm <worker_image> ls /app/_extensions/senda/`; assert exit 0.
- CI step: render `tests/fixtures/smoke.qmd` inside the worker image; assert `smoke.html` is created.

**Quarto extension layout**
- `test_extension_directory_depth` — walk `_extensions/`; assert no `_extension.yml` is more than two directories deep under `_extensions/`.

**MinIO bucket policy**
- `test_bucket_is_public_after_ensure` — call `ensure_bucket_exists()`, upload a file, unauthenticated GET; assert 200.
- `test_ensure_bucket_is_idempotent` — call twice; assert no exception and policy remains public.

**String templating**
- `test_policy_json_is_valid_json` — assert `json.loads(policy)` succeeds on the generated string.

**Frontend round-trip**
- `test_editor_hydrates_saved_ast` (Playwright) — save document with two block types, reload, assert editor has matching content.
- `test_ast_to_blocknote_roundtrip` (Vitest) — for each block type, assert `astToBlockNote(blockNoteToAST([block]))` deep-equals the original block structure.

---

## Cross-References

- `docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md` — asyncio/event-loop patterns in FastAPI; asyncio.to_thread() for sync I/O in async routes
- `docs/solutions/database-issues/alembic-asyncpg-fastapi-migration-foundation.md` — asyncpg dual-engine setup; NullPool for one-shot processes (Alembic migrator)
- `docs/solutions/runtime-errors/docker-compose-stack-startup-failures.md` — Dockerfile COPY semantics; `COPY api/ api/` vs `COPY api/ .`
- `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md` — sync boto3 blocking async loop; MinIO path traversal; asyncio.to_thread() for storage calls
- `docs/solutions/integration-issues/blocknote-047-typescript-integration-pitfalls.md` — BlockNote schema types; editor state management; React 19 compatibility
