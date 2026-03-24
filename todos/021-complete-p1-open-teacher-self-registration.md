---
status: complete
priority: p1
issue_id: "021"
tags: [code-review, security, auth]
dependencies: []
---

# Prevent Open Self-Registration of Teacher Role

## Problem Statement

The `UsuarioCreate` schema accepts `rol: Literal["teacher", "student"]` and the `/auth/registro` endpoint is unauthenticated. Any anonymous user on the internet can self-register as a teacher and immediately obtain full teacher privileges (lesson creation, student analytics, document publishing). Role-based access control is entirely bypassed at the enrollment seam.

## Findings

- `api/schemas/auth.py:13`: `rol: Literal["teacher", "student"]` — both roles accepted from unauthenticated requests
- `api/routers/auth.py:53–65`: `/registro` is unauthenticated, no admin token or invitation required
- `api/dependencies/auth.py:32–37`: `require_teacher` will gate Phase 4 document creation and analytics — a self-registered teacher bypasses all of it
- Teacher accounts grant access to content creation, student data, and administrative UI flows planned for Phase 4

## Proposed Solutions

### Option 1: Force student role on self-registration (Recommended for now)

**Approach:** Remove `rol` from `UsuarioCreate`. The endpoint always creates `rol="student"`. Teacher accounts are provisioned separately (by an existing teacher via an admin endpoint, or set directly in DB for initial bootstrapping).

**Pros:**
- Zero new code — just remove one field from the schema and hardcode `rol="student"` in the endpoint
- Students can still self-register freely
- Unblocks merge immediately

**Cons:**
- No self-service path for teachers until a provisioning endpoint is built
- Requires manual DB insert or separate admin endpoint for first teacher account

**Effort:** 30 minutes

**Risk:** Low

---

### Option 2: Invitation token for teacher registration

**Approach:** Add an invitation mechanism: an existing teacher (or admin) generates a signed one-time token. The `/registro` endpoint accepts an optional `invitation_token` field; if present and valid, the `rol` is set to `"teacher"`.

**Pros:**
- Self-service for teachers via invite flow
- Works well for institution onboarding

**Cons:**
- Requires additional endpoint + token storage
- Adds scope to this PR

**Effort:** 4–6 hours

**Risk:** Medium

---

### Option 3: Role from LTI assertion only

**Approach:** Role is never set by the user — it comes exclusively from the LTI `roles` claim when the LTI flow is implemented. Self-registration always creates students.

**Pros:**
- Clean institutional model
- No invitation infrastructure needed

**Cons:**
- LTI not yet implemented; defers teacher provisioning entirely

**Effort:** 0 now, then LTI work later

**Risk:** Low

## Recommended Action

Option 1 immediately (hardcode `rol="student"` on self-registration). Build a `POST /auth/admin/usuarios` endpoint protected by `require_teacher` for teacher provisioning in Phase 4.

## Technical Details

**Affected files:**
- `api/schemas/auth.py` — remove `rol` from `UsuarioCreate` (or make it optional/ignored)
- `api/routers/auth.py:61` — replace `rol=payload.rol` with `rol="student"`
- `api/tests/unit/test_auth_router.py` — update `test_registro_success` assertion

## Acceptance Criteria

- [ ] `/auth/registro` cannot create a teacher account
- [ ] All self-registered users have `rol="student"`
- [ ] Teacher provisioning path is documented (even if it's a manual DB step for now)
- [ ] Test asserts `rol` is always `"student"` regardless of request body

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)

**Actions:**
- Security reviewer flagged as P2 High; classified P1 here given it trivially defeats the access control model

---

## Notes

- First teacher account can be created directly in DB during initial setup: `INSERT INTO usuarios (id, email, hashed_password, rol) VALUES (gen_random_uuid(), 'admin@school.edu', crypt('...', gen_salt('bf')), 'teacher');`
