---
status: pending
priority: p3
issue_id: "044"
tags: [code-review, performance, health]
dependencies: []
---

# Cache `_get_version()` Result in `health.py`

## Problem Statement

`api/routers/health.py:9-13` calls `importlib.metadata.version("senda-api")` on every `/health` request. This performs a filesystem read (locating the package's `METADATA` dist-info file) each time. The result never changes during the process lifetime. Health endpoints are typically probed every 10–30 seconds. This is a trivially fixable per-request I/O waste.

## Findings

- `api/routers/health.py:9-13` — `_get_version()` called unconditionally inside the route handler
- `importlib.metadata.version()` reads from the filesystem on each call
- Simple fix: compute once at module load time or use `@lru_cache(maxsize=None)`
- Confirmed by: performance-oracle (P3), kieran-python-reviewer (low), code-simplicity-reviewer

## Proposed Solutions

### Option 1: Module-level constant (Recommended)

```python
try:
    _VERSION = version("senda-api")
except PackageNotFoundError:
    _VERSION = "unknown"
```

Then `health_check` returns `_VERSION` directly. Eliminates the helper function entirely.

**Pros:** No per-request I/O; removes the single-use helper function
**Cons:** None
**Effort:** 5 minutes
**Risk:** None

### Option 2: `@lru_cache(maxsize=None)` on `_get_version`

**Pros:** Lazy — only reads on first call
**Cons:** Slightly more code than Option 1
**Effort:** 2 minutes
**Risk:** None

## Recommended Action

Option 1 — compute `_VERSION` at module load time and remove `_get_version()`.

## Technical Details

**Affected files:**
- `api/routers/health.py`

## Acceptance Criteria

- [ ] `importlib.metadata.version()` is not called inside a request handler
- [ ] `/health` still returns the correct version string
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
