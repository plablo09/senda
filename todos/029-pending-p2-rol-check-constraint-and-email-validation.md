---
status: pending
priority: p2
issue_id: "029"
tags: [code-review, database, migration, validation]
dependencies: []
---

# Add DB CHECK Constraint on rol + Email Format Validation

## Problem Statement

Two related validation gaps:
1. `usuarios.rol` is `String(10)` with no database-level constraint — any string up to 10 characters is accepted, so scripts, LTI provisioning, or bugs can silently store invalid roles that cause authorization guards to behave unexpectedly.
2. `UsuarioCreate.email` validates length but not format — `"notanemail"` passes schema validation and reaches the database.

## Findings

- `api/models/usuario.py:19`: `rol: Mapped[str] = mapped_column(String(10), ...)` — no CHECK constraint
- `alembic/versions/0002_add_usuarios_and_refresh_sessions.py:29`: Column definition has no constraint
- `api/schemas/auth.py:11`: `email: str = Field(max_length=320)` — format not validated
- `api/dependencies/auth.py:33,41`: `user.rol != "teacher"` / `user.rol != "student"` — string comparison with no guarantee of valid values
- Invalid role (e.g. `"admin"`, `"teacher "` with trailing space) silently behaves as unprivileged account with no error at insert time

## Proposed Solutions

### Option 1: CheckConstraint + EmailStr (Recommended)

**Approach:**
- Add `sa.CheckConstraint("rol IN ('teacher', 'student')", name="ck_usuarios_rol")` to the migration (or amend 0002 since it's greenfield)
- Add `email: EmailStr` to `UsuarioCreate` (requires `pydantic[email]` which adds the `email-validator` dependency)

```python
# schemas/auth.py
from pydantic import EmailStr
class UsuarioCreate(BaseModel):
    email: EmailStr = Field(max_length=320)
    ...
```

```python
# migration (amend 0002 or add to 0003)
sa.CheckConstraint("rol IN ('teacher', 'student')", name="ck_usuarios_rol"),
```

**Pros:**
- DB invariant enforced regardless of how rows are created
- Email format validated at API boundary before hitting DB
- `pydantic[email]` is a standard addition

**Cons:**
- Small dependency addition for `EmailStr`

**Effort:** 1 hour

**Risk:** Low

## Recommended Action

Option 1. Group the `CheckConstraint` into migration 0003 alongside the session cleanup index (todo-024). Add `email-validator` to `api/pyproject.toml`.

## Technical Details

**Affected files:**
- `api/schemas/auth.py` — `email: EmailStr`
- `api/pyproject.toml` — add `pydantic[email]` or `email-validator>=2.0`
- New migration 0003 (or amend 0002) — add `CheckConstraint`
- `api/models/usuario.py` — optionally switch to `sqlalchemy.Enum("teacher", "student", name="rol_enum")`

## Acceptance Criteria

- [ ] `POST /auth/registro` with `email: "notanemail"` returns 422
- [ ] Direct DB insert of `rol='admin'` raises `IntegrityError`
- [ ] Migration includes `CHECK (rol IN ('teacher', 'student'))` constraint
- [ ] Tests cover email format validation rejection

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
