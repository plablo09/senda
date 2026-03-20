---
status: complete
priority: p1
issue_id: "002"
tags: [code-review, python, celery, docker, correctness]
dependencies: []
---

# cleanup_stale_containers kills ALL active containers every 5 minutes

## Problem Statement

`cleanup_stale_containers` compares `container.id[:12]` (12-char prefix) against the values stored in Redis by `execution_pool.execute()`, which stores the **full 64-char container ID**. This comparison will never match, so `container_id not in active_ids` is always `True`, and the task kills and removes **every execution container on every run** — including ones actively executing student code.

The beat schedule runs this every 5 minutes, meaning mid-execution sessions are terminated on a timer.

## Findings

- `api/tasks/render_task.py:70` — `container_id = container.id[:12]` (short form)
- `api/tasks/render_task.py:73` — `active_ids = {r.get(k).decode() ...}` (full form from Redis)
- `api/services/execution_pool.py:113` — `await self._redis.setex(f"session:{session_id}:container_id", 1800, container_id)` — stores full `container.id`
- The `container_id not in active_ids` check is always `True` → kills everything

## Proposed Solutions

### Option A: Remove cleanup_stale_containers entirely (recommended for Phase 1)
The pool's `finally` block in `execute()` already calls `pool.release(container_id)`. The Redis session TTL is 30 minutes. There is no actual leakage scenario in Phase 1 (pool size 2+2, always released). Remove the task, the beat schedule entry, and the Redis session writes — they serve no consumer.

- **Pros:** Eliminates the bug, removes ~25 lines of dead/broken code, no more periodic container killing
- **Cons:** No stale container cleanup if the API crashes mid-execution (containers would stay running until manually stopped)
- **Effort:** Small
- **Risk:** Low

### Option B: Fix the ID comparison
Change `container_id = container.id[:12]` to `container_id = container.id` so the comparison uses the full ID.

- **Pros:** Preserves intent of the cleanup task
- **Cons:** The task still has the `r.get(k)` double-call N+1 issue (Performance finding P2-C); need to fix that too
- **Effort:** Small
- **Risk:** Medium (cleanup logic is complex; re-test carefully)

## Recommended Action

Option A for Phase 1. Option B in Phase 3/4 when the pool scales and actual stale containers become a real operational concern.

## Technical Details

- **Affected files:** `api/tasks/render_task.py:59-79`, `api/celery_app.py:18-23`, `api/services/execution_pool.py:112-115,121`

## Acceptance Criteria

- [ ] Running the stack for 10+ minutes does not kill any exec containers
- [ ] If Option A: `cleanup_stale_containers` task removed from `render_task.py` and beat schedule removed from `celery_app.py`
- [ ] If Option A: Redis session writes (`setex` for container_id and language) removed from `execution_pool.py`
- [ ] If Option B: Integration test asserts that a container with an active Redis session survives a cleanup run

## Work Log

- 2026-03-20: Identified by code-simplicity-reviewer, performance-oracle, security-sentinel, architecture-strategist
