---
status: pending
priority: p3
issue_id: "045"
tags: [code-review, type-safety, auth]
dependencies: []
---

# Make `RefreshPayload` a Frozen Dataclass

## Problem Statement

`api/services/auth_service.py:21-24` defines `RefreshPayload` as a plain `@dataclass`. It is a pure value object extracted from a verified JWT — it should be immutable. Using `@dataclass(frozen=True)` makes the immutability intent explicit and prevents accidental mutation in a security-sensitive context.

## Findings

- `api/services/auth_service.py:20-23` — `@dataclass class RefreshPayload` with `sub: str` and `jti: str`
- No `frozen=True` — fields are mutable after construction
- `TokenPayload` (the access token analog in `api/schemas/auth.py`) is a Pydantic model which is immutable by default
- Confirmed by: kieran-python-reviewer (medium)

## Proposed Solutions

### Option 1: Add `frozen=True` to the dataclass decorator (Recommended)

Change `@dataclass` to `@dataclass(frozen=True)`.

**Effort:** 1 minute
**Risk:** None — no code modifies `RefreshPayload` fields after construction

## Technical Details

**Affected files:**
- `api/services/auth_service.py:20`

## Acceptance Criteria

- [ ] `@dataclass(frozen=True)` on `RefreshPayload`
- [ ] `make test` passes

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
