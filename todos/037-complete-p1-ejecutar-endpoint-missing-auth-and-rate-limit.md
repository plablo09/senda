---
status: pending
priority: p1
issue_id: "037"
tags: [code-review, security, auth, rate-limiting, ejecutar]
dependencies: []
---

# Add Auth + Rate Limit to `POST /ejecutar` and `WS /ws/ejecutar`

## Problem Statement

The newly added `POST /ejecutar` HTTP endpoint and the pre-existing `WS /ws/ejecutar` WebSocket endpoint both expose the Docker code execution pool to any anonymous caller with network access to the API. The execution pool has only 4 total container slots (2 Python + 2 R). Four simultaneous unauthenticated requests can exhaust the pool and block all legitimate users for up to the full execution duration. There is no per-run timeout enforced (see todo 042).

## Findings

- `api/routers/ejecutar.py:12` — `POST /ejecutar` has no `CurrentUser` dependency and no `@limiter.limit()` decorator
- `api/routers/ejecutar.py:23` — `WS /ws/ejecutar` has no authentication check
- `api/routers/ejecutar.py:33-35` — WebSocket accepts raw JSON with `payload.get("language", "python")` — no schema validation, no auth
- `api/schemas/ejecutar.py:10` — `code: str = Field(max_length=50000)` is the only guard
- All auth endpoints use `@limiter.limit(...)` + `CurrentUser`; `/ejecutar` has neither
- `api/config.py:38` — `exec_timeout_seconds = 30` exists but is never read in `execution_pool.py`
- Confirmed by: security-sentinel (C-1, C-2), architecture-strategist (Issue A), agent-native-reviewer (Critical #1), initial kieran-review

## Proposed Solutions

### Option 1: Add CurrentUser + rate limit to both endpoints (Recommended)

Add `current_user: CurrentUser` dependency to `ejecutar_http`. Add `@limiter.limit("30/minute")` decorator. For the WebSocket endpoint, call `get_current_user` explicitly at the start of the handler using the cookie/bearer from the request headers.

**Pros:** Consistent with all other resource-intensive endpoints; blocks unauthenticated pool exhaustion; any authenticated user (student or teacher) can execute
**Cons:** Agents must log in first to get a token (already supported by bearer fallback in `get_current_user`)
**Effort:** 30 minutes
**Risk:** Low

### Option 2: Rate-limit only (no auth)

Add `@limiter.limit("5/minute")` per IP without requiring auth.

**Pros:** No breaking change for anonymous callers during development
**Cons:** Bypassable by rotating IPs; does not stop pool exhaustion from a single determined caller; inconsistent with security posture of Phase 3
**Effort:** 10 minutes
**Risk:** Medium — still leaves the endpoint unauthenticated

## Recommended Action

Option 1 before this branch merges. The login endpoint already returns a bearer token via cookie; `get_current_user` already has the bearer header fallback. The change is local to `ejecutar.py` and should also validate the WebSocket `language` field using `EjecucionRequest` rather than raw `payload.get()`.

## Technical Details

**Affected files:**
- `api/routers/ejecutar.py:12-21` — add `current_user: CurrentUser` + `@limiter.limit()`
- `api/routers/ejecutar.py:23-56` — add auth check at WebSocket handler start; validate language via `EjecucionRequest`

## Acceptance Criteria

- [ ] `POST /ejecutar` without auth returns 401
- [ ] `POST /ejecutar` with valid bearer token returns 200
- [ ] `POST /ejecutar` at > N requests/minute from same IP returns 429
- [ ] WebSocket `/ws/ejecutar` without auth closes with 4008 or equivalent
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)

**Actions:**
- Flagged by security-sentinel as C-1/C-2, architecture-strategist as Issue A, agent-native-reviewer as Critical #1
- Confirmed: no `CurrentUser`, no `@limiter.limit` on either execution endpoint
