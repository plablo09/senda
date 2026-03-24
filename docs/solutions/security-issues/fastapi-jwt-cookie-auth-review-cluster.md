---
title: "Phase 2 JWT Cookie Auth Code Review: 16 Issues Across Auth Layer (FastAPI + SQLAlchemy 2.0)"
category: "security-issues"
date: "2026-03-23"
tags:
  - jwt
  - authentication
  - fastapi
  - sqlalchemy
  - security-review
  - refresh-tokens
  - bcrypt
  - httponly-cookies
  - alembic
  - postgresql
problem_type: "multi-issue code review — security gaps, blocking I/O, schema defects, missing token lifecycle management"
components:
  - "api/services/auth_service.py"
  - "api/routers/auth.py"
  - "api/dependencies/auth.py"
  - "api/models/usuario.py"
  - "api/models/sesion_refresh.py"
  - "alembic/versions/0002_add_usuarios_and_refresh_sessions.py"
symptoms:
  - "refresh token not rotated on use — stolen token valid for full 7-day window"
  - "teacher role self-assignable at registration — no privileged role gating"
  - "httpOnly cookie-only auth blocks agent and CI Bearer token flows"
  - "duplicate unique index in migration (UniqueConstraint + explicit create_index on same columns)"
  - "sesiones_refresh table grows unbounded — no expired row cleanup"
  - "jwt.decode called on event loop without asyncio.to_thread — blocks async worker"
---

# FastAPI JWT Cookie Auth — Code Review Cluster (Phase 2)

8 review agents ran in parallel against the Phase 2 authentication layer (452 lines added, 19 unit tests). 16 issues surfaced across 6 categories. This document captures all findings, fixes, and the prevention framework so future auth implementations and reviewers know what to look for.

---

## Root Cause Summary

The auth implementation has correct structural foundations — bcrypt is offloaded correctly, uniform error messages are used for most paths, JWT is validated properly, and the DB-backed `jti` scheme gives real revocability. However, several integration gaps exist where the scaffolded pieces were not wired together: refresh token rotation was implemented in the service layer but never called from the router, Bearer auth was omitted leaving all non-browser clients locked out, and a migration error creates redundant unique indexes.

Additionally, several systemic issues exist around scalability (unbounded session table growth, synchronous JWT decoding in async handlers) and hardening (no rate limiting, missing DB-level constraints, open teacher self-registration). Security properties must be enforced at every layer independently — ORM validation does not substitute for DB constraints, and router-layer checks do not substitute for service-layer invariants.

---

## P1 Issues and Fixes (Blocks Merge)

### 1. Refresh Token Rotation Absent

**Root cause:** `/auth/refresh` validates the existing `jti` but never calls `revoke_refresh_token` + `create_refresh_token`. The same refresh token is valid for its entire 7-day lifetime.

**Fix** — in `routers/auth.py`, after session/user validation:

```python
# After confirming the session is valid and user is active:
await revoke_refresh_token(jti, db)
new_refresh_token, _ = await create_refresh_token(user.id, db)
new_access_token = create_access_token(user.id, user.rol)
_set_auth_cookies(response, new_access_token, new_refresh_token)
return {"mensaje": "Token renovado"}
```

The infrastructure (`revoke_refresh_token`, `create_refresh_token`, `_set_auth_cookies`) already exists — ~5-line addition.

---

### 2. Open Teacher Self-Registration

**Root cause:** `UsuarioCreate` accepts `rol: Literal["teacher", "student"]` and `/registro` is unauthenticated — anyone can self-assign the teacher role.

**Fix** — remove `rol` from `UsuarioCreate`, hardcode `"student"` in the endpoint:

```python
# schemas/auth.py
class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # rol removed — always set to "student" by the endpoint

# routers/auth.py — /registro
user = Usuario(email=payload.email, hashed_password=hashed_pw, rol="student")
```

First teacher account: provision via a separate admin-gated endpoint or direct DB insert during initial setup.

---

### 3. No Bearer Token Auth — Agents and CI Locked Out

**Root cause:** `get_current_user` reads exclusively from `request.cookies.get("access_token")`. httpOnly cookies are inaccessible to non-browser HTTP clients. Once Phase 4 adds `require_teacher`/`require_student` to existing routers, all 8 current endpoints become unreachable to agents and automation.

**Fix** — add `HTTPBearer` fallback in `api/dependencies/auth.py`:

```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    db: DbDep,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Usuario:
    token = request.cookies.get("access_token")
    if not token and bearer:
        token = bearer.credentials
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    # rest unchanged
```

Also return the access token in the `/login` JSON response body so agents can capture it:

```python
return {"mensaje": "Sesión iniciada", "access_token": access_token, "token_type": "bearer"}
```

Browser clients continue using the cookie; agents use the Bearer header. Single `get_current_user` change propagates to all protected routes automatically.

---

### 4. Migration Double Unique Index

**Root cause:** `create_table` contains both `sa.UniqueConstraint("email")` and a separate `op.create_index("ix_usuarios_email", ..., unique=True)` — PostgreSQL creates two distinct unique indexes on the same column. Same pattern on `sesiones_refresh.jti`.

**Fix** — remove the inline `UniqueConstraint` from both `create_table` calls; keep only the named `create_index` calls:

```python
# In alembic/versions/0002_add_usuarios_and_refresh_sessions.py
# Remove these two lines:
# sa.UniqueConstraint("email"),        ← from create_table("usuarios")
# sa.UniqueConstraint("jti"),          ← from create_table("sesiones_refresh")

# Keep only the named indexes:
op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)
op.create_index("ix_sesiones_refresh_jti", "sesiones_refresh", ["jti"], unique=True)
```

Since the DB is greenfield, amend migration 0002 directly and wipe-and-remigrate dev environments.

**Verification SQL:**
```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('usuarios', 'sesiones_refresh')
ORDER BY tablename, indexname;
-- Should show exactly one unique index per column, not two
```

---

### 5. `sesiones_refresh` Grows Without Bound

**Root cause:** Every login inserts one row. Logout marks `revoked_at` but never deletes. No cleanup job exists. Projection: ~1.8M rows at 5k DAU after one year — B-tree index pages spill to disk.

**Fix — Part A:** Add `expires_at` index in migration 0003:

```python
op.create_index("ix_sesiones_refresh_expires_at", "sesiones_refresh", ["expires_at"])
```

**Fix — Part B:** Add a Celery beat cleanup task:

```python
# api/tasks/cleanup.py
@celery_app.task
def purge_expired_sessions() -> None:
    """Delete expired and revoked refresh sessions."""
    with SyncSessionLocal() as db:
        db.execute(
            delete(SesionRefresh).where(
                (SesionRefresh.expires_at < datetime.now(UTC)) |
                (SesionRefresh.revoked_at.isnot(None))
            )
        )
        db.commit()

# Register in Celery beat schedule (e.g., every 6 hours)
```

---

### 6. `verify_access_token` Blocks the Event Loop

**Root cause:** `jwt.decode` is synchronous CPU-bound work called directly from async handlers without `asyncio.to_thread`. `bcrypt` is correctly wrapped; JWT is not. This is on the hot path for every authenticated request.

**Fix** — make `verify_access_token` async and wrap `jwt.decode`:

```python
# api/services/auth_service.py
async def verify_access_token(token: str) -> TokenPayload:
    try:
        payload = await asyncio.to_thread(
            jwt.decode, token, settings.secret_key, algorithms=[_ALGORITHM]
        )
        return TokenPayload(sub=payload["sub"], rol=payload["rol"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

# api/dependencies/auth.py
payload = await verify_access_token(token)   # add await
```

---

## P2 Issues and Fixes (Should Fix)

### 7. JWT Decode Logic in Router Layer

The router calls `jwt.decode` directly in `/logout` and `/refresh`, importing `jwt` into the router and duplicating the `_ALGORITHM` constant as a string literal.

**Fix:** Extract `verify_refresh_token(token: str) -> str` in `auth_service.py`. Router calls the service function; router never imports `jwt`.

---

### 8. Cookie Helper Consistency Gaps

Two gaps: (a) `/auth/refresh` sets the access cookie inline bypassing `_set_auth_cookies`; (b) `_clear_auth_cookies` calls `delete_cookie` without matching `secure`/`samesite` attributes — logout may silently fail to clear cookies in production when `cookie_secure=True`.

**Fix:**

```python
def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        "access_token", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(
        "refresh_token", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )

# /refresh endpoint — replace inline set_cookie block with:
_set_auth_cookies(response, new_access_token, new_refresh_token)
```

---

### 9. `DbDep` Defined in Four Files

`Annotated[AsyncSession, Depends(get_db)]` is copy-pasted into `routers/auth.py`, `dependencies/auth.py`, `routers/documentos.py`, and `routers/datasets.py`.

**Fix:** Define once in `api/database.py` alongside `get_db`; import everywhere else.

---

### 10. `rol` Has No DB-Level Constraint + Email Not Validated

`rol` is `String(10)` with no `CHECK` constraint — invalid values stored silently via direct DB writes or bulk updates. `email` accepts arbitrary strings like `"notanemail"`.

**Fix:**

```python
# In migration 0003:
op.execute(
    "ALTER TABLE usuarios "
    "ADD CONSTRAINT ck_usuarios_rol CHECK (rol IN ('teacher', 'student'))"
)

# In schemas/auth.py:
from pydantic import EmailStr
class UsuarioCreate(BaseModel):
    email: EmailStr   # replaces str
```

Add `email-validator>=2.0` to `api/pyproject.toml`.

---

### 11. `is_active` Checked After bcrypt (Timing Oracle + Waste)

`is_active` check runs after `verify_password`. An inactive user with a correct password burns 100ms on bcrypt, then returns `"Cuenta inactiva"` — directly revealing that the correct password was supplied.

**Fix — reorder and normalize message:**

```python
user = result.scalar_one_or_none()
if not user or not user.hashed_password or not user.is_active:
    raise HTTPException(status_code=401, detail="Credenciales inválidas")
if not await verify_password(payload.password, user.hashed_password):
    raise HTTPException(status_code=401, detail="Credenciales inválidas")
```

---

### 12. No Rate Limiting on Auth Endpoints

No rate limiting on `/login`, `/registro`, `/refresh`, or `/logout`. Redis is already in the stack.

**Fix** using `slowapi`:

```python
# api/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# api/routers/auth.py
@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, ...): ...

@router.post("/registro")
@limiter.limit("5/minute")
async def registro(request: Request, ...): ...
```

---

### 13. `updated_at` Has No DB Trigger

`onupdate=lambda: datetime.now(UTC)` fires only on ORM flush. Bulk `UPDATE` statements and direct SQL leave `updated_at` stale silently.

**Fix** — add in migration 0003:

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER usuarios_set_updated_at
BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

The `set_updated_at()` function is reusable for any future table with `updated_at`.

---

## P3 Issues (Nice to Have)

- **`except Exception: pass` in `/logout`** — narrow to `except (jwt.InvalidTokenError, KeyError, ValueError)` so DB failures propagate
- **`dependency_overrides.clear()` in tests** — use an `autouse` fixture with `yield` instead of manual `.clear()` calls that are skipped on test failure
- **No `GET /auth/me`** — trivial addition needed for frontend user hydration post page refresh; also validates the full `get_current_user` dependency chain as an integration test

---

## Auth Implementation Checklist

Apply this checklist on every PR that touches auth:

### Security
- [ ] Refresh token rotation: issuing a new refresh token invalidates the previous one (atomic revoke + create)
- [ ] Teacher/admin role assignment requires out-of-band gate — self-registration assigns `"student"` only
- [ ] `is_active` check occurs **before** bcrypt comparison
- [ ] `logout` clears cookies with **identical** attributes to those used during `set`
- [ ] Rate limiting applied to `/login`, `/registro`, `/refresh`
- [ ] All auth failures return the same error message and status code (no state leakage)

### Token & Cookie Handling
- [ ] `jwt.decode` wrapped in `asyncio.to_thread`
- [ ] `_set_auth_cookies` called in **every** token-issuing endpoint — no inline `set_cookie` anywhere
- [ ] Bearer token fallback (`Authorization: Bearer`) supported alongside cookie auth
- [ ] Token expiry values sourced from config, not hardcoded

### Database & Migration
- [ ] No `UniqueConstraint` + `create_index` on the same column in the same migration
- [ ] `rol` (or any enum-like column) has a `CHECK` constraint or PostgreSQL `ENUM`
- [ ] Every FK column has an explicit index
- [ ] `updated_at` maintained by DB trigger, not ORM hook only
- [ ] Cleanup job or TTL policy exists for session rows

### Architecture
- [ ] JWT decode/validation lives in `auth_service.py` — router does not import `jwt`
- [ ] `DbDep` defined in one file; confirmed by `grep -rn "DbDep\s*=" | wc -l == 1`
- [ ] No business logic in routers

---

## Testing Requirements

| Bug Class | Test Type | Key Assertion |
|---|---|---|
| Token reuse after rotation | Unit + Integration | Old token → 401 on second use |
| Role escalation via registration | Unit | DB `rol` == `"student"` regardless of input |
| Timing oracle (`is_active`) | Unit (monkeypatch bcrypt) | bcrypt never called for inactive user |
| Cookie clear mismatch | Unit (response headers) | Attribute-by-attribute header comparison |
| Missing rate limit | Integration | 429 before N+1 requests |
| Event loop blocking | Concurrency test | p99 latency stable under 50 concurrent requests |
| Duplicate index | Migration lint CI | Script flags UniqueConstraint + create_index on same column |
| Unbounded session table | Integration | Row count after cleanup job run |

---

## Architectural Patterns to Establish

1. **Single `DbDep` source** — `api/database.py` only; CI grep assertion rejects duplicates
2. **Cookie helper contract** — `_set_auth_cookies` and `_clear_auth_cookies` are the only permitted locations for cookie construction; unit test asserts attribute symmetry between them
3. **Layered auth** — Router → Service (`auth_service.py`) → Core (`jwt` library). Router never imports `jwt`. Enforced by an AST/import check.
4. **Migration review protocol** — Lint script flags any column in both `UniqueConstraint` and `create_index`; checklist confirms CHECK constraints on enum-like columns and indexes on FK columns
5. **Role assignment via explicit allowlist** — `SELF_ASSIGNABLE_ROLES = {"student"}` constant; elevated roles assigned only through privileged endpoint
6. **Refresh token rotation as atomic unit** — Extract `rotate_refresh_token(old_jti, user_id, db)` service function; the only permitted way to issue a refresh token after initial login

---

## Related Documentation

- [`docs/solutions/database-issues/alembic-asyncpg-fastapi-migration-foundation.md`](../database-issues/alembic-asyncpg-fastapi-migration-foundation.md) — dual-engine URL pattern; `server_default` requirement; "Adding a New Model" checklist — verify `usuario.py` and `sesion_refresh.py` are imported in `alembic/env.py`
- [`docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md`](../runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md) — lambda wrapping for `DateTime` defaults; `asyncio.to_thread` vs `run_in_executor` (bcrypt pattern that JWT should mirror)
- [`docs/solutions/security-issues/phase-3-llm-guidance-pre-merge-review-fixes.md`](phase-3-llm-guidance-pre-merge-review-fixes.md) — Cluster 1: async task boundary (db sessions must not cross task boundaries); Cluster 4: localStorage vs sessionStorage vs httpOnly cookies — rationale for cookie-only auth
- [`docs/solutions/security-issues/fastapi-upload-qmd-websocket-security-cluster.md`](fastapi-upload-qmd-websocket-security-cluster.md) — Issue 5: commit-before-notify ordering applies to `create_refresh_token` and logout flows
- [`docs/solutions/runtime-errors/docker-compose-stack-startup-failures.md`](../runtime-errors/docker-compose-stack-startup-failures.md) — `service_completed_successfully` for migrator; migration `0002` depends on this startup pattern
