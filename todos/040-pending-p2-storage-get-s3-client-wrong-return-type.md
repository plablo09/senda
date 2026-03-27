---
status: pending
priority: p2
issue_id: "040"
tags: [code-review, type-safety, storage]
dependencies: []
---

# Fix Invalid Return Type Annotation on `get_s3_client()`

## Problem Statement

`api/services/storage.py:16` has the annotation `-> boto3.client`. `boto3.client` is a factory function, not a type. This annotation was added on this branch (previously no return annotation). As written it is incorrect — `boto3.client(...)` returns a `botocore.client.BaseClient` subclass, not `boto3.client` itself. Any strict type checker (mypy, pyright) will flag this as a `TypeError` at check time.

## Findings

- `api/services/storage.py:16` — `def get_s3_client() -> boto3.client:` — `boto3.client` is a factory, not a type
- The actual return type is `botocore.client.BaseClient` (or `Any` if stubs are not installed)
- This annotation was introduced on this branch — it is worse than no annotation
- Confirmed by: kieran-python-reviewer (critical), code-simplicity-reviewer, security-sentinel, initial kieran-review

## Proposed Solutions

### Option 1: Use `Any` (Quick fix)

`def get_s3_client() -> Any:` — stops the type error, honest about the limitation.

**Pros:** One word change; removes the incorrect annotation
**Cons:** Loses type information
**Effort:** 1 minute
**Risk:** None

### Option 2: Remove the return annotation (Equivalent to Option 1)

Remove `-> boto3.client` entirely.

**Pros:** Same effect as Option 1
**Cons:** Less explicit
**Effort:** 1 minute
**Risk:** None

### Option 3: Install `boto3-stubs[s3]` and use the precise type

`from mypy_boto3_s3 import S3Client` and annotate `-> S3Client`.

**Pros:** Accurate type; enables autocomplete
**Cons:** Requires adding `boto3-stubs[s3]` to dev dependencies
**Effort:** 15 minutes
**Risk:** Low

## Recommended Action

Option 1 for now — change to `-> Any` or remove the annotation. Option 3 can be a follow-up when the team adds typing toolchain.

## Technical Details

**Affected files:**
- `api/services/storage.py:16`

## Acceptance Criteria

- [ ] `get_s3_client()` has no `-> boto3.client` annotation
- [ ] mypy/pyright does not raise a `TypeError` on the annotation
- [ ] Existing storage tests pass

## Work Log

### 2026-03-26 - Identified during ce-review

**By:** Claude Code (ce-review)
