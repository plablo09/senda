---
title: Integration suite P1 fixes — Alembic IF EXISTS gap, async fixture coroutine injection, silent poll timeout
category: test-failures
date: 2026-03-28
tags: pytest-asyncio, alembic, migration, integration-tests, code-review, async-fixtures, coroutine-injection, timeout-handling
symptoms: Fresh-DB downgrade crash on documentos table drop; auth_headers fixture receiving coroutine object instead of token string; _wait_for_render silently returning pendiente-state document causing misleading KeyError downstream
components: alembic/versions/0001_initial_schema.py, api/tests/integration/conftest.py
---

# Integration suite P1 fixes — Alembic IF EXISTS gap, async fixture coroutine injection, silent poll timeout

Three P1 bugs discovered during multi-agent code review of PR #8 (`test/integration-suite`). None caused CI to fail at the time because the affected code paths were not yet exercised. Left unaddressed, all three would surface as confusing, hard-to-diagnose failures in future test runs.

## Problem Description

The PR added a pytest+httpx integration test suite for auth (Zone 1) and document lifecycle (Zone 2). Code review by 8 parallel agents found three bugs in the test suite's own code:

1. **Incomplete `IF EXISTS` guard** — the migration `downgrade()` was partially fixed: `datasets` and `ejecucion_errores` got `IF EXISTS` guards, but `documentos` still used bare `op.drop_table()`. Running `alembic downgrade base` on a fresh (stamped-but-not-migrated) database would crash on the `documentos` drop — the exact failure mode the PR was fixing.

2. **Sync fixture depending on async fixture** — `auth_headers` was a `def` (sync) fixture that consumed `auth_token`, an `async def` fixture. Under `asyncio_mode = "auto"`, pytest-asyncio does not auto-await coroutines injected into sync fixtures. The fixture would produce `Authorization: Bearer <coroutine object at 0x...>` silently.

3. **Silent timeout return in polling helper** — `_wait_for_render` returned `resp.json()` on timeout with no status check and no exception, causing the caller to receive a document in `pendiente` state. Downstream assertions would fail with `KeyError: 'estado_render'` or a misleading state mismatch rather than "render timed out after 90s".

## Root Cause Analysis

### Bug 1: Partial fix on IF EXISTS guards

When applying a defensive guard to a pattern that appears multiple times, it is natural to stop once the originally observed failure mode is resolved. The `documentos` table is the last dropped in `downgrade()`. If the failure was first reproduced on `datasets` or `ejecucion_errores`, fixing those two made the observable failure go away — leaving `documentos` broken and unnoticed.

`op.drop_table()` has no `if_exists` parameter in Alembic's standard API. The correct approach for idempotent drops in PostgreSQL is `op.execute("DROP TABLE IF EXISTS ...")`.

### Bug 2: pytest-asyncio sync/async fixture boundary

With `asyncio_mode = "auto"`, async fixtures are automatically awaited when injected into other **async** fixtures or test functions. However, when a **sync** (`def`) fixture requests an `async def` fixture as a parameter, pytest-asyncio does **not** automatically await the coroutine — the sync fixture receives the raw coroutine object.

This is the most dangerous of the three bugs because:
- It does not raise at definition time or fixture setup time.
- The coroutine object is truthy and can be embedded in strings without error.
- The bug is only observable when a test actually exercises the broken fixture's output (e.g., receiving a 401 because the bearer token is `<coroutine object ...>`).
- The fixture was latent — no test in the PR called `auth_headers` yet.

### Bug 3: Silent exit paths in test helpers

A polling helper that times out silently does not fail the test — it contaminates it. The original `_wait_for_render` fell through to a bare `return resp.json()` with no status check, making timeout indistinguishable from a slow-but-successful render from the caller's perspective.

## Solution

### Fix 1: Apply IF EXISTS to all three table drops

```python
# alembic/versions/0001_initial_schema.py

# Before:
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS datasets")
    op.execute("DROP TABLE IF EXISTS ejecucion_errores")
    op.drop_table("documentos")  # raises ProgrammingError on fresh DB

# After:
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS datasets")
    op.execute("DROP TABLE IF EXISTS ejecucion_errores")
    op.execute("DROP TABLE IF EXISTS documentos")  # consistent + idempotent
```

**Rule**: after writing any `downgrade()`, count drop operations and verify an equal number of `IF EXISTS` guards. One missing guard can fail a production rollback.

### Fix 2: Make auth_headers an async fixture

```python
# api/tests/integration/conftest.py

# Before:
@pytest.fixture
def auth_headers(auth_token: str) -> dict:  # sync — receives coroutine, not str
    return {"Authorization": f"Bearer {auth_token}"}

# After:
@pytest.fixture
async def auth_headers(auth_token: str) -> dict[str, str]:  # async — receives resolved str
    return {"Authorization": f"Bearer {auth_token}"}
```

**Rule**: if a fixture is in a chain that includes any `async def` fixture, it must itself be `async def`. Async fixtures propagate upward — no exceptions.

### Fix 3: Raise on timeout instead of silently returning

```python
# api/tests/integration/conftest.py

# Before:
    for _ in range(timeout):
        resp = await client.get(f"/documentos/{doc_id}")
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        if doc["estado_render"] in ("listo", "fallido"):
            return doc
        await asyncio.sleep(1.0)
    # Return whatever state we have on timeout
    resp = await client.get(f"/documentos/{doc_id}")
    return resp.json()  # no status check, no error on timeout

# After:
    for _ in range(timeout):
        resp = await client.get(f"/documentos/{doc_id}")
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        if doc["estado_render"] in ("listo", "fallido"):
            return doc
        await asyncio.sleep(1.0)
    # Timeout — fail loudly with diagnostic context
    resp = await client.get(f"/documentos/{doc_id}")
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    raise AssertionError(
        f"Render did not reach terminal state within {timeout}s. "
        f"Last estado_render={doc.get('estado_render')!r}, "
        f"error_render={doc.get('error_render')!r}"
    )
```

**Rule**: every exit path of a test helper must be explicit and loud. A timeout branch ends with `raise`, and the message must name what was being waited for and for how long.

## Prevention Strategies

### Alembic downgrade idempotency
- After writing any `downgrade()`, grep the function body for bare `drop_table` / `drop_index` / `drop_constraint` calls and verify each has the `IF EXISTS` guard.
- The checklist item: "count drop operations in `upgrade()`, verify a corresponding `IF EXISTS` guard exists for each in `downgrade()`."
- CI verification: `alembic upgrade head && alembic downgrade base && alembic upgrade head` — all three commands must exit 0.

### pytest-asyncio fixture scope
- All fixtures in `conftest.py` that touch async code (DB sessions, HTTP clients, token generation) must be `async def`.
- Any fixture added downstream of an `async def` fixture must also be `async def` — trace the dependency chain at definition time.
- Add `filterwarnings = ["error::RuntimeWarning"]` to `pyproject.toml` to surface unawaited coroutines as hard failures (already done in this project).

### Test helper contracts
- Require all polling helpers to document what exceptions they raise and under what conditions.
- Every timeout branch ends with `raise` — a silent `return` from a timeout is a contract violation.
- Write a test for the test helper: assert that it raises (not returns) when the condition is never met.

## Detection Rules (Review Checklist)

- [ ] Every `drop_*` call in a `downgrade()` function uses `IF EXISTS` or a safe wrapper
- [ ] No sync (`def`) fixture takes an `async def` fixture as a parameter
- [ ] Every polling/retry helper has a documented timeout path that raises a named exception
- [ ] Any new fixture added to `conftest.py` — check whether it is in a chain that includes any `async def` fixture; if so, it must be `async def`
- [ ] Partial fixes: when applying a guard to one instance of a pattern, search for all sibling instances in the same function/file before marking complete

## Key Rules

1. **Every drop in downgrade gets IF EXISTS — count them.** One missing guard can fail a production rollback on a stamped-but-not-migrated database.

2. **Async fixtures propagate upward.** If fixture B is `async def`, fixture A that consumes it must also be `async def`. pytest-asyncio silently injects the coroutine object into sync fixtures — no warning, no error at definition time.

3. **Every exit path of a test helper must be explicit and loud.** Timeout → raise, not return. The exception message must say what was being waited for and for how long.

4. **Partial fixes are the second bug.** When applying a defensive guard, apply it to the entire call site category. Search for all sibling call sites before marking the fix complete.

5. **Test helper contracts are first-class.** Write a test for your test helper. If `_wait_for_render` had a test asserting it raises on timeout, Bug 3 would have been caught at definition time.

## Related Documentation

- [`docs/solutions/test-failures/docker-pytest-async-mock-pitfalls.md`](docker-pytest-async-mock-pitfalls.md) — silent async/sync mismatches in pytest, `filterwarnings` guard, mock patch completeness; Pitfall 2 there (sync test calling async function) is the same family as Bug 2 here
- [`docs/solutions/database-issues/alembic-asyncpg-fastapi-migration-foundation.md`](../database-issues/alembic-asyncpg-fastapi-migration-foundation.md) — Alembic setup, `NullPool` for migrations, `downgrade()` completeness checklist (does not yet mention `IF EXISTS` — cross-reference this doc when that checklist is updated)
- [`docs/solutions/security-issues/unauthenticated-execution-endpoints-p1-fixes.md`](../security-issues/unauthenticated-execution-endpoints-p1-fixes.md) — Fix 3 there documents the `CREATE OR REPLACE TRIGGER` / `DROP TRIGGER IF EXISTS` pattern for shared function DDL; same idempotency category as Bug 1
- [`docs/solutions/integration-issues/live-test-session-six-bugs-celery-quarto-minio-editor.md`](../integration-issues/live-test-session-six-bugs-celery-quarto-minio-editor.md) — the live-test session that motivated the integration suite PR #8
- [`docs/plans/2026-03-28-001-test-live-test-strategy-plan.md`](../../plans/2026-03-28-001-test-live-test-strategy-plan.md) — full integration test strategy, Zone 5 migration idempotency playbook

## Context

Found during multi-agent code review (8 parallel agents) of PR #8 (`test/integration-suite`) on 2026-03-28. The PR was adding a pytest+httpx integration test suite for auth (Zone 1) and document lifecycle (Zone 2) against the live Docker Compose stack. All three bugs were latent — none caused CI failures at review time. Fixed in commit `7480ac7`.

Pre-existing production P1 gaps discovered in the same review (not fixed in this PR, tracked separately): unauthenticated write access to `/documentos`/`/datasets`/`/retroalimentacion`; default JWT `secret_key` in `api/config.py`; `cookie_secure=False` default.
