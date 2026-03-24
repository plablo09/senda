---
status: complete
priority: p1
issue_id: "024"
tags: [code-review, performance, database, auth]
dependencies: []
---

# Add Cleanup for Expired/Revoked Refresh Token Rows

## Problem Statement

Every login appends one row to `sesiones_refresh`. Logout marks `revoked_at` but leaves the row in place. Expired sessions are never deleted. The table and its B-tree index on `jti` grow without bound, degrading every `/auth/refresh` and `/auth/logout` query over time. At realistic platform scale (5k DAU, 1 year), the table reaches ~1.8M rows and index pages begin spilling to disk.

## Findings

- `api/services/auth_service.py:40–52`: `create_refresh_token` inserts a new row on every login; no cleanup counterpart
- `api/services/auth_service.py:65–70`: `revoke_refresh_token` sets `revoked_at` but does not delete the row
- `alembic/versions/0002_add_usuarios_and_refresh_sessions.py`: No `expires_at` index — cleanup queries would require a full table scan
- No Celery beat task, pg_cron query, or any other periodic job exists for session cleanup
- Performance reviewer projection: ~365k rows/year at 500 DAU; index spills to disk at ~1.8M rows on typical dev/small-prod RAM

## Proposed Solutions

### Option 1: Celery beat cleanup task (Recommended)

**Approach:** Add a periodic Celery beat task (e.g., every 6 hours) that deletes rows where `expires_at < NOW()` OR `revoked_at IS NOT NULL`. Add a migration that creates an index on `expires_at` to make the DELETE efficient.

```python
# api/tasks/cleanup.py
@celery_app.task
def cleanup_expired_sessions():
    with SyncSessionLocal() as db:
        db.execute(
            delete(SesionRefresh).where(
                (SesionRefresh.expires_at < datetime.now(UTC)) |
                (SesionRefresh.revoked_at.isnot(None))
            )
        )
        db.commit()
```

**Pros:**
- Uses existing Celery + Redis infrastructure
- No new dependencies
- Configurable interval

**Cons:**
- Requires sync session for Celery task (established pattern in codebase)

**Effort:** 2–3 hours (task + migration + beat config)

**Risk:** Low

---

### Option 2: pg_cron in PostgreSQL

**Approach:** Add a pg_cron job in a migration that runs a DELETE directly in PostgreSQL.

**Pros:**
- No application code needed
- Runs even if Celery is down

**Cons:**
- Requires pg_cron extension (not standard in all environments)
- Less visible in application code

**Effort:** 1 hour (if pg_cron available)

**Risk:** Medium (extension availability)

---

### Option 3: TTL-based delete on access (lazy cleanup)

**Approach:** In `revoke_refresh_token` and `create_refresh_token`, opportunistically delete old rows for the same `user_id` where `expires_at < NOW()`.

**Pros:**
- No background job needed

**Cons:**
- Cleanup only happens on auth activity; inactive users accumulate stale rows indefinitely
- Adds latency to auth hot paths

**Effort:** 1 hour

**Risk:** Low

## Recommended Action

Option 1 (Celery beat task) + a migration adding `ix_sesiones_refresh_expires_at`. The migration should be added as `0003` alongside the fix for todo-023.

## Technical Details

**Affected files:**
- New: `api/tasks/cleanup.py`
- New: `alembic/versions/0003_add_session_cleanup_index.py`
- `api/celery_app.py` — add beat schedule entry

**Database changes:**
- New index: `CREATE INDEX ix_sesiones_refresh_expires_at ON sesiones_refresh (expires_at);`

## Acceptance Criteria

- [ ] A periodic task runs that deletes rows where `expires_at < NOW()` or `revoked_at IS NOT NULL`
- [ ] A migration adds an index on `sesiones_refresh.expires_at`
- [ ] Task is registered in Celery beat schedule
- [ ] Unit test asserts expired rows are deleted, active rows are preserved

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)

**Actions:**
- Performance reviewer flagged as P1 with detailed scale projections
