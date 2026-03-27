---
status: pending
priority: p2
issue_id: "041"
tags: [code-review, security, execution-pool, config]
dependencies: []
---

# Wire `exec_timeout_seconds` into Container Execution

## Problem Statement

`api/config.py:38` defines `exec_timeout_seconds: int = 30` but this value is never read in `api/services/execution_pool.py`. The `container.exec_run()` call has no `timeout` parameter. This means an infinite loop (`while True: pass`) or a hanging computation will hold a Docker container for an unlimited duration, starvitng the pool. With only 4 total containers, a single bad code submission can block all legitimate users indefinitely.

## Findings

- `api/config.py:38` — `exec_timeout_seconds: int = 30` — declared but unused
- `api/services/execution_pool.py:130-136` — `container.exec_run(exec_cmd, stream=True, demux=True, ...)` — no `timeout` parameter
- `api/services/execution_pool.py:58-63` — acquire waits up to 60 seconds; container holds block this indefinitely if execution doesn't terminate
- The docker SDK `exec_run` does not have a native `timeout` parameter — the timeout must be enforced at the asyncio level with `asyncio.wait_for`
- Confirmed by: security-sentinel (M-1, L-3), performance-oracle, architecture-strategist (Issue A), learnings-researcher

## Proposed Solutions

### Option 1: Wrap `_run_in_container` with `asyncio.wait_for` (Recommended)

In `ExecutionPool.execute()`, wrap the `async for chunk in self._run_in_container(...)` with `asyncio.wait_for(..., timeout=settings.exec_timeout_seconds)`. Yield a `OutputChunk(tipo="error", contenido="Tiempo de ejecución excedido")` on timeout.

**Pros:** Uses the existing config key; applies to all languages uniformly; releases the container back to the pool on timeout
**Cons:** `asyncio.wait_for` on an async generator requires the generator to be wrapped in a task
**Effort:** 1 hour
**Risk:** Medium — test coverage needed for the timeout path

### Option 2: Pass timeout to `exec_run` directly

The Docker SDK's `exec_run` does not support `timeout` natively but the underlying API does via `timeout` on the HTTP request. This requires lower-level SDK access.

**Pros:** Terminates the container-side process, not just the client side
**Cons:** More complex; container process may still be running after client timeout
**Effort:** 2-3 hours
**Risk:** Medium

## Recommended Action

Option 1 — `asyncio.wait_for` wrapper in `execute()`. On `asyncio.TimeoutError`, yield an error chunk and release the container. Note: the container's running process will still need to be killed; consider `container.exec_run(["kill", "-9", "<pid>"])` or relying on the `/tmp` cleanup at release time.

## Technical Details

**Affected files:**
- `api/services/execution_pool.py:96-113` — wrap execution with timeout
- `api/services/execution_pool.py` — read `settings.exec_timeout_seconds`

## Acceptance Criteria

- [ ] `exec_timeout_seconds` from config is used in `execution_pool.py`
- [ ] Infinite loop code submitted to `/ejecutar` terminates within `exec_timeout_seconds + epsilon` seconds
- [ ] Container is returned to pool after timeout (not leaked)
- [ ] Error chunk with `tipo: "error"` is yielded on timeout
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
