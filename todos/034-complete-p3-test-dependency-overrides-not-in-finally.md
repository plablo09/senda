---
status: complete
priority: p3
issue_id: "034"
tags: [code-review, testing, quality]
dependencies: []
---

# Guard dependency_overrides.clear() in a pytest fixture

## Problem Statement

Every test in `test_auth_router.py` calls `_test_app.dependency_overrides.clear()` at the end of the test body. If any assertion before that line fails, the cleanup is skipped, leaving stale overrides for subsequent tests — causing false failures or false passes that are hard to diagnose.

## Findings

- `api/tests/unit/test_auth_router.py`: 9 tests each set `_test_app.dependency_overrides[get_db] = _get_db_override` and manually call `.clear()` at the end
- Python reviewer: P3-B
- If e.g. `test_login_success_sets_cookies` fails mid-test, the next test runs with the override from the previous test's `_get_db_override`

## Proposed Solutions

### Option 1: autouse fixture with yield

```python
import pytest

@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _test_app.dependency_overrides.clear()
```

Remove all manual `.clear()` calls from test bodies.

**Effort:** 15 minutes
**Risk:** Low

## Recommended Action

Option 1. Add the fixture at module level in `test_auth_router.py`.

## Technical Details

**Affected files:**
- `api/tests/unit/test_auth_router.py` — add autouse fixture, remove 9 manual `.clear()` calls

## Acceptance Criteria

- [ ] `_test_app.dependency_overrides` is always cleared after each test regardless of pass/fail
- [ ] No manual `.clear()` calls remain in test bodies
- [ ] All 19 tests continue passing

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
