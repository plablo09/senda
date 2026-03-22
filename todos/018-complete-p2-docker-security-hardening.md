---
status: complete
priority: p2
issue_id: "018"
tags: [code-review, security, docker, configuration]
dependencies: []
---

# Docker security hardening: parameterize POSTGRES_PASSWORD, restrict MinIO ports

## Problem Statement

Two pre-existing but easily-fixable security issues surfaced during the Phase 1 review. Both are in `docker-compose.yml`, which was modified in this PR, making now the right time to address them.

## Findings

### 1. POSTGRES_PASSWORD hardcoded as a literal in `docker-compose.yml`

**Location:** `docker-compose.yml:75`

```yaml
POSTGRES_PASSWORD: senda
```

Unlike all other service credentials (MinIO, LLM API key) which are sourced through `env_file: .env`, the Postgres password is a literal value in the compose file itself. This means:
- It's embedded in version history and visible to anyone with repo access
- It cannot be rotated without editing a committed file
- It diverges from the pattern used for every other secret in the stack

The `DATABASE_URL` in `.env` already encodes the password, but the `db` service uses a separate literal rather than deriving it from the same source.

### 2. MinIO admin console port (9001) bound to all host interfaces

**Location:** `docker-compose.yml:95-96`

```yaml
ports:
  - "9000:9000"
  - "9001:9001"
```

Both the MinIO S3 API (9000) and the MinIO web console admin port (9001) are bound to `0.0.0.0`. Port 9001 is the full admin UI — it allows listing, deleting, and overwriting all stored artifacts, and rotating MinIO credentials. Binding it to all interfaces exposes it to anyone on the same network (relevant in university labs, shared cloud VMs, or developer laptops on shared WiFi).

The S3 API (9000) has a legitimate reason to be reachable from localhost for direct artifact URL access. The admin console (9001) has no reason to be reachable outside the developer's own machine.

## Proposed Solutions

### Fix 1: Parameterize POSTGRES_PASSWORD

**`docker-compose.yml`:**
```yaml
db:
  environment:
    POSTGRES_DB: ${POSTGRES_DB:-senda}
    POSTGRES_USER: ${POSTGRES_USER:-senda}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
```

**`.env` and `.env.example`:** Add `POSTGRES_PASSWORD=senda` (dev) / `POSTGRES_PASSWORD=<fill-in>` (example).

Update `DATABASE_URL` in both files to use the same variable if desired, or keep them in sync by convention. The key is removing the hardcoded literal from the compose file.

### Fix 2: Restrict MinIO port binding

```yaml
minio:
  ports:
    - "127.0.0.1:9000:9000"   # S3 API — localhost only
    - "127.0.0.1:9001:9001"   # admin console — localhost only
```

Alternatively, remove the `9001` port binding entirely — the admin console is only used for manual inspection and can be accessed via `docker compose exec minio` when needed.

## Acceptance Criteria

- [ ] `POSTGRES_PASSWORD` is sourced from `.env` via `${POSTGRES_PASSWORD}` in `docker-compose.yml`
- [ ] `.env.example` updated with `POSTGRES_PASSWORD=` placeholder
- [ ] MinIO ports bound to `127.0.0.1` (or admin port 9001 removed)
- [ ] Stack still starts and artifacts are reachable via `http://localhost:9000`

## Work Log

- 2026-03-22: POSTGRES_PASSWORD flagged as P1 by security-sentinel (pre-existing, not introduced in this PR but touched in this diff); MinIO ports flagged as P2 by security-sentinel. Assigned P2 here given greenfield/dev-only context.
