---
status: complete
priority: p1
issue_id: "025"
tags: [code-review, performance, auth]
dependencies: []
---

# Wrap jwt.decode in asyncio.to_thread in verify_access_token

## Problem Statement

`verify_access_token` in `auth_service.py` calls `jwt.decode` synchronously from an async route handler without `asyncio.to_thread`. Every authenticated request blocks the event loop for the duration of HMAC-SHA256 signature verification + JSON parsing. This is on the hot path for every protected endpoint — far more frequent than bcrypt — yet bcrypt is correctly wrapped while JWT verification is not.

## Findings

- `api/services/auth_service.py:55–62`: `jwt.decode(token, ...)` called synchronously; no `to_thread` wrapper
- `api/services/auth_service.py:21,26`: `bcrypt.hashpw` and `bcrypt.checkpw` are correctly wrapped in `asyncio.to_thread` — JWT should follow the same pattern
- `api/dependencies/auth.py:20`: `verify_access_token(token)` called directly from async `get_current_user`
- Under concurrent load (e.g., 100 students submitting code simultaneously), 100 `jwt.decode` calls serialize on one event loop thread, blocking all other coroutines waiting on that thread

## Proposed Solutions

### Option 1: Make verify_access_token async with to_thread (Recommended)

**Approach:** Change `verify_access_token` to `async def` and wrap the `jwt.decode` call:

```python
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
```

**Pros:**
- Consistent with bcrypt pattern already in the codebase
- Non-blocking event loop on every authenticated request
- One-line change to the function signature

**Cons:**
- All callers must `await` the function (currently 1 call site: `dependencies/auth.py:20`)
- Test in `test_auth_service.py` must become async

**Effort:** 30 minutes

**Risk:** Low

---

### Option 2: Workaround — multiple Uvicorn workers

**Approach:** Run `uvicorn --workers N` to distribute load across separate processes, each with its own event loop.

**Pros:**
- No code change

**Cons:**
- Does not eliminate per-request blocking within a single worker
- Not a fix, just a mitigation

**Effort:** 0 (config change only)

**Risk:** Low (acceptable as short-term workaround)

## Recommended Action

Option 1 — make `verify_access_token` async. The change is minimal and consistent with the existing bcrypt pattern.

## Technical Details

**Affected files:**
- `api/services/auth_service.py:55` — change to `async def`, add `await asyncio.to_thread`
- `api/dependencies/auth.py:20` — add `await` to the call
- `api/tests/unit/test_auth_service.py` — `test_create_and_verify_access_token` and related tests must be `async`

## Acceptance Criteria

- [ ] `verify_access_token` is `async def`
- [ ] `jwt.decode` is wrapped in `asyncio.to_thread`
- [ ] `get_current_user` awaits `verify_access_token`
- [ ] All existing tests pass
- [ ] Test for `verify_access_token` uses `@pytest.mark.asyncio`

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)

**Actions:**
- Performance reviewer flagged as P1; confirmed by Python reviewer comparison with bcrypt pattern
