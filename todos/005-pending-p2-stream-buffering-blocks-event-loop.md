---
status: pending
priority: p2
issue_id: "005"
tags: [code-review, python, async, performance, websocket]
dependencies: [004]
---

# list(stream) buffers all docker exec output — defeats streaming, risks OOM

## Problem Statement

`_run_in_container` calls `await asyncio.to_thread(list, stream)` which eagerly collects the **entire output** of a running container process before yielding a single chunk to the WebSocket client. This defeats the purpose of streaming entirely — students see nothing until the program completes. For long-running computations, this also buffers unbounded output in memory.

Additionally, `exec_timeout_seconds` is configured (default 30s) but is never applied to this call — a student can submit an infinite loop and hold a container indefinitely.

## Findings

```python
# api/services/execution_pool.py:148-156
async def read_stream():
    for stdout_chunk, stderr_chunk in await asyncio.to_thread(list, stream):
        # list(stream) blocks until process exits — no incremental streaming
```

- `api/config.py:20` — `exec_timeout_seconds: int = 30` declared but never used

## Proposed Solutions

### Option A: asyncio.Queue-based chunk forwarding (recommended)
Run the blocking generator in a thread that pushes chunks to a queue; the async side reads from the queue incrementally.

```python
async def _run_in_container(self, container_id, language, code):
    container = await asyncio.to_thread(self._docker.containers.get, container_id)
    exec_cmd = ["python3", "-c", code] if language == "python" else ["Rscript", "-e", code]

    _, stream = await asyncio.to_thread(
        container.exec_run, exec_cmd, stream=True, demux=True,
        environment={"MPLBACKEND": "Agg"}
    )

    queue: asyncio.Queue = asyncio.Queue()

    def _read():
        for stdout, stderr in stream:
            if stdout:
                queue.put_nowait(OutputChunk(tipo="stdout", contenido=stdout.decode("utf-8", errors="replace")))
            if stderr:
                queue.put_nowait(OutputChunk(tipo="stderr", contenido=stderr.decode("utf-8", errors="replace")))
        queue.put_nowait(None)  # sentinel

    await asyncio.to_thread(_read)  # or run in executor with timeout

    while True:
        chunk = await asyncio.wait_for(queue.get(), timeout=settings.exec_timeout_seconds)
        if chunk is None:
            break
        yield chunk
    yield OutputChunk(tipo="fin", contenido="")
```

- **Pros:** True incremental streaming; applies timeout; doesn't buffer all output
- **Cons:** More complex; thread/queue coordination
- **Effort:** Medium
- **Risk:** Low

### Option B: asyncio.wait_for around the existing list() call
At minimum, wrap the existing call to enforce the timeout:

```python
chunks = await asyncio.wait_for(
    asyncio.to_thread(list, stream),
    timeout=settings.exec_timeout_seconds
)
```

- **Pros:** Simple, applies timeout
- **Cons:** Still buffers all output; still not true streaming
- **Effort:** Tiny
- **Risk:** Low

## Recommended Action

Option A for Phase 2 (when interactive use matters). Option B now as a safety floor.

## Technical Details

- **Affected files:** `api/services/execution_pool.py:148-156`, `api/config.py:20`
- On timeout: send `{"tipo": "error", "contenido": "Tiempo de ejecución excedido."}` and kill the exec

## Acceptance Criteria

- [ ] `exec_timeout_seconds` is enforced — an infinite loop is terminated within 30s
- [ ] Client receives first output chunk before program completes (Option A only)
- [ ] Timeout sends a Spanish error chunk: `"Tiempo de ejecución excedido."`

## Work Log

- 2026-03-20: Identified by performance-oracle (P1-A), security-sentinel (P2-A)
