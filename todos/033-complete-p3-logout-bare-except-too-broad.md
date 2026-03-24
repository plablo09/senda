---
status: complete
priority: p3
issue_id: "033"
tags: [code-review, quality, auth]
dependencies: []
---

# Narrow bare except Exception in /auth/logout

## Problem Statement

`/auth/logout` catches `except Exception: pass` when decoding the refresh token. This silently swallows all exceptions including DB connection failures and unexpected programming errors, making production debugging impossible.

## Findings

- `api/routers/auth.py:94–100`: `except Exception: pass` catches everything
- Intent is correct (proceed with cookie clearing even if token is invalid)
- But a DB error in `revoke_refresh_token` or an unexpected `AttributeError` would be silently discarded
- Python reviewer: P3-A

## Proposed Solutions

### Option 1: Narrow to expected exception types

```python
try:
    payload = jwt.decode(refresh_token, settings.secret_key, algorithms=["HS256"])
    await revoke_refresh_token(uuid.UUID(payload["jti"]), db)
except (jwt.InvalidTokenError, KeyError, ValueError):
    pass  # token already invalid or malformed — proceed with clearing cookies
```

**Effort:** 5 minutes
**Risk:** Low

## Recommended Action

Option 1. This becomes moot if todo-026 is implemented (JWT decode moves to service), but the narrowing is still worthwhile in the interim.

## Technical Details

**Affected files:**
- `api/routers/auth.py:94–100`

## Acceptance Criteria

- [ ] `except` clause catches only `jwt.InvalidTokenError`, `KeyError`, `ValueError`
- [ ] DB errors from `revoke_refresh_token` propagate normally

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
