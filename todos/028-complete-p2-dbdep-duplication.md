---
status: complete
priority: p2
issue_id: "028"
tags: [code-review, architecture]
dependencies: []
---

# Consolidate DbDep to a Single Definition

## Problem Statement

`DbDep = Annotated[AsyncSession, Depends(get_db)]` is defined independently in four files: `api/routers/auth.py`, `api/dependencies/auth.py`, `api/routers/documentos.py`, and `api/routers/datasets.py`. Any change to the DB dependency (e.g., adding tracing middleware, switching to a scoped session) must be applied to four separate locations.

## Findings

- `api/routers/auth.py:26`
- `api/dependencies/auth.py:13`
- `api/routers/documentos.py:18`
- `api/routers/datasets.py:18`
- All four definitions are byte-for-byte identical
- The canonical home is `api/database.py` (where `get_db` is already defined) or a new `api/dependencies/db.py`

## Proposed Solutions

### Option 1: Define DbDep in api/database.py (Recommended)

**Approach:** Add `DbDep = Annotated[AsyncSession, Depends(get_db)]` to `api/database.py` alongside `get_db`. All four files import it from there.

**Pros:**
- Co-located with `get_db` — one file owns the DB session infrastructure
- No new file needed

**Cons:**
- `database.py` gains a FastAPI import (`Depends`) — minor layering impurity

**Effort:** 30 minutes

**Risk:** Low

---

### Option 2: Define DbDep in api/dependencies/db.py

**Approach:** Create `api/dependencies/db.py` containing just `DbDep`.

**Pros:**
- Clean separation: database.py is pure SQLAlchemy; dependencies/ owns FastAPI-specific wrappers

**Cons:**
- New file for a one-liner

**Effort:** 30 minutes

**Risk:** Low

## Recommended Action

Option 1 (add to `api/database.py`) for simplicity. This is a pure cleanup — no behavior change.

## Technical Details

**Affected files:**
- `api/database.py` — add `DbDep`
- `api/routers/auth.py:26` — remove local definition, import from database
- `api/dependencies/auth.py:13` — remove local definition, import from database
- `api/routers/documentos.py:18` — remove local definition, import from database
- `api/routers/datasets.py:18` — remove local definition, import from database

## Acceptance Criteria

- [ ] `DbDep` defined in exactly one location
- [ ] All four files import from that location
- [ ] All tests pass

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
