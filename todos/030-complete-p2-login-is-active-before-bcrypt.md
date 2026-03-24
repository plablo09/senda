---
status: complete
priority: p2
issue_id: "030"
tags: [code-review, security, performance, auth]
dependencies: []
---

# Move is_active Check Before verify_password in /auth/login

## Problem Statement

The `/auth/login` endpoint checks `is_active` AFTER running bcrypt verification. This wastes ~100ms on bcrypt for accounts that will be rejected anyway, and — more importantly — the distinct `"Cuenta inactiva"` error message confirms to an attacker that both the email is registered AND the correct password was supplied.

## Findings

- `api/routers/auth.py:72–83`: order is: SELECT user → check existence → bcrypt verify → check is_active
- An inactive user with a correct password: bcrypt runs (100ms), returns 401 `"Cuenta inactiva"` — reveals valid credentials
- An inactive user with wrong password: bcrypt runs (100ms), returns 401 `"Credenciales inválidas"`
- The timing is the same either way after bcrypt, but the different error message is a direct oracle
- A missing/LTI user (no hashed_password): bcrypt is skipped (~1ms), returns 401 — creates a timing difference
- Security reviewer: F-05 (medium) — `"Cuenta inactiva"` discloses both account existence and correct password

## Proposed Solutions

### Option 1: Reorder checks + normalize error message (Recommended)

**Approach:**
```python
user = result.scalar_one_or_none()
if not user or not user.hashed_password or not user.is_active:
    raise HTTPException(status_code=401, detail="Credenciales inválidas")
if not await verify_password(payload.password, user.hashed_password):
    raise HTTPException(status_code=401, detail="Credenciales inválidas")
```

**Pros:**
- No bcrypt wasted on inactive accounts
- Eliminates the timing oracle for the `is_active` case
- Uniform `"Credenciales inválidas"` message for all rejection paths

**Cons:**
- Users cannot distinguish "wrong password" from "account deactivated" — intentional from a security perspective, but may affect UX if teachers need to know why they can't log in

**Effort:** 10 minutes

**Risk:** Low

---

### Option 2: Reorder only (no message change)

**Approach:** Move `is_active` check before `verify_password` but keep `"Cuenta inactiva"` message.

**Pros:**
- Saves bcrypt computation
- Users see a helpful message

**Cons:**
- Still a partial timing oracle (inactive vs wrong password paths now same timing, but message still reveals valid credentials)

**Effort:** 5 minutes

**Risk:** Low

## Recommended Action

Option 1. The performance win is secondary to the security improvement. Users who need to know their account is inactive can be told out-of-band by an administrator.

## Technical Details

**Affected files:**
- `api/routers/auth.py:72–83` — reorder guards, merge into single check, normalize message
- `api/tests/unit/test_auth_router.py` — update `test_login_inactive_user_returns_401` to confirm no bcrypt call is made

## Acceptance Criteria

- [ ] `is_active=False` check happens before `verify_password` is called
- [ ] `verify_password` is never called for an inactive user
- [ ] Inactive user returns 401 with the same message as wrong-password
- [ ] Tests confirm behavior

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
