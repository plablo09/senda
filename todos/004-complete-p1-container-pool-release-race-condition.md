---
status: complete
priority: p1
issue_id: "004"
tags: [code-review, python, async, concurrency, correctness]
dependencies: []
---

# ContainerPool.release() modifies shared list without lock — data race

## Problem Statement

`ContainerPool.acquire()` correctly uses `async with self._lock` to protect `self._available`. But `release()` appends to the same list without acquiring the lock at all. Under concurrent WebSocket connections this is a data race: a container could be added back to `_available` while `acquire()` is reading or modifying the list, leading to a container being acquired twice simultaneously.

## Findings

```python
# api/services/execution_pool.py:57-64
async def acquire(self) -> str:
    for _ in range(60):
        async with self._lock:           # ← lock held here
            if self._available:
                return self._available.pop(0)

# api/services/execution_pool.py:66-68
def release(self, container_id: str):
    self._available.append(container_id)  # ← NO lock! data race
```

Python's GIL protects against CPython list corruption but does not protect against logical races in async code (where `acquire` can interleave with `release` between awaits).

## Proposed Solutions

### Option A: Acquire lock in release() (recommended)
```python
async def release(self, container_id: str) -> None:
    async with self._lock:
        self._available.append(container_id)
```

- **Pros:** Simple, consistent with acquire()
- **Cons:** release() must become async (callers use `await pool.release(...)`)
- **Effort:** Small
- **Risk:** Low

### Option B: Replace with asyncio.Queue
`asyncio.Queue` is inherently safe for concurrent async producers/consumers and eliminates the lock entirely. `acquire()` becomes `await queue.get()` and `release()` becomes `await queue.put(container_id)`.

- **Pros:** Removes lock + polling loop in one change; elegant
- **Cons:** More refactoring needed (queue initialized with pre-warmed containers)
- **Effort:** Medium
- **Risk:** Low

## Recommended Action

Option B if also fixing the busy-wait acquire() (see todo 007). Option A if fixing just this issue.

## Technical Details

- **Affected files:** `api/services/execution_pool.py:66-68`

## Acceptance Criteria

- [ ] Two concurrent WebSocket connections cannot acquire the same container
- [ ] release() acquires the lock (or uses Queue)
- [ ] Stress test: 10 concurrent connections with pool size 2 — all execute correctly without double-acquisition

## Work Log

- 2026-03-20: Identified by kieran-python-reviewer (P1-3)
