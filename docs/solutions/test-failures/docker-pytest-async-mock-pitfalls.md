---
title: "Docker stale image, wrong working directory, sync/async test mismatch, and missing mock patches"
category: test-failures
date: 2026-03-23
tags:
  - docker
  - pytest
  - pytest-asyncio
  - async
  - jwt
  - fastapi
  - mocking
  - refresh-token
  - working-directory
  - module-not-found
components:
  - docker-compose
  - api/tests/unit/test_auth_service.py
  - api/tests/unit/test_auth_router.py
  - api/routers/auth.py
  - api/services/auth_service.py
symptoms:
  - "ModuleNotFoundError: No module named 'api' when running pytest inside container"
  - "Coroutine-was-never-awaited RuntimeWarning for verify_access_token calls in sync test functions"
  - "test_refresh_valid_token_returns_new_access_token hits un-mocked DB interactions after refresh rotation added"
  - "Silent test failures due to missing await on async verify_access_token"
  - "pytest invoked from /app/api loses api package from sys.path"
problem_type: compound
related:
  - docs/solutions/runtime-errors/docker-compose-stack-startup-failures.md
  - docs/solutions/runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md
  - docs/solutions/security-issues/fastapi-jwt-cookie-auth-review-cluster.md
  - docs/solutions/security-issues/phase-3-llm-guidance-pre-merge-review-fixes.md
---

# Docker + pytest + async/mock test pitfalls

Four related failures surfaced while resolving Phase 2 P1 auth issues on `feat/phase-2-authentication`. All 87 tests pass after the fixes below.

---

## Problem 1: `ModuleNotFoundError: No module named 'api'` — stale Docker image

### Root cause

New source files added after the last `docker compose build` do not exist inside the running container. The container executes the old image layer, so any new modules are simply absent.

### Fix

Always rebuild the API image after adding, removing, or changing source files:

```bash
docker compose build api
```

This must be done every time a new file is added or an existing source file is modified. Forgetting this step is the most common silent footgun.

**Diagnosis hint:** If `ModuleNotFoundError` appears for a package you know exists locally, rebuild before investigating further.

---

## Problem 2: `ModuleNotFoundError: No module named 'api'` — wrong pytest working directory

### Root cause

The `Dockerfile` sets `WORKDIR /app` and copies source with `COPY api/ api/`, placing the `api` package at `/app/api/`. Python only finds `api` as a top-level package when `/app` is on `sys.path`. Running pytest from `/app/api` removes `api` from the importable namespace.

### Fix

Always run pytest from `/app` (the WORKDIR), never from `/app/api`:

```bash
# Correct — Docker entrypoint is already /app:
docker compose run --rm api pytest api/tests/unit/test_auth_service.py -v

# Also correct — explicit cd:
docker compose run --rm api bash -c "cd /app && python -m pytest api/tests/unit/test_auth_service.py -v"

# Wrong — breaks import resolution:
docker compose run --rm api bash -c "cd /app/api && python -m pytest tests/unit/test_auth_service.py -v"
```

### Key mental model

`WORKDIR` in the Dockerfile is the Python import root, not just a convenience path. `COPY api/ api/` means the package is at `<WORKDIR>/api`, so `<WORKDIR>` must always be on `sys.path`. Keeping the pytest invocation relative to `WORKDIR` maintains this invariant.

**Note:** This produces the same `ModuleNotFoundError: No module named 'api'` as Problem 1. Distinguish them: Problem 1 is a missing file (rebuild fixes it); Problem 2 is a wrong directory (path fixes it). See also: [docker-compose-stack-startup-failures.md](../runtime-errors/docker-compose-stack-startup-failures.md), which covers a third cause — wrong `COPY` destination in the Dockerfile itself.

---

## Problem 3: Silent test failures after `verify_access_token` became `async def`

### Root cause

`verify_access_token` was refactored from `def` to `async def` (wrapping `jwt.decode` in `asyncio.to_thread` to avoid blocking the event loop). Three test functions that called it directly remained as plain `def`. Calling an `async def` from a sync context returns a coroutine object immediately without executing the function body — the assertion runs against an unawaited coroutine, not a `TokenPayload`. No exception is raised; the test appears to pass.

### Fix

Every test that calls an async function must be `async def`, `await` the call, and carry `@pytest.mark.asyncio`:

```python
# Before (broken after async refactor):
def test_create_and_verify_access_token():
    token = create_access_token(user_id, "teacher")
    payload = verify_access_token(token)   # returns coroutine object, never executes
    assert payload.sub == str(user_id)     # coroutine is truthy — assertion passes silently

def test_verify_access_token_expired_raises_401():
    with pytest.raises(HTTPException) as exc:
        verify_access_token(expired_token) # coroutine created, never run, no exception raised
    assert exc.value.status_code == 401    # fails — no exception was raised

# After (correct):
@pytest.mark.asyncio
async def test_create_and_verify_access_token():
    token = create_access_token(user_id, "teacher")
    payload = await verify_access_token(token)
    assert payload.sub == str(user_id)

@pytest.mark.asyncio
async def test_verify_access_token_expired_raises_401():
    with pytest.raises(HTTPException) as exc:
        await verify_access_token(expired_token)
    assert exc.value.status_code == 401
```

### Key mental model

`async def f()` does not execute when called from sync code — it returns a coroutine object. A plain `def` test has no event loop, so the call is a no-op that silently succeeds. `@pytest.mark.asyncio` spins up an event loop for the test and enables `await`. Rule: if the function under test is `async`, the test must be `async` too.

**Detection:** Add `filterwarnings = ["error::RuntimeWarning"]` to `[tool.pytest.ini_options]` in `pyproject.toml`. Python emits `RuntimeWarning: coroutine 'X' was never awaited`; promoting it to an error catches this class of silent failure immediately.

**Related:** [async-python-fastapi-sqlalchemy-impl-pitfalls.md](../runtime-errors/async-python-fastapi-sqlalchemy-impl-pitfalls.md) covers `asyncio.to_thread` (the production-side change that triggers this test-side conversion). [fastapi-jwt-cookie-auth-review-cluster.md](../security-issues/fastapi-jwt-cookie-auth-review-cluster.md) Issue 6 shows the specific `verify_access_token` async refactor at the dependency call site.

---

## Problem 4: Missing mock patches after `/auth/refresh` gained token rotation calls

### Root cause

The `/auth/refresh` endpoint was extended to implement token rotation: after validating the incoming refresh token, it now calls `revoke_refresh_token(jti, db)` and `create_refresh_token(user.id, db)` in addition to the existing `create_access_token`. The test `test_refresh_valid_token_returns_new_access_token` only patched `create_access_token`. The two new unmocked functions ran against the `AsyncMock` db session with no controlled return values, causing unexpected side effects and assertion failures.

### Fix

Patch every service function an endpoint calls. When an endpoint is extended, expand the patch surface to match:

```python
# Before (incomplete patches):
with patch("api.routers.auth.settings") as mock_cfg, \
     patch("api.routers.auth.create_access_token", return_value="new_access_tok"):
    # revoke_refresh_token and create_refresh_token run against AsyncMock db — unexpected
    resp = await client.post("/auth/refresh", cookies={"refresh_token": token})

assert resp.status_code == 200
# rotation not verified — no assertion on new refresh cookie

# After (all calls patched, rotation verified):
new_jti = uuid.uuid4()
with patch("api.routers.auth.settings") as mock_cfg, \
     patch("api.routers.auth.create_access_token", return_value="new_access_tok"), \
     patch("api.routers.auth.revoke_refresh_token", AsyncMock()), \
     patch("api.routers.auth.create_refresh_token",
           AsyncMock(return_value=("new_refresh_tok", new_jti))):
    mock_cfg.secret_key = _TEST_SECRET
    mock_cfg.access_token_expire_minutes = 15
    mock_cfg.refresh_token_expire_days = 7
    mock_cfg.cookie_secure = False
    resp = await client.post("/auth/refresh", cookies={"refresh_token": token})

assert resp.status_code == 200
assert resp.json()["mensaje"] == "Token renovado"
assert "access_token" in resp.cookies
assert "refresh_token" in resp.cookies  # rotation verified
```

### Key mental model

A unit test for an endpoint owns all collaborators via patches — it is a contract. If production code calls additional services, the test's patch surface must expand to match. Unmocked async service calls against a mock db session do not raise loudly; they silently produce unexpected `AsyncMock` return values that corrupt downstream assertions.

**Audit rule:** For every import at the top of the router module that could be invoked during a request, ask whether it is patched in the test.

**Related:** [phase-3-llm-guidance-pre-merge-review-fixes.md](../security-issues/phase-3-llm-guidance-pre-merge-review-fixes.md) Cluster 3 H2 shows the same pattern — patching `_get_redis` vs `aioredis.from_url` after a refactor.

---

## Prevention strategies

### Docker image freshness

- Run `docker compose build api` before running tests any time source files have changed.
- Treat `ModuleNotFoundError` for a known package as a build-staleness signal first — rebuild before investigating.
- `docker compose run` does not rebuild automatically; always rebuild explicitly.

### pytest working directory

- Use `docker compose run --rm api pytest api/tests/` — this starts at `/app` by default.
- Never `cd /app/api` before running pytest inside the container.
- If running interactively: `cd /app && python -m pytest api/tests/`.

### Async/sync test consistency checklist

When any function is changed from `def` to `async def`:

- [ ] Search the test suite for every call to that function by name
- [ ] For each call site: change `def test_*` → `async def test_*`
- [ ] Add `await` before each call
- [ ] Add `@pytest.mark.asyncio` (or set `asyncio_mode = "auto"` project-wide)
- [ ] Add `filterwarnings = ["error::RuntimeWarning"]` to `pyproject.toml` to make unawaited coroutines fail loudly

### Mock completeness checklist

When an endpoint gains new service calls:

- [ ] List every service function the endpoint now calls
- [ ] For each test that exercises that endpoint, verify a `patch` exists for each service call
- [ ] Add missing patches; set realistic return values
- [ ] Verify both success-path and error-path tests cover the new calls
- [ ] Assert the new mock was called: `mock.assert_called_once()` where applicable

### Makefile targets (recommended)

```makefile
.PHONY: test test-fast

build:
	docker compose build api

# Always rebuilds — safe for CI and after source changes
test: build
	docker compose run --rm api pytest api/tests/ -v

# Skip rebuild — use only when test files changed, not source files
test-fast:
	docker compose run --rm api pytest api/tests/ -v
```
