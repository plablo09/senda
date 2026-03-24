---
status: pending
priority: p2
issue_id: "026"
tags: [code-review, architecture, auth]
dependencies: []
---

# Move JWT Decode Logic from Router into auth_service

## Problem Statement

`api/routers/auth.py` calls `jwt.decode` directly in `/logout` (line 96) and `/refresh` (line 113), importing the `jwt` library into the router layer. The service layer already owns all JWT mechanics (`verify_access_token`). The router knows about PyJWT exception types and the algorithm string — knowledge that belongs exclusively in the service. Additionally, `_ALGORITHM = "HS256"` is defined in `auth_service.py` but the router hardcodes the literal `"HS256"` without importing it.

## Findings

- `api/routers/auth.py:96,113`: `jwt.decode(token, settings.secret_key, algorithms=["HS256"])` — raw JWT decode in router
- `api/services/auth_service.py:17`: `_ALGORITHM = "HS256"` defined but not imported by router
- `api/routers/auth.py:114–121`: `except jwt.ExpiredSignatureError` / `except jwt.InvalidTokenError` — PyJWT exception types in router
- No `verify_refresh_token(token)` function exists in `auth_service.py` — the parallel to `verify_access_token` is missing
- Architecture reviewer: Dependency Inversion violation — router depends on concrete `jwt` library instead of service abstraction

## Proposed Solutions

### Option 1: Add verify_refresh_token to auth_service (Recommended)

**Approach:** Add `async def verify_refresh_token(token: str) -> dict` (or a typed `RefreshPayload`) to `auth_service.py`. Router calls this function instead of `jwt.decode` directly.

```python
# auth_service.py
class RefreshPayload(BaseModel):
    sub: str
    jti: str

async def verify_refresh_token(token: str) -> RefreshPayload:
    try:
        payload = await asyncio.to_thread(
            jwt.decode, token, settings.secret_key, algorithms=[_ALGORITHM]
        )
        return RefreshPayload(sub=payload["sub"], jti=payload["jti"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token de refresco expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token de refresco inválido")
```

**Pros:**
- Router is free of JWT knowledge
- Naturally resolves the `_ALGORITHM` duplication
- Also resolves todo-025 (async to_thread) if implemented together

**Cons:**
- Small increase in service surface (one new function)

**Effort:** 1 hour

**Risk:** Low

---

### Option 2: Just import _ALGORITHM (Minimal fix)

**Approach:** Import `_ALGORITHM` from `auth_service.py` in the router and replace the string literals. Leave the `jwt.decode` calls in place.

**Pros:**
- One-line import change

**Cons:**
- Does not fix the architectural violation (JWT knowledge still in router)

**Effort:** 15 minutes

**Risk:** Low

## Recommended Action

Option 1. Implement alongside todo-025 (async jwt.decode) since they touch the same code path.

## Technical Details

**Affected files:**
- `api/services/auth_service.py` — add `RefreshPayload` schema + `verify_refresh_token` function
- `api/routers/auth.py:94–121` — replace `jwt.decode` blocks with `await verify_refresh_token(token)` calls
- `api/tests/unit/test_auth_service.py` — add tests for `verify_refresh_token`

## Acceptance Criteria

- [ ] `api/routers/auth.py` does not import `jwt` directly
- [ ] `_ALGORITHM` appears only in `auth_service.py`
- [ ] `verify_refresh_token` is tested for expired, invalid, and valid token cases
- [ ] Router tests still pass

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
