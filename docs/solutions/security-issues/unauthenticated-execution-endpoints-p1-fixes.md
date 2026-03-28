---
title: "Pre-Phase-3 Hardening: Four P1 Findings Fixed (Dead Imports, Unauthenticated Execution, Non-Idempotent Migration, Missing Login Token)"
category: security-issues
date: "2026-03-26"
tags:
  - authentication
  - rate-limiting
  - websocket
  - migration
  - dead-code
  - fastapi
  - alembic
  - jwt
  - docker
  - execution-sandbox
components:
  - api/tasks/render_task.py
  - api/routers/ejecutar.py
  - alembic/versions/0005_auth_db_constraints_and_updated_at_trigger.py
  - api/routers/auth.py
problem_type: "compound — security gap (unauthenticated endpoint), API contract defect (missing token in login response), migration reliability (non-idempotent trigger), code hygiene (dead inner imports)"
symptoms:
  - "POST /ejecutar and WS /ws/ejecutar accepted requests from unauthenticated callers, allowing 4 anonymous requests to exhaust all container execution slots"
  - "POST /auth/login returned only {mensaje} with no access_token, blocking any agent or CI flow that needed a bearer token from the response body"
  - "Migration 0005 failed with 'trigger already exists' on replay (CI snapshot restore, manual re-run) due to CREATE TRIGGER without OR REPLACE"
  - "render_task.py carried dead inner import block inside render_documento that was silently shadowed by module-level imports added later"
outcome: resolved
---

# Pre-Phase-3 Hardening: Four P1 Findings Fixed

Four P1 issues were identified during a 10-agent code review of `fix/pre-phase-3-hardening` (PR #7) before merging to main. All four were fixed and the branch was squash-merged at 94 tests passing.

---

## Root Cause Analysis

Each finding stems from an **incomplete migration during a refactoring pass**. Auth was bolted onto existing routes without auditing all entry points; imports were partially modernized leaving dead deferred blocks in place; migrations were written without idempotency or shared-resource awareness; and the login endpoint was written for browser clients without considering agents/CI that cannot read `HttpOnly` cookies.

---

## Investigation

- `render_task.py` had module-level imports added but the original deferred import block inside the function body was never cleaned up, causing the inner imports to silently shadow the outer ones.
- `/ejecutar` and `/ws/ejecutar` were found to have no `CurrentUser` dependency or rate limiting — every other router had been updated but these were missed.
- The Alembic migration for `usuarios` used `CREATE TRIGGER` (not `CREATE OR REPLACE TRIGGER`), meaning any replay raised "trigger already exists". The downgrade also contained `DROP FUNCTION IF EXISTS set_updated_at` that would destroy a shared function potentially used by future tables.
- `POST /auth/login` returned only `{"mensaje": "Sesión iniciada"}`, providing no programmatic path for agents or CI pipelines to retrieve the access token — they cannot read `HttpOnly` cookies.

---

## Solution

### Fix 1: Dead imports in `render_task.py`

Removed the stale deferred import block left inside `render_documento` after module-level imports were introduced. The inner block shadowed the module-level imports and was never executed via any distinct code path.

**Removed from inside `render_documento`:**
```python
from api.database import AsyncSessionLocal
from api.models.documento import Documento
from api.services.qmd_serializer import serialize_document
from api.services.renderer import render_qmd, RenderError
from api.services.storage import upload_html, ensure_bucket_exists
from sqlalchemy import select
```

---

### Fix 2: Unauthenticated `/ejecutar` endpoints

**HTTP endpoint** — added `CurrentUser` dependency and a rate limit:
```python
from api.dependencies.auth import CurrentUser
from api.limiter import limiter

@router.post("/ejecutar", response_model=EjecucionResponse)
@limiter.limit("30/minute")
async def ejecutar_http(
    request: Request, payload: EjecucionRequest, current_user: CurrentUser
) -> EjecucionResponse:
    ...
```

**WebSocket endpoint** — FastAPI's `Depends(get_current_user)` cannot be used cleanly on WebSocket routes because the dependency expects an HTTP `Request` object, not a `WebSocket`. Token extraction must be done manually:
```python
@router.websocket("/ws/ejecutar")
async def ejecutar(websocket: WebSocket):
    await websocket.accept()
    # Extract token from cookie or Authorization header
    token = websocket.cookies.get("access_token")
    if not token:
        auth_header = websocket.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        await websocket.close(code=4008)
        return
    try:
        await verify_access_token(token)
    except Exception:
        await websocket.close(code=4008)
        return
    # proceed with execution...
```

Key: WebSocket must `accept()` before it can `close()`. Use close code `4008` (Policy Violation) for auth failures.

---

### Fix 3: Non-idempotent `CREATE TRIGGER` and unsafe `DROP FUNCTION` in downgrade

**Upgrade** — changed bare `CREATE TRIGGER` to `CREATE OR REPLACE TRIGGER`:
```python
op.execute("""
    CREATE OR REPLACE TRIGGER usuarios_set_updated_at
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
""")
```

**Downgrade** — removed `DROP FUNCTION IF EXISTS set_updated_at` and documented the convention:
```python
def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS usuarios_set_updated_at ON usuarios;")
    # NOTE: set_updated_at() is a shared function intended for reuse across tables.
    # Do not drop it here — a future migration may have attached it to other tables.
    op.drop_constraint("ck_usuarios_rol", "usuarios", type_="check")
```

---

### Fix 4: Login response missing `access_token` for agent/CI bearer auth

Changed `POST /auth/login` to include the token in the response body while continuing to set the `HttpOnly` cookie for browser clients:
```python
# Before:
return {"mensaje": "Sesión iniciada"}

# After:
return {"mensaje": "Sesión iniciada", "access_token": access_token, "token_type": "bearer"}
```

The cookie handles browser clients; the body enables agents and CI pipelines.

---

## Key Technical Insights

- **FastAPI `Depends()` does not compose onto WebSocket routes** — `get_current_user` relies on `fastapi.Request`, which is not the same object as `fastapi.WebSocket`. WebSocket auth must be implemented manually by inspecting cookies or headers directly on the `WebSocket` object.

- **WebSocket protocol requires `accept()` before `close()`** — attempting to close a WebSocket that has not been accepted yet will silently fail or raise. Always call `await websocket.accept()` first, then close with a policy-violation code (4008) for auth failures.

- **`CREATE OR REPLACE TRIGGER` is the correct idempotency primitive for PostgreSQL triggers** — plain `CREATE TRIGGER` has no `IF NOT EXISTS` guard; `CREATE OR REPLACE TRIGGER` (added in PG 14) is the safe, replay-safe form.

- **Shared database functions must never be dropped in a table-scoped migration downgrade** — a migration targeting a single table has no visibility into whether a shared utility function (`set_updated_at`) is also attached to other tables added in later migrations. Dropping it in a downgrade creates a hidden cross-migration dependency that only surfaces during partial rollbacks.

- **Cookie-only login responses are hostile to non-browser clients** — `HttpOnly` cookies are intentionally inaccessible to JavaScript and completely invisible to CLI tools, CI pipelines, and agent runtimes. A login endpoint used by both browsers and automated clients must return the token in the JSON body as well; the two delivery mechanisms are not mutually exclusive.

---

## Prevention Strategies

### Dead Imports from Incomplete Refactors

- Enforce `ruff` or `flake8` with `F401` (unused import) and `F811` (redefined unused name) as CI-blocking checks. These rules catch exactly this class of error at zero cost.
- Adopt a single convention: either all imports are at module level, or they are all deferred. Mixed style invites partial migrations.
- When a PR says "refactor imports," treat every file touched as requiring a full import audit, not just the changed lines.

### Unauthenticated Endpoints

- Create a **dedicated WebSocket auth helper** and call it explicitly at the top of every WebSocket handler body — never via `Depends` on the route signature alone.
- For HTTP, enforce `dependencies=[Depends(get_current_user)]` at the **router level** for any router that handles mutations, so a missed `Depends` on a single route is still covered.
- Every new endpoint must have at least one test that sends a request with no credentials and asserts `401`/`403`.

### Non-Idempotent Alembic Migrations

- All `CREATE` statements for triggers, functions, types, and sequences must use `CREATE OR REPLACE` or `IF NOT EXISTS`. Add a pre-commit check that greps for bare `CREATE TRIGGER` or `CREATE FUNCTION` inside `alembic/versions/`.
- For `downgrade()`, use `DROP ... IF EXISTS`. For shared functions, add a reference comment and never drop a function in a downgrade unless you own all callers.
- Add a CI job: `alembic upgrade head && alembic downgrade base && alembic upgrade head`. Catches non-idempotency and broken downgrades in every PR.

### Auth Endpoint Token Contract

- Define a canonical `TokenResponse` Pydantic model with `access_token: str` and `token_type: str`. All login/refresh endpoints must return this model in the JSON body *in addition to* setting the cookie.
- Declare `response_model=TokenResponse` on the route so Pydantic enforces the contract at serialization time.
- Write a test that calls login, ignores all `Set-Cookie` headers, and asserts `response.json()["access_token"]` is non-empty.

---

## Review Checklist

- [ ] `ruff check --select F401,F811` passes on all changed Python files
- [ ] Every `@router.websocket` handler calls the WebSocket auth helper as its first substantive statement
- [ ] Every new router that performs mutations declares `dependencies=[Depends(get_current_user)]` at router construction
- [ ] All `CREATE` DDL in `alembic/versions/` uses `OR REPLACE` or `IF NOT EXISTS`
- [ ] All `DROP` DDL in migration downgrades uses `IF EXISTS`; shared functions are never dropped
- [ ] Login and refresh endpoints return `access_token` in the JSON body (not only in a cookie)
- [ ] Every new endpoint has at least one unauthenticated test asserting `401`/`403`

---

## Test Cases to Add

- `test_no_unused_imports` — Run `ruff check --select F401,F811 .` as a subprocess; assert exit 0.
- `test_websocket_rejects_missing_token` — Open WS connection without a token; assert close code 4008.
- `test_websocket_rejects_invalid_token` — Send a malformed JWT; assert close code 4008.
- `test_http_execution_endpoint_no_credentials` — `POST /ejecutar` with no auth; assert `401`.
- `test_migration_upgrade_downgrade_upgrade` — Run full migration sequence twice; assert no exceptions.
- `test_login_returns_access_token_in_body` — Login, ignore cookies, assert `access_token` in `response.json()`.

---

## Cross-References

- `docs/solutions/security-issues/fastapi-jwt-cookie-auth-review-cluster.md` — Bearer token fallback in `get_current_user` (Issue 3); rate limiting with `slowapi` (Issue 12)
- `docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md` — WebSocket race conditions and timeout fallback patterns (Issue 6)
- `docs/solutions/database-issues/alembic-asyncpg-fastapi-migration-foundation.md` — Dual-engine URL pattern, `server_default` requirements, migration structure; mentions `set_updated_at()` as a reusable trigger function (partial coverage — no idempotency guard docs yet)
- `docs/solutions/security-issues/phase-3-llm-guidance-pre-merge-review-fixes.md` — Execution pool concurrency with `asyncio.Semaphore`; session identity and cookie vs. localStorage separation

**Potential refresh candidate:** `alembic-asyncpg-fastapi-migration-foundation.md` mentions the `set_updated_at()` trigger function pattern but does not document the `CREATE OR REPLACE TRIGGER` idempotency requirement or the shared-function downgrade safety rule. Consider adding a "Database Triggers" section to that doc.
