---
status: complete
priority: p1
issue_id: "013"
tags: [code-review, alembic, migrations, python, quality]
dependencies: []
---

# Delete `create_tables()` dead code and stale lifespan model import

## Problem Statement

`create_tables()` still exists in `api/database.py` even though `main.py` no longer calls it. The function calls `Base.metadata.create_all`, which is the exact mechanism Alembic was introduced to replace. Any developer who rediscovers this function and calls it — in a test helper, a one-off script, or an accidental lifespan re-edit — will silently bypass Alembic and produce a schema that Alembic's version graph does not know about. A subsequent `alembic upgrade head` will then fail because the tables already exist.

The companion issue: `main.py` lifespan still imports `api.models.ejecucion_error` with a comment claiming it "registers EjecucionError with Base.metadata". This registration was needed when `create_all()` ran at startup. It is not needed now — the `ejecutar` router already imports `EjecucionError` transitively, and Alembic's `env.py` handles model registration for migrations. The comment actively misleads: it implies the API runtime still depends on `Base.metadata` registration.

## Findings

- `api/database.py:27-29` — `create_tables()` is an unreachable async function that calls `Base.metadata.create_all`. Not called from anywhere. Flagged by 4 independent review agents as a P1.
- `api/main.py:17` — `import api.models.ejecucion_error  # noqa: F401 — registers EjecucionError with Base.metadata` is a holdover from the `create_all` era. The model is already imported transitively by the `ejecutar` router. Comment is misleading about why the import is needed.

## Proposed Solutions

### Option A: Delete both (Recommended)
- Delete `create_tables()` entirely from `api/database.py`
- Remove the `# noqa` model import line from `api/main.py` lifespan
- Remove the `from api.database import create_tables` import that's no longer needed in `api/main.py` (note: it was moved to be a local import — check if it's now entirely absent)
- **Pros:** Clean, no ambiguity, matches the intent of the Alembic migration
- **Cons:** None — it's dead code with no callers

### Option B: Deprecate with raising body
- Replace the body with `raise RuntimeError("Use alembic upgrade head instead")`
- **Pros:** Louder failure if someone tries to call it
- **Cons:** Keeping dead code with a trap body is worse than deleting it

**Recommended:** Option A.

## Acceptance Criteria

- [ ] `create_tables()` does not exist in `api/database.py`
- [ ] `api/main.py` lifespan does not contain a `# noqa` model import for `ejecucion_error`
- [ ] All 59 existing unit tests pass
- [ ] `grep -rn "create_tables" api/` returns zero results

## Work Log

- 2026-03-22: Flagged as P1 by kieran-python-reviewer, architecture-strategist, data-migration-expert, performance-oracle in Phase 1 Alembic review
