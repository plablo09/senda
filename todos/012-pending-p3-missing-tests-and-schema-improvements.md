---
status: pending
priority: p3
issue_id: "012"
tags: [code-review, testing, schema, architecture]
dependencies: [001, 009]
---

# Missing tests, no AST schema version, asyncpg pool not configured

## Problem Statement

Three independent P3 issues best addressed before Phase 2 begins.

## Findings

### 1. No tests for documentos router or WebSocket ejecutar
- `api/tests/` — only `test_qmd_serializer.py` and `test_health.py`
- The render pipeline dispatch, CRUD state transitions, and WebSocket execution have zero test coverage
- The `try/except ImportError` guard in `documentos.py` signals testability was planned — follow through

### 2. AST has no schema version field
- `api/schemas/documento.py:11`, `api/models/documento.py:20` — `ast: dict | None`
- Phase 2 (BlockNote editor) will introduce new block types; without a version field, old documents can't be distinguished from new ones
- Fix: require `"schemaVersion": 1` at the top level of every AST; the serializer can default old documents to version 0

### 3. asyncpg connection pool not configured
- `api/database.py:10` — `create_async_engine(settings.database_url, echo=False)` uses all defaults
- No `pool_size`, `pool_timeout`, `pool_pre_ping`, `pool_recycle`
- Under moderate load, default 30s `pool_timeout` causes silent 30s stalls; stale connections after DB restart raise errors on first use

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_timeout=5,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=False,
)
```

### 4. exec-python and exec-r containers in docker-compose have no resource limits
- `docker-compose.yml:81-101` — no `mem_limit`, `cpus`, or `pids_limit`
- Pool-spawned containers get `mem_limit="512m"` and `cpu_quota=50000` but reused docker-compose containers get none
- Fix: add matching `deploy.resources.limits` to compose services

### 5. listar_documentos loads all columns with no pagination
- `api/routers/documentos.py:38-40` — loads `ast` (JSONB) and `qmd_source` (TEXT) for every document
- Fix: project only needed columns for list view; add `limit`/`offset` query params

## Acceptance Criteria

- [ ] Integration test for `POST /documentos` → `GET /documentos/{id}` verifying `estado_render` transitions
- [ ] Test for WebSocket `/ws/ejecutar` with mock execution_pool
- [ ] `ast` field validated to contain `schemaVersion` key
- [ ] `create_async_engine` configured with explicit pool params
- [ ] docker-compose exec services have resource limits matching ContainerPool.initialize()
- [ ] `GET /documentos` accepts `limit` and `offset` query parameters

## Work Log

- 2026-03-20: Identified by kieran-python-reviewer (P3-6), architecture-strategist (P3-C, P3-F), performance-oracle (P2-A, P3-B)
