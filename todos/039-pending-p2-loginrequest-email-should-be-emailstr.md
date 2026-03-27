---
status: pending
priority: p2
issue_id: "039"
tags: [code-review, schema, validation, auth]
dependencies: []
---

# `LoginRequest.email` Should Use `EmailStr` Not `str`

## Problem Statement

`UsuarioCreate.email` was upgraded to `EmailStr` on this branch. `LoginRequest.email` in the same file (`api/schemas/auth.py:25`) remains `str`. This inconsistency means a client can attempt login with a structurally invalid email (e.g., `"not-an-email"`) and the request passes schema validation, hits the database for a lookup, and returns a 401 instead of a 422. Beyond the wasted DB roundtrip, it is confusing that the same email field has different constraints on registration vs. login.

## Findings

- `api/schemas/auth.py:7` — `UsuarioCreate.email: EmailStr = Field(max_length=320)` — validated
- `api/schemas/auth.py:25` — `LoginRequest.email: str = Field(max_length=320)` — not validated
- Both fields represent the same domain concept (user email address)
- `email-validator>=2.0` is already in `pyproject.toml` — no new dependency needed
- Confirmed by: security-sentinel (medium), kieran-python-reviewer (medium), architecture-strategist (Issue D), initial kieran-review

## Proposed Solutions

### Option 1: Change `LoginRequest.email` to `EmailStr` (Recommended)

One-line change: `email: EmailStr = Field(max_length=320)`

**Pros:** Consistent; rejects invalid emails at the schema layer before DB lookup; no extra dependency
**Cons:** None
**Effort:** 1 minute
**Risk:** None — valid email addresses still pass

## Recommended Action

Change `LoginRequest.email` from `str` to `EmailStr` in `api/schemas/auth.py:25`.

## Technical Details

**Affected files:**
- `api/schemas/auth.py:25`

## Acceptance Criteria

- [ ] `LoginRequest.email` uses `EmailStr`
- [ ] `POST /auth/login` with `"not-an-email"` returns 422
- [ ] Existing login tests still pass

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
