---
title: "test: Live-Test Strategy — Automated Integration Suite (Zones 1-2) + Manual Playbooks (Zones 3-5)"
type: test
status: active
date: 2026-03-28
---

# Live-Test Strategy: Automated Integration Suite + Manual Playbooks

## Overview

The current test suite has 94 passing **unit** tests. Every test uses `dependency_overrides` and `AsyncMock` — none of them touch a real database, a real Celery worker, a real MinIO bucket, or a real WebSocket connection. The first live-test session found 6 bugs that all unit tests had missed, each at an integration seam.

This plan defines a two-track strategy:

- **Track A — Automated** (Zones 1-2): a pytest integration suite in `api/tests/integration/` that runs against the full live Docker Compose stack. Covers auth flows and the teacher document authoring lifecycle including render pipeline.
- **Track B — Manual playbooks** (Zones 3-5): structured, step-by-step browser and CLI guides for student WebSocket execution, LLM feedback, and infrastructure reset scenarios that cannot be automated reliably without significant test infrastructure investment.

---

## Problem Statement / Motivation

Six integration bugs were missed by 94 unit tests and only found during the first live session:

1. Celery event loop conflict (`asyncio.run()` + module-level pool)
2. Missing `_extensions/` from worker Docker image
3. Quarto extension directory depth wrong
4. MinIO bucket without public-read policy → 403
5. `str.format()` on JSON → `KeyError`
6. Editor ignoring `doc.ast` on load → blank editor

The root cause pattern: **assumptions made at integration seams that are impossible to catch with mocked dependencies**. Every seam not covered by an integration test is a latent bug waiting to be found in production.

Additionally, the following integration paths have zero test coverage of any kind:
- `documentos` router (CRUD + render trigger)
- `ejecutar` router (HTTP + WebSocket)
- `retroalimentacion` router
- `render_task.py` (Celery task)
- Render-status WebSocket (`/ws/documentos/{id}/estado`)
- MinIO bucket lifecycle

---

## Proposed Solution

### Track A: Automated Integration Suite

Create `api/tests/integration/` with a shared `conftest.py` and two test modules. Tests run against the live Docker Compose stack via `make test-int` (already configured: `docker compose run --rm -e PYTHONPATH=/app api pytest api/tests/integration/ -v`).

**One-time prerequisite fix:** add `filterwarnings = ["error::RuntimeWarning"]` to `pyproject.toml` — this turns silent async coroutine-as-truthy failures into loud errors, the single highest-leverage change to make the entire test suite trustworthy. (See `docs/solutions/test-failures/docker-pytest-async-mock-pitfalls.md`.)

### Track B: Manual Playbooks

Two Markdown checklists embedded in this plan:
1. **Student execution playbook** — browser-based, covers WebSocket execution for Python/R/geo, plot output, auth rejection, sandbox escape attempts, LLM hints
2. **Infrastructure playbook** — CLI-based, covers cold-start idempotency, worker kill/retry, migration replay, Dockerfile completeness

---

## Technical Approach

### Phase 0: Foundation (prerequisite — do first)

**`api/pyproject.toml`** — add to `[tool.pytest.ini_options]`:
```toml
filterwarnings = ["error::RuntimeWarning"]
```

**Directory structure to create:**
```
api/tests/integration/
├── __init__.py
├── conftest.py
├── test_auth.py
└── test_documentos.py
```

---

### Phase 1: `conftest.py` — shared fixtures

**File:** `api/tests/integration/conftest.py`

All integration tests talk to the stack at `http://api:8000` (reachable from inside the `api` container where `make test-int` runs). Do not use `localhost` — tests run inside Docker.

```python
import pytest
import httpx
import uuid

BASE_URL = "http://api:8000"

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _random_email():
    return f"test-{uuid.uuid4().hex[:8]}@senda-test.local"

@pytest.fixture
async def registered_user(client):
    """Creates a student user, yields (email, password, user_id). Leaves user in DB."""
    email = _random_email()
    password = "Test1234!"
    resp = await client.post("/auth/registro", json={"email": email, "password": password, "rol": "student"})
    assert resp.status_code == 201
    yield {"email": email, "password": password, "id": resp.json()["id"]}

@pytest.fixture
async def auth_token(client, registered_user):
    """Logs in, returns access_token string from JSON body (not cookie)."""
    resp = await client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token
    return token

@pytest.fixture
def auth_headers(auth_token):
    """Authorization header dict for use in all authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}

# ── Document helpers ───────────────────────────────────────────────────────────

MINIMAL_AST = {
    "blocks": [
        {"type": "text", "text": "# Título de prueba"},
        {"type": "text", "text": "Párrafo de contenido."},
    ]
}

FULL_AST = {
    "blocks": [
        {"type": "text", "text": "# Documento completo"},
        {"type": "text", "text": "Párrafo introductorio."},
        {
            "type": "ejercicio",
            "attrs": {
                "exerciseId": "ej-001",
                "language": "python",
                "caption": "Ejercicio de prueba",
                "starterCode": "# escribe tu código aquí",
                "solutionCode": "print('hola')",
                "hints": ["Piensa en print()", "Usa comillas"],
            },
        },
        {"type": "nota", "attrs": {"content": "Esta es una nota importante."}},
        {"type": "ecuacion", "attrs": {"latex": "E = mc^2", "display": True}},
    ]
}

@pytest.fixture
async def created_document(client):
    """Creates a document without AST (no render triggered). Deletes on teardown."""
    resp = await client.post("/documentos", json={"titulo": "Doc de prueba"})
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    yield resp.json()
    await client.delete(f"/documentos/{doc_id}")

@pytest.fixture
async def rendered_document(client):
    """Creates a document with a minimal AST, waits for render to complete. Deletes on teardown."""
    import asyncio
    resp = await client.post("/documentos", json={"titulo": "Doc render prueba", "ast": MINIMAL_AST})
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # Poll until terminal state or timeout (60s — Quarto can be slow)
    for _ in range(60):
        doc = (await client.get(f"/documentos/{doc_id}")).json()
        if doc["estado_render"] in ("listo", "fallido"):
            break
        await asyncio.sleep(1.0)

    yield doc
    await client.delete(f"/documentos/{doc_id}")
```

**Key design decisions:**
- `scope="session"` on `base_url` only; all others are function-scoped to guarantee isolation.
- Token comes from `resp.json()["access_token"]` — the P1 fix confirmed this is always present (see `docs/solutions/security-issues/unauthenticated-execution-endpoints-p1-fixes.md`).
- Never use `resp.cookies["access_token"]` — `httpx` in async mode does not persist httpOnly cookies across requests the same way a browser does.
- No `dependency_overrides` — these tests talk to the real app.

---

### Phase 2: Zone 1 — Auth integration tests

**File:** `api/tests/integration/test_auth.py`

#### Happy path

| Test | Endpoint | Assert |
|------|----------|--------|
| `test_registro_creates_user` | `POST /auth/registro` | 201; `id`, `email`, `rol="student"` in body |
| `test_login_returns_token_in_body` | `POST /auth/login` | 200; `access_token` non-empty string; `Set-Cookie` header present |
| `test_me_with_valid_token` | `GET /auth/me` | 200; `email` matches registered user |
| `test_refresh_rotates_token` | `POST /auth/refresh` (via cookie from login response) | 200; new `access_token` != original; original refresh token is revoked (second call returns 401) |
| `test_logout_clears_session` | `POST /auth/logout` then `GET /auth/me` | logout returns 200; subsequent `/me` with the old token returns 401 |

#### Negative / security

| Test | Input | Assert |
|------|-------|--------|
| `test_registro_duplicate_email` | Same email twice | Second registration: 409, not 500 |
| `test_login_wrong_password` | Correct email, wrong password | 401 |
| `test_login_nonexistent_email` | Unknown email | 401 (not 404 — don't leak existence) |
| `test_me_no_token` | `GET /auth/me` with no auth header | 401 |
| `test_me_invalid_token` | `Authorization: Bearer garbage` | 401 |
| `test_registro_invalid_payload` | Missing `email` field | 422 |
| `test_refresh_without_cookie` | `POST /auth/refresh` with no cookie | 401 |

#### Rate limiting (smoke only — full rate-limit tests are slow)

| Test | Action | Assert |
|------|--------|--------|
| `test_registro_rate_limit` | 6 registration attempts in a loop | At least one `429`; confirm limit is 5/min |

**Implementation note:** Send `cookies={"refresh_token": refresh_token_value}` to the `httpx` client to test the refresh endpoint, since httpx won't automatically forward the `Set-Cookie` from login. Extract the refresh token from `resp.headers.get("set-cookie")` by parsing the cookie header.

---

### Phase 3: Zone 2 — Document lifecycle integration tests

**File:** `api/tests/integration/test_documentos.py`

#### CRUD basics

| Test | Action | Assert |
|------|--------|--------|
| `test_create_document_no_ast` | `POST /documentos` with title only | 201; `estado_render="pendiente"` (no render triggered) |
| `test_get_document` | Use `created_document` fixture | 200; all fields present |
| `test_list_documents` | `GET /documentos` | 200; list (may have items from other tests, assert `len >= 1`) |
| `test_update_document_titulo` | `PUT /documentos/{id}` with new title | 200; `titulo` updated |
| `test_delete_document` | `DELETE /documentos/{id}` | 204; subsequent `GET` returns 404 |
| `test_get_nonexistent_document` | `GET /documentos/{uuid4()}` | 404 |

#### Render pipeline (the critical path)

| Test | Action | Assert |
|------|--------|--------|
| `test_render_completes_with_minimal_ast` | Use `rendered_document` fixture | `estado_render == "listo"`; `url_artefacto` is non-null string |
| `test_render_artifact_is_publicly_accessible` | `httpx.get(doc["url_artefacto"])` with no auth | HTTP 200; `Content-Type: text/html` |
| `test_render_produces_valid_html` | GET artifact content | Contains `<html` (not empty, not JSON error) |
| `test_render_with_full_ast` | `POST` with `FULL_AST` (all block types) | `estado_render == "listo"` within 90s |
| `test_update_triggers_rerender` | Create doc, wait for `listo`, update AST, wait again | Second `url_artefacto` present; `estado_render == "listo"` |

#### Editor AST round-trip (regression for Bug 6)

| Test | Action | Assert |
|------|--------|--------|
| `test_ast_saved_and_returned` | `POST /documentos` with `FULL_AST`; `GET /documentos/{id}` | `doc["ast"]` is not null; `doc["ast"]["blocks"]` has same length as input |
| `test_ast_exercise_block_roundtrip` | POST with `ejercicio` block; GET | `hints`, `starterCode`, `solutionCode`, `language` all match; `hints` is a list (not a JSON string) |

#### Edge cases

| Test | Action | Assert |
|------|--------|--------|
| `test_create_document_empty_blocks` | `POST` with `{"blocks": []}` | 201; render attempts; does not crash with 500 |
| `test_create_document_malformed_ast` | `POST` with `{"ast": {"not_blocks": []}}` | 422 with validation error details |
| `test_long_text_block` | Text block with 5000-char string | No truncation; `GET` returns same length |

#### Render failure (Celery error path)

| Test | Action | Assert |
|------|--------|--------|
| `test_render_failure_sets_fallido` | Inject invalid AST that will fail Quarto serialization (e.g., unknown block type) | `estado_render == "fallido"` within 30s; `error_render` is non-null; not a 500 on the API |

**Implementation note on polling:** Use the render-status WebSocket (`ws://api:8000/ws/documentos/{id}/estado`) rather than polling for faster tests. Use the `websockets` Python library for this — `httpx` does not support WebSocket. Add `websockets>=12.0` to `api/pyproject.toml` test dependencies.

```python
import websockets

async def wait_for_render(doc_id: str, timeout: int = 90) -> str:
    uri = f"ws://api:8000/ws/documentos/{doc_id}/estado"
    try:
        async with websockets.connect(uri) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.loads(msg)["estado"]
    except asyncio.TimeoutError:
        return "timeout"
```

Note the race condition documented in `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md`: if the render completes before the WS subscription is established, the pub/sub message is missed. The server should handle this by doing a DB read after subscribing — verify this is implemented in `render_status` WebSocket handler before relying on it in tests. Fallback: always have a polling loop as the safety net.

---

### Phase 4: Zone 3 — Student execution manual playbook

> **Prerequisites:** Stack is up (`docker compose up`). Open browser devtools (Network + Console) before starting.

#### 4.1 Basic execution

| # | Steps | Expected |
|---|-------|----------|
| E1 | Create a document with one Python `ejercicio` block. Set `starterCode = "print('hola mundo')"`. Save and wait for render (`estado_render = listo`). | Artifact URL appears in editor preview. |
| E2 | Open the artifact URL in an **incognito window** (no cookies). | HTML renders. Code cell is visible with the starter code. No JS errors in console. |
| E3 | Click "Ejecutar" on the Python cell. | Output `hola mundo` appears below the cell within 5s. No WS errors in Network tab. |
| E4 | Add an R `ejercicio` block with `starterCode = "cat('hola desde R\n')"`. Re-render. Open artifact. Click Ejecutar. | `hola desde R` appears. |
| E5 | Python cell with `import matplotlib.pyplot as plt; plt.plot([1,2,3]); plt.savefig('/tmp/out.png'); print('done')` | `done` in output. No crash. (Image output via current path may not render inline — note behavior.) |
| E6 | Python cell with `import geopandas as gpd; print(gpd.__version__)` | Version string in output. Confirms geo stack is installed in the exec container. |
| E7 | R cell with `library(sf); cat(packageVersion('sf'), '\n')` | Version string. Confirms R geo stack. |

#### 4.2 WebSocket auth behavior

| # | Steps | Expected |
|---|-------|----------|
| A1 | Open the artifact URL normally (no login). Click Ejecutar. | Check Network tab: WS connection opens, **closes with code 4008** (Policy Violation). UI shows a message, not a blank hang. |
| A2 | Log in, open the artifact, click Ejecutar. | WS stays open. Output appears. |
| A3 | Log out, refresh the artifact page, click Ejecutar. | Same as A1 — 4008, not a silent hang. |

**Diagnostic commands:**
```bash
# Watch worker logs during execution
docker compose logs -f worker api

# Check execution container status
docker ps --filter "label=senda.exec=true"

# Confirm network isolation on exec containers
docker inspect $(docker ps -q --filter "label=senda.exec=true") | grep '"NetworkMode"'
# Should be "none"
```

#### 4.3 Concurrency and timeouts

| # | Steps | Expected |
|---|-------|----------|
| C1 | Open artifact in two browser tabs. Click Ejecutar in both simultaneously. | Both complete. No "pool exhausted" or cross-contamination of output. |
| C2 | Python cell with `import time; time.sleep(300)` (infinite-like). Click Ejecutar. | Within 60s (or configured timeout), execution is terminated. Cell shows timeout message. Other executions still work. |
| C3 | Python cell with `import subprocess; subprocess.run(['ls', '/'])`. | Execution fails or returns empty — network isolation and limited filesystem access prevents escape. |

---

### Phase 5: Zone 4 — LLM feedback manual playbook

> **Prerequisites:** `ollama` service running OR configured LLM provider. Check `LLM_BASE_URL` and `LLM_MODEL` in `.env`.

| # | Steps | Expected |
|---|-------|----------|
| F1 | Open a Python exercise. Write intentionally wrong code (e.g., `prit("hola")`). Click Ejecutar. | Error output appears. LLM hint appears below the cell. Hint is Socratic (question, not solution). Hint contains `diagnostico` and `pregunta_guia`. |
| F2 | Repeat F1 twice more (same cell). | Second attempt: no hint (silence window). Third attempt: hint reappears. (Rate limiter: first error → hint; next 2 → silence; 4th → hint; max 3 total hints.) |
| F3 | After 3 hints on the same cell, trigger error again. | No LLM call. "Límite de retroalimentación alcanzado" message (or equivalent). |
| F4 | Same intentionally-wrong R code. | Hint appears for R errors as well. |
| F5 | Correct the code and execute successfully. | No hint. Success output only. |
| F6 | Bring LLM service down (`docker compose stop ollama`). Trigger an error. | Execution result is still visible. LLM call fails gracefully — fallback message shown, not a 500 or blank. |

**Diagnostic command:**
```bash
# Watch LLM feedback calls (look for "retroalimentacion" in logs)
docker compose logs -f api | grep -i retro
```

---

### Phase 6: Zone 5 — Infrastructure reset manual playbook

> Run after any significant change or before declaring a feature "done".

#### 6.1 Full cold start

```bash
docker compose down -v          # wipe volumes including DB and MinIO
docker compose up --build -d    # rebuild all images, start fresh
docker compose logs migrator     # confirm "alembic upgrade head" ran without errors
```

| Check | Command | Expected |
|-------|---------|----------|
| Migrations ran | `docker compose logs migrator` | `INFO  [alembic.runtime.migration] Running upgrade ...` for each migration; process exits 0 |
| Bucket policy set | `docker compose exec minio mc anonymous get local/senda-documentos` (after setting `mc alias set local http://minio:9000 minioadmin minioadmin`) | `download` or `public` |
| API healthy | `curl http://localhost:8080/health` | `{"status":"ok"}` |
| Worker connected | `docker compose logs worker` | `celery@... ready.` |

**Expected:** All services healthy within 60s. `ensure_bucket_exists()` re-applies the policy on startup. `alembic upgrade head` is idempotent (no "already exists" errors).

#### 6.2 Worker kill during render

```bash
# Start a render (create a document with AST via the editor)
# Immediately after triggering render:
docker compose kill worker
# Wait 10s
docker compose start worker
```

| Check | Expected |
|-------|----------|
| `estado_render` after worker restart | `fallido` (retry exhausted) OR `listo` (if task was retried and succeeded) |
| `error_render` in DB | Non-null if `fallido` — not `NULL` |
| Worker logs on restart | `Retry` attempt visible; no event-loop `Future attached to a different loop` error |

#### 6.3 Migration idempotency

```bash
docker compose run --rm migrator alembic upgrade head   # second run
```

Expected: no errors, "Running upgrade" messages only for new (unapplied) migrations.

Full cycle test:
```bash
docker compose run --rm migrator alembic downgrade base
docker compose run --rm migrator alembic upgrade head
```

Expected: both commands exit 0. All tables re-created.

#### 6.4 Worker Dockerfile completeness

```bash
docker build --no-cache -f docker/Dockerfile.worker -t senda-worker-test .
docker run --rm senda-worker-test ls /app/_extensions/senda/
```

Expected: `_extension.yml` listed. If it's missing, a `COPY _extensions/ _extensions/` line is absent from the Dockerfile.

---

## System-Wide Impact

### Interaction Graph

The automated tests in Zone 2 trigger the full render pipeline:
`POST /documentos` → `render_documento.delay()` (Celery) → `serialize_document()` → `render_qmd()` → `upload_html()` → Redis pub/sub → WS close.

Any test that creates a document with an AST will trigger a real Celery task in the worker container. Tests must be written to tolerate async completion — never assert on `estado_render` synchronously after `POST`.

### Error Propagation

The render pipeline swallows exceptions into `estado_render = "fallido"`. The only way to observe errors is by reading `error_render` from the DB (via `GET /documentos/{id}`). Integration tests must assert on the DB state, not on task exit codes.

### State Lifecycle Risks

Integration tests create real DB rows and MinIO objects. Without explicit teardown, the DB accumulates test documents. The `created_document` and `rendered_document` fixtures handle teardown via `await client.delete(f"/documentos/{doc_id}")`. Verify that DELETE also removes the MinIO artifact (it does — `api/routers/documentos.py` calls `delete_object` in the delete handler).

### API Surface Parity

The `documentos`, `datasets`, and `retroalimentacion` routers currently have **no auth**. Integration tests must not add auth headers to those calls or the tests will break once auth is added (Phase 3 / todo #012). Document this explicitly as a known gap in each test file's module docstring.

---

## Acceptance Criteria

### Track A — Automated

- [ ] `api/tests/integration/` directory exists with `__init__.py`, `conftest.py`, `test_auth.py`, `test_documentos.py`
- [ ] `make test-int` runs all integration tests without manual setup
- [ ] All Zone 1 auth tests pass (happy path + 7 negative cases)
- [ ] `test_render_completes_with_minimal_ast` passes — confirms Celery, Quarto, MinIO pipeline end-to-end
- [ ] `test_render_artifact_is_publicly_accessible` passes — unauthenticated GET returns 200 (catches MinIO policy regression)
- [ ] `test_ast_exercise_block_roundtrip` passes — confirms editor AST round-trip regression doesn't recur
- [ ] `filterwarnings = ["error::RuntimeWarning"]` added to `pyproject.toml` — all 94 existing unit tests still pass
- [ ] `websockets` added to test dependencies in `pyproject.toml`

### Track B — Manual

- [ ] All Zone 3 execution scenarios (E1–E7, A1–A3, C1–C3) completed and outcomes noted
- [ ] All Zone 4 LLM feedback scenarios (F1–F6) completed
- [ ] All Zone 5 infrastructure reset scenarios (6.1–6.4) completed
- [ ] Any new bugs found during manual testing are filed and triaged

---

## Dependencies & Risks

| Dependency | Risk | Mitigation |
|------------|------|------------|
| `websockets` library (not yet a test dep) | Low — well-established library | Add to `[project.optional-dependencies] dev` in `pyproject.toml` |
| Render status WS race condition (task completes before WS subscription) | Medium — test may hang or time out | Implement polling fallback in `wait_for_render()`; verify server-side DB read-after-subscribe is present |
| `documentos` router has no auth | Low for now | Test without auth headers; add a module docstring noting this will need updating when auth is added |
| LLM service required for Zone 4 manual tests | Medium — may not be running | Test F6 explicitly covers the no-LLM fallback path; Zones 1-2 don't require it |
| Quarto render time in CI | Medium — renders take 10-30s | Use `timeout=90` on render fixture; consider a pre-built minimal QMD fixture that renders in <10s |
| Celery retry delay (10s × 3) | Low for passing tests, high for failure tests | For the render-failure test, use an AST that fails fast (invalid serialization, not a Quarto runtime error) |

---

## Implementation Order

1. Add `filterwarnings = ["error::RuntimeWarning"]` to `pyproject.toml` → run `make test` → confirm 94 tests still pass
2. Add `websockets` to test dependencies
3. Create `api/tests/integration/__init__.py` (empty)
4. Write `api/tests/integration/conftest.py`
5. Write `api/tests/integration/test_auth.py` — Zone 1
6. Run `make test-int` — confirm auth tests pass
7. Write `api/tests/integration/test_documentos.py` — Zone 2 (CRUD first, then render pipeline)
8. Run `make test-int` — confirm all integration tests pass
9. Execute Zone 3 manual playbook (student execution)
10. Execute Zone 4 manual playbook (LLM feedback)
11. Execute Zone 5 manual playbook (infrastructure reset)
12. File any new bugs found; update this plan with findings

---

## Sources & References

### Internal

- `docs/solutions/integration-issues/live-test-session-six-bugs-celery-quarto-minio-editor.md` — all 6 prior live-test bugs; Live-Test Checklist (steps 1-12)
- `docs/solutions/security-issues/unauthenticated-execution-endpoints-p1-fixes.md` — WS auth pattern; `access_token` in login body; WebSocket close code 4008
- `docs/solutions/test-failures/docker-pytest-async-mock-pitfalls.md` — `filterwarnings = error::RuntimeWarning`; coroutine-as-truthy silent passes; pytest working directory
- `docs/solutions/security-issues/fastapi-jwt-cookie-auth-review-cluster.md` — dual token delivery; bearer fallback in `get_current_user`; refresh token rotation test
- `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md` — WS pub/sub race condition; `accept()` before `close()`
- `api/tests/unit/test_auth_router.py` — reference for existing test patterns (`_test_app`, `dependency_overrides`, `_make_user`)
- `api/AGENTS.md` — unit tests in `api/tests/unit/`; integration tests in `api/tests/integration/`; `make test` vs `make test-int`
