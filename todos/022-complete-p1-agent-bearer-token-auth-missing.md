---
status: complete
priority: p1
issue_id: "022"
tags: [code-review, agent-native, auth]
dependencies: []
---

# Add Bearer Token Auth Alongside Cookie Auth

## Problem Statement

All auth uses httpOnly cookies exclusively. No LLM agent runtime (Claude Code, CI pipelines, test scripts) can read httpOnly cookies or forward them. Once Phase 4 wires `require_teacher`/`require_student` onto existing routers, agents will lose access to the entire authenticated API surface. Currently 8/8 non-auth endpoints are accessible; post-Phase 4 this drops to 0/8 without a fix.

## Findings

- `api/dependencies/auth.py:17`: `token = request.cookies.get("access_token")` — only source of credentials
- `api/routers/auth.py:87`: login returns `{"mensaje": "Sesión iniciada"}` with no token in the body — agents cannot extract the access token even if they could call login
- `api/routers/documentos.py`, `api/routers/datasets.py`: currently unprotected; will gain `require_teacher` in Phase 4
- Agent-native reviewer: 4/10 auth capabilities accessible today; will drop to ~0 after Phase 4 without this fix

## Proposed Solutions

### Option 1: Bearer header fallback in get_current_user + token in login body (Recommended)

**Approach:** Modify `get_current_user` to try cookie first, then `Authorization: Bearer <token>` header. Modify `POST /auth/login` to include the access token in the JSON response body alongside the cookie.

```python
# dependencies/auth.py
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
    ...
```

```python
# routers/auth.py — login response
return {"mensaje": "Sesión iniciada", "access_token": access_token, "token_type": "bearer"}
```

**Pros:**
- Non-breaking: browsers continue using cookies; agents use Bearer header
- Single `get_current_user` change propagates to all protected routes automatically
- Standard OAuth2 pattern, works with FastAPI's OpenAPI docs

**Cons:**
- Access token in response body is visible to JavaScript (not httpOnly) — acceptable since it's the same token and expires in 15 minutes

**Effort:** 2 hours

**Risk:** Low

---

### Option 2: Separate agent-only endpoints with API keys

**Approach:** Add a `ApiKey` model and a separate auth path (`Authorization: ApiKey <key>`) for service accounts.

**Pros:**
- Long-lived credentials without rotation overhead
- Clean separation of human vs agent auth

**Cons:**
- More complex infrastructure
- Overkill for current needs

**Effort:** 1–2 days

**Risk:** Medium

## Recommended Action

Option 1 before Phase 4's first `require_teacher` guard ships. The change is local to `get_current_user` and the login response — no per-route changes needed.

## Technical Details

**Affected files:**
- `api/dependencies/auth.py` — add `HTTPBearer` fallback
- `api/routers/auth.py:87` — add token to login JSON response
- `api/tests/unit/test_auth_router.py` — add test for Bearer header auth path

**Related components:**
- All future protected routers (documentos, datasets, retroalimentacion) benefit automatically

## Acceptance Criteria

- [ ] `GET /documentos` (once protected) returns 200 with `Authorization: Bearer <token>` header
- [ ] `GET /documentos` returns 200 with `access_token` cookie as before
- [ ] `POST /auth/login` response body includes `access_token` and `token_type`
- [ ] Test covers the Bearer header path through `get_current_user`
- [ ] Existing cookie-based tests still pass unchanged

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)

**Actions:**
- Agent-native reviewer flagged as P1; confirmed by architecture reviewer
- Fix is isolated to one dependency function + one login response change
