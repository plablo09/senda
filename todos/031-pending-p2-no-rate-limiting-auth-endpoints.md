---
status: pending
priority: p2
issue_id: "031"
tags: [code-review, security, performance, auth]
dependencies: []
---

# Add Rate Limiting to Auth Endpoints

## Problem Statement

`/auth/login`, `/auth/registro`, `/auth/refresh`, and `/auth/logout` have zero rate limiting. Because bcrypt is deliberately slow (~100ms/call), an unthrottled attacker can drive sustained CPU load by flooding `/auth/login`. Redis is already in the stack, making per-IP limits straightforward to add with `slowapi`.

## Findings

- `api/routers/auth.py`: all four endpoints have no rate-limit decorator or middleware
- `api/main.py`: only `CORSMiddleware` is applied — no rate-limit middleware
- Redis is already available at `settings.redis_url`
- Performance reviewer: 8 concurrent `/auth/login` requests saturate the thread pool (4-core machine); 50 concurrent requests could starve legitimate requests
- Security reviewer: credential stuffing, account enumeration via `/registro` 409 responses, and DoS via bcrypt flood are all enabled without rate limiting

## Proposed Solutions

### Option 1: slowapi with Redis store (Recommended)

**Approach:** Add `slowapi` (`pip install slowapi`), configure a `Limiter` using the Redis URL from `settings`, and decorate auth endpoints.

```python
# api/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# api/routers/auth.py
@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...
```

Suggested limits:
- `/auth/login`: 10/minute per IP
- `/auth/registro`: 5/minute per IP
- `/auth/refresh`: 30/minute per IP (legitimate clients refresh frequently)
- `/auth/logout`: 20/minute per IP

**Pros:**
- Uses existing Redis infrastructure
- Survives process restarts (Redis-backed counters)
- Works well in Docker Compose stack

**Cons:**
- New dependency (`slowapi`)
- Rate limits need tuning based on class size

**Effort:** 2 hours

**Risk:** Low

---

### Option 2: Nginx rate limiting

**Approach:** Add `limit_req_zone` to nginx config for `/auth/` paths.

**Pros:**
- No application code change
- Nginx handles it before requests hit Python

**Cons:**
- Not yet configured in the project (`nginx/` exists but is for Phase 4)
- Doesn't help in dev (Docker Compose without nginx)

**Effort:** 1 hour (when nginx is set up)

**Risk:** Low

## Recommended Action

Option 1 for the application layer. Option 2 can be added on top in Phase 4 when nginx is configured.

## Technical Details

**Affected files:**
- `api/pyproject.toml` — add `slowapi>=0.1`
- `api/main.py` — initialize limiter, add exception handler
- `api/routers/auth.py` — decorate all four endpoints
- `api/tests/unit/test_auth_router.py` — mock/skip rate limiting in tests

## Acceptance Criteria

- [ ] `/auth/login` returns 429 after 10 requests per minute from same IP
- [ ] `/auth/registro` returns 429 after 5 requests per minute
- [ ] Rate limit counts are stored in Redis (survive process restart)
- [ ] Tests are not affected by rate limiting (dev/test env disables limiter or mocks Redis)

## Work Log

### 2026-03-23 - Identified in code review

**By:** Claude Code (ce-review)
