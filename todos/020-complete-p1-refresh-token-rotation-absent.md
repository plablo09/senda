---
status: complete
priority: p1
issue_id: "020"
tags: [code-review, security, auth]
dependencies: []
---

# Implement Refresh Token Rotation on /auth/refresh

## Problem Statement

The `/auth/refresh` endpoint issues a new access token but leaves the existing `SesionRefresh` row and its cookie completely unchanged. The same refresh token can be used an unlimited number of times across its 7-day lifetime. A stolen refresh token gives an attacker persistent account access for up to 7 days with no ability for the legitimate user to detect or terminate the intrusion.

## Findings

- `api/routers/auth.py:138–146`: `/refresh` calls `create_access_token` and sets a new `access_token` cookie, but the old `SesionRefresh` row is never revoked and no new refresh token is issued
- `api/services/auth_service.py:65–70`: `revoke_refresh_token` exists and is fully implemented — it is simply not called from `/refresh`
- `api/services/auth_service.py:40–52`: `create_refresh_token` is also available and reusable
- The `revoked_at` field and `sesiones_refresh` table were designed for rotation; the infrastructure is complete
- Refresh token rotation also enables reuse-detection: presenting a revoked `jti` means a stolen token is in play — the correct response is to revoke all sessions for that user

## Proposed Solutions

### Option 1: Standard Rotation (Recommended)

**Approach:** On each `/refresh` call: (1) revoke old `jti`, (2) issue new refresh token via `create_refresh_token`, (3) set both new access token and new refresh token cookies via `_set_auth_cookies`.

**Pros:**
- Full rotation: every use of the refresh token produces a new one
- Reuse-detection becomes possible (revoked jti = potential theft)
- Existing `revoke_refresh_token` + `create_refresh_token` make this a ~5-line change

**Cons:**
- Clients that store the refresh token externally (agents) must update their stored token after each call

**Effort:** 1 hour

**Risk:** Low

---

### Option 2: Rotation + Theft Detection

**Approach:** Same as Option 1, but additionally: if a revoked `jti` is presented, revoke ALL sessions for that user_id.

**Pros:**
- Full protection against token theft scenarios
- Users can be notified of potential compromise

**Cons:**
- More complex; requires querying all sessions for a user
- May produce false positives for clients with retry logic

**Effort:** 3 hours

**Risk:** Medium

## Recommended Action

Implement Option 1 now (simple rotation). Option 2 can be added once the platform has user notification infrastructure. The fix is: call `revoke_refresh_token(jti, db)` then `create_refresh_token(user.id, db)` inside `/refresh`, and pass both tokens to `_set_auth_cookies`.

## Technical Details

**Affected files:**
- `api/routers/auth.py:138–146` — add revocation + new token issuance
- `api/tests/unit/test_auth_router.py` — update `test_refresh_valid_token_returns_new_access_token` to assert both cookies are set and old token is revoked

**Related components:**
- `api/services/auth_service.py` — `revoke_refresh_token`, `create_refresh_token` (no changes needed)

**Database changes:** None — schema already supports rotation

## Acceptance Criteria

- [ ] `/auth/refresh` revokes the presented `jti` before issuing a new access token
- [ ] `/auth/refresh` issues a new refresh token and sets it as a cookie
- [ ] Old refresh token cookie is replaced, not just left in place
- [ ] Test asserts that the presented jti is marked revoked in DB
- [ ] Test asserts that a new `sesiones_refresh` row is created
- [ ] Presenting a refresh token twice returns 401 on the second call

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)

**Actions:**
- Python reviewer, security reviewer, architecture reviewer, and agent-native reviewer all independently flagged this as P1
- Infrastructure (revoke + create functions) confirmed as already implemented

---

## Notes

- This is the single most important security gap in the current implementation
- The fix is small because the service layer already has all the pieces
