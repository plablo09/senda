---
status: complete
priority: p3
issue_id: "035"
tags: [code-review, auth, api]
dependencies: []
---

# Add GET /auth/me Endpoint

## Problem Statement

The frontend has no way to hydrate the current user's identity after a page refresh, since tokens are httpOnly cookies that JavaScript cannot read. A teacher dashboard that needs to know whether the current user is a teacher or student must make a speculative request to a protected endpoint. `GET /auth/me` is the standard solution and also serves as the integration test vehicle for the full `get_current_user` dependency chain.

## Findings

- No `/auth/me` endpoint exists
- `api/dependencies/auth.py:CurrentUser` is fully implemented but never exercised by a real HTTP integration test
- Architecture reviewer: Finding 10 — frontend needs this for Phase 3 teacher-only UI surfaces
- Agent-native reviewer: also enables agents to confirm their auth state

## Proposed Solutions

### Option 1: Add GET /auth/me (Trivial)

```python
@router.get("/me", response_model=UsuarioResponse)
async def me(user: CurrentUser) -> Usuario:
    return user
```

**Effort:** 15 minutes (including test)
**Risk:** Low

## Recommended Action

Add in Phase 3 when the first teacher-only UI surface is built. Tag this as a dependency for the teacher dashboard work.

## Technical Details

**Affected files:**
- `api/routers/auth.py` — add `GET /me` endpoint
- `api/tests/unit/test_auth_router.py` — add test with valid cookie

## Acceptance Criteria

- [ ] `GET /auth/me` with valid `access_token` cookie returns `UsuarioResponse`
- [ ] `GET /auth/me` without cookie returns 401
- [ ] Test exercises the full `get_current_user` → DB lookup path

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
