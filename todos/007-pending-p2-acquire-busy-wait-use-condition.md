---
status: pending
priority: p2
issue_id: "007"
tags: [code-review, python, async, performance]
dependencies: [004]
---

# ContainerPool.acquire() busy-polls every 1s — use asyncio.Condition

## Problem Statement

The acquire loop polls `self._available` every second for up to 60 iterations. There is no notification mechanism when `release()` makes a container available — waiters always sleep the full 1-second interval. Under the default pool size of 2, any 3rd concurrent student request experiences at least 1 second of artificial latency even if a container frees up 1 millisecond into the wait.

## Findings

```python
# api/services/execution_pool.py:59-64
for _ in range(60):
    async with self._lock:
        if self._available:
            return self._available.pop(0)
    await asyncio.sleep(1)  # always waits 1s regardless of when container is freed
raise TimeoutError("No hay contenedores de ejecución disponibles. Intenta de nuevo.")
```

## Proposed Solutions

### Option A: asyncio.Condition (recommended)
```python
# Replace _lock: asyncio.Lock with _condition: asyncio.Condition

async def acquire(self) -> str:
    async with self._condition:
        if not await asyncio.wait_for(
            self._condition.wait_for(lambda: bool(self._available)),
            timeout=60.0
        ):
            raise TimeoutError("No hay contenedores de ejecución disponibles. Intenta de nuevo.")
        return self._available.pop(0)

async def release(self, container_id: str) -> None:
    async with self._condition:
        self._available.append(container_id)
        self._condition.notify()
```

- **Pros:** Wakes immediately on release; no polling overhead; fixes race condition (todo 004) at the same time
- **Cons:** Minor refactor
- **Effort:** Small
- **Risk:** Low

### Option B: asyncio.Queue (cleanest)
Use a `asyncio.Queue` initialized with pre-warmed container IDs. `acquire()` = `await queue.get()`, `release()` = `await queue.put()`.

- **Pros:** Queue is the natural abstraction; no lock needed
- **Cons:** Harder to introspect pool size; queue.qsize() is not reliable
- **Effort:** Small-Medium
- **Risk:** Low

## Recommended Action

Option B if refactoring the whole pool. Option A as a targeted fix.

## Technical Details

- **Affected files:** `api/services/execution_pool.py:57-68`

## Acceptance Criteria

- [ ] When a container is released, the next waiter is notified within <10ms (not up to 1s)
- [ ] `TimeoutError` still raised after 60s if no container becomes available
- [ ] No busy-wait loop in acquire()

## Work Log

- 2026-03-20: Identified by performance-oracle (P1-B), architecture-strategist (P3-E), code-simplicity-reviewer (P2)
