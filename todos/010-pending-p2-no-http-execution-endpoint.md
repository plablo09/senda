---
status: pending
priority: p2
issue_id: "010"
tags: [code-review, api, agent-native, websocket]
dependencies: []
---

# Code execution is WebSocket-only — add HTTP POST /ejecutar for agents and CI

## Problem Statement

The only way to execute code is via `WS /ws/ejecutar`. Standard HTTP clients (LLM tool-calling, MCP tools, CI pipelines, curl) cannot use WebSockets. The underlying `execution_pool.execute()` is already a well-designed async generator — adding an HTTP wrapper is a thin addition.

## Findings

- `api/routers/ejecutar.py` — only WebSocket endpoint, no HTTP equivalent
- `api/services/execution_pool.py:99-121` — `execute()` is a reusable async generator

## Proposed Solutions

### Option A: Add POST /ejecutar that collects all chunks (recommended for Phase 1)
```python
@router.post("/ejecutar", response_model=EjecucionResponse)
async def ejecutar_http(payload: EjecucionRequest):
    chunks = []
    async for chunk in execution_pool.execute(
        payload.session_id, payload.language, payload.code
    ):
        chunks.append(chunk)
    return {"session_id": payload.session_id, "chunks": chunks}
```

With a Pydantic response model that exposes `OutputChunk` as a typed schema.

- **Pros:** Simple; reuses existing pool; WebSocket stays for interactive browser use
- **Effort:** Small
- **Risk:** Low

### Option B: Add SSE (Server-Sent Events) endpoint
`GET /ejecutar/stream` with `text/event-stream` for streaming without WebSocket.

- **Pros:** Progressive streaming over plain HTTP
- **Cons:** SSE is GET-based; code goes in query string or requires POST+polling pattern
- **Effort:** Medium
- **Risk:** Low

## Recommended Action

Option A for Phase 2. The WebSocket endpoint is fine for Phase 1 browser use; the HTTP endpoint unlocks agent/CI access.

## Technical Details

- **Affected files:** `api/routers/ejecutar.py`, `api/schemas/` (new `EjecucionRequest`, `EjecucionResponse`)
- `OutputChunk.tipo` should be a `Literal` type (see P3 todos) so it appears in OpenAPI

## Acceptance Criteria

- [ ] `curl -X POST /ejecutar -d '{"language":"python","code":"print(1)"}' ` returns JSON with chunks
- [ ] Response schema documented in OpenAPI
- [ ] WebSocket endpoint still works for browser interactive use

## Work Log

- 2026-03-20: Identified by agent-native-reviewer (P1)
