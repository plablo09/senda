---
status: pending
priority: p2
issue_id: "008"
tags: [code-review, architecture, storage, configuration]
dependencies: []
---

# url_artefacto stores internal MinIO hostname — not browser-reachable

## Problem Statement

`upload_html()` returns `f"{settings.storage_endpoint}/{settings.storage_bucket}/{key}"` where `storage_endpoint` defaults to `http://minio:9000` — the Docker-internal hostname. This URL is written to `doc.url_artefacto` and returned in every `DocumentoResponse`. A browser cannot reach `http://minio:9000`. Teachers will get a broken link for every rendered document.

## Findings

- `api/services/storage.py:34` — constructs URL from `settings.storage_endpoint`
- `api/config.py:9` — `storage_endpoint: str = "http://minio:9000"` (internal Docker hostname)
- `api/.env.example:8` — same default

## Proposed Solutions

### Option A: Add STORAGE_PUBLIC_ENDPOINT setting (recommended)
```python
# api/config.py
storage_public_endpoint: str = "http://localhost:9000"
```

```python
# api/services/storage.py
return f"{settings.storage_public_endpoint}/{settings.storage_bucket}/{key}"
```

Nginx can proxy `/artefactos/` → `http://minio:9000/senda-documentos/` for cleaner URLs.

- **Pros:** Clean separation of internal vs public access; works for all deployment tiers
- **Cons:** One more env var to configure
- **Effort:** Small
- **Risk:** Low

### Option B: Generate MinIO presigned URLs
Use `client.generate_presigned_url("get_object", ...)` with a configurable TTL.

- **Pros:** No public bucket exposure; built-in access control
- **Cons:** URLs expire; students can't bookmark rendered lessons
- **Effort:** Small-Medium
- **Risk:** Low

## Recommended Action

Option A with an nginx proxy rule for clean URLs. Option B for production authentication phase.

## Technical Details

- **Affected files:** `api/services/storage.py:34`, `api/config.py`, `.env.example`
- **Also:** `docker-compose.yml` — MinIO ports are `0.0.0.0:9000:9000`, should be `127.0.0.1:9000:9000` in dev

## Acceptance Criteria

- [ ] `doc.url_artefacto` contains a URL reachable from a browser (not `http://minio:9000/...`)
- [ ] `STORAGE_PUBLIC_ENDPOINT` documented in `.env.example`
- [ ] MinIO port binding uses `127.0.0.1` in docker-compose

## Work Log

- 2026-03-20: Identified by architecture-strategist (P3-D), security-sentinel (P3-A, P3-B)
