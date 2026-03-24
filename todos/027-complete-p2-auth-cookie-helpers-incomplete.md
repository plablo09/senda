---
status: complete
priority: p2
issue_id: "027"
tags: [code-review, security, auth]
dependencies: []
---

# Fix Two Cookie Helper Gaps: /refresh and _clear_auth_cookies

## Problem Statement

Two related gaps in cookie management create silent divergence risks:

1. `/auth/refresh` sets the access token cookie inline (8 lines, duplicated from `_set_auth_cookies`) instead of using the helper.
2. `_clear_auth_cookies` calls `delete_cookie` without matching the `secure`, `httponly`, and `samesite` attributes used when setting cookies — in production (`cookie_secure=True`), the delete may fail to clear the cookie in some browsers.

## Findings

- `api/routers/auth.py:139–146`: inline `response.set_cookie(key="access_token", ...)` duplicates `_set_auth_cookies` policy
- `api/routers/auth.py:31–45`: `_set_auth_cookies` uses `_COOKIE_KWARGS` + `settings.cookie_secure`; the inline block repeats these manually
- `api/routers/auth.py:48–51`: `_clear_auth_cookies` calls `response.delete_cookie("access_token")` and `response.delete_cookie("refresh_token")` with no matching cookie attributes
- RFC 6265: browsers require `Path`, `Domain`, and `Secure` to match between the Set-Cookie that set a cookie and the Set-Cookie used to clear it; a `Secure` mismatch in production leaves the original cookie in place
- Security reviewer: F-06 (medium) — users may believe they have logged out but browser still sends old cookies

## Proposed Solutions

### Option 1: Extract _set_access_cookie helper + fix _clear_auth_cookies (Recommended)

**Approach:**
```python
def _set_access_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        secure=settings.cookie_secure,
        **_COOKIE_KWARGS,
    )

def _set_auth_cookies(response, access_token, refresh_token):
    _set_access_cookie(response, access_token)
    response.set_cookie(key="refresh_token", ...)  # unchanged

def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie("refresh_token", secure=settings.cookie_secure, httponly=True, samesite="lax")
```

**Pros:**
- Single place for access token cookie policy
- Clear cookies correctly mirror set attributes
- Also enables todo-020 (refresh rotation) to call `_set_auth_cookies` cleanly

**Cons:**
- Minor refactor

**Effort:** 30 minutes

**Risk:** Low

## Recommended Action

Option 1. Do this alongside todo-020 (refresh token rotation) since that todo also needs to call the cookie helpers.

## Technical Details

**Affected files:**
- `api/routers/auth.py:31–51` — extract helper, fix `_clear_auth_cookies`
- `api/routers/auth.py:139–146` — replace inline block with helper call

## Acceptance Criteria

- [ ] `/auth/refresh` uses `_set_access_cookie` or `_set_auth_cookies` — no inline `set_cookie` calls
- [ ] `_clear_auth_cookies` passes `secure=settings.cookie_secure, httponly=True, samesite="lax"` to both `delete_cookie` calls
- [ ] Cookie policy is defined in exactly one place per cookie type

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
