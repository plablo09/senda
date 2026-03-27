---
status: pending
priority: p1
issue_id: "036"
tags: [code-review, quality, render-task]
dependencies: []
---

# Remove Duplicate Dead Imports Inside `render_documento` Task Body

## Problem Statement

The `api/tasks/render_task.py` branch refactor moved imports to module level (lines 9–15) but left the old deferred import block inside the `render_documento` function body (lines 37–42). These inner imports shadow the module-level ones. The module-level imports are now dead code — the function-level imports win due to Python scoping. This creates confusion about which import path is active and is a correctness hazard if the two ever diverge.

## Findings

- `api/tasks/render_task.py:9-15` — top-level imports added by this branch: `AsyncSessionLocal`, `Documento`, `serialize_document`, `render_qmd`, `RenderError`, `upload_html`, `ensure_bucket_exists`, `select`
- `api/tasks/render_task.py:37-42` — identical deferred imports still inside `render_documento` body, never removed
- `select` from `sqlalchemy` is imported at both line 7 (top-level) and line 42 (inside function)
- The `reset_stale_procesando` function correctly uses top-level imports without any inner imports — the pattern was partially applied
- Confirmed by: kieran-python-reviewer, code-simplicity-reviewer, architecture-strategist, schema-drift-detector

## Proposed Solutions

### Option 1: Delete the inner import block (Recommended)

Remove lines 37–42 from `render_documento`. The top-level imports already cover everything needed.

**Pros:** Fixes the dead code immediately, consistent with `reset_stale_procesando` pattern
**Cons:** None
**Effort:** < 5 minutes
**Risk:** None — the inner imports and top-level imports are identical

## Recommended Action

Delete `api/tasks/render_task.py:37-42` — the six deferred import lines inside `render_documento`. Verify with `make test` after removal.

## Technical Details

**Affected files:**
- `api/tasks/render_task.py:37-42` — delete these lines

## Acceptance Criteria

- [ ] Lines 37–42 removed from `render_documento`
- [ ] `api/tasks/render_task.py` has no duplicate imports (check with `grep -n "from api" api/tasks/render_task.py`)
- [ ] `make test` passes (94 tests)

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)

**Actions:**
- Confirmed by reading `render_task.py` — top-level imports at 9-15 exactly match inner imports at 37-42
- Flagged by 4 independent review agents
