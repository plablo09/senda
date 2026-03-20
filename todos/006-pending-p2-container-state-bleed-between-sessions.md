---
status: pending
priority: p2
issue_id: "006"
tags: [code-review, security, docker, isolation]
dependencies: [004]
---

# Container /tmp files persist between student sessions — cross-session data leakage

## Problem Statement

`ContainerPool.release()` returns a container to the pool without any cleanup. Files written to `/tmp` during student A's session persist and are readable by student B who acquires the same container. The `tmpfs` mount (`/tmp: size=100m`) is not wiped on release.

Scenario: Student A writes a CSV with sensitive analysis results to `/tmp/data.csv`. Container is released. Student B acquires it and runs `import os; os.listdir('/tmp')` — they see and can read the file.

## Findings

- `api/services/execution_pool.py:66-68` — `release()` returns container with no cleanup
- `api/services/execution_pool.py:51` — `tmpfs={"/tmp": "size=100m"}` — correct, but not wiped on release
- `docker-compose.yml` — exec services have no `read_only: true`

## Proposed Solutions

### Option A: Wipe /tmp and /workspace on release (recommended for Phase 1)
```python
async def release(self, container_id: str) -> None:
    container = await asyncio.to_thread(self._docker.containers.get, container_id)
    await asyncio.to_thread(
        container.exec_run,
        ["sh", "-c", "rm -rf /tmp/* /workspace/*"],
        user="root"
    )
    async with self._lock:
        self._available.append(container_id)
```

- **Pros:** Simple, effective, minimal overhead
- **Cons:** Requires root exec in container; adds ~100ms per release
- **Effort:** Small
- **Risk:** Low

### Option B: Restart container on release
`container.restart()` gives a fully clean filesystem state.

- **Pros:** Strongest isolation — process state, kernel state, everything reset
- **Cons:** Container restart takes 1-3s; pool effectively has no warm containers
- **Effort:** Small
- **Risk:** Medium (latency impact)

### Option C: Track "dirty" containers and destroy/replace
Mark containers as dirty after use. Replace them with fresh containers in a background task.

- **Pros:** Clean isolation + warm containers for next user
- **Cons:** Complex pool management; Phase 4 concern
- **Effort:** Large
- **Risk:** Medium

## Recommended Action

Option A for Phase 1-3. Option C for Phase 4.

## Technical Details

- **Affected files:** `api/services/execution_pool.py:66-68`

## Acceptance Criteria

- [ ] After session A writes to `/tmp/secret.txt`, session B on the same container cannot read it
- [ ] `/tmp` is empty at the start of every execution session
- [ ] Cleanup runs before container is returned to pool

## Work Log

- 2026-03-20: Identified by security-sentinel (P2-B), architecture-strategist (P2-B)
