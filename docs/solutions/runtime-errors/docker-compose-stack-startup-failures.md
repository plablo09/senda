---
title: "Docker Compose Stack Startup Failures: Nginx DNS, Python COPY Path, ARM64 R Packages"
category: runtime-errors
date: 2026-03-20
tags:
  - docker
  - nginx
  - fastapi
  - celery
  - r
  - rocker
  - arm64
  - dns-resolution
  - proxy-pass
  - dockerfile
problem_type: configuration_error
components:
  - nginx/dev.conf
  - docker/Dockerfile.api
  - docker/Dockerfile.worker
  - docker/Dockerfile.r-geo
  - api/config.py
  - docker-compose.yml
---

# Docker Compose Stack Startup Failures

A cluster of infrastructure issues caused crash-loops that blocked smoke tests from passing. All five problems manifested at container startup time — the images built successfully, but services failed to come up. The fixes span nginx DNS configuration, Dockerfile COPY semantics, ARM64 R binary packages, image name alignment, and port binding.

---

## Problem 1: Nginx crash-loop — "host not found in upstream"

### Symptom

```
nginx: [emerg] host not found in upstream "api:8000" in /etc/nginx/nginx.conf:10
```

nginx container enters a crash-loop immediately on startup.

### Root Cause

Nginx resolves all `upstream {}` block hostnames at **startup time**. In Docker Compose, upstream containers (API, frontend) may not have registered themselves with Docker's embedded DNS yet when nginx starts. Result: fatal DNS failure at boot.

### Fix

1. Remove all `upstream {}` blocks.
2. Add `resolver 127.0.0.11 valid=10s;` — Docker's embedded DNS resolver.
3. Assign every upstream to a `set $var` variable and proxy to the variable — this defers DNS resolution to **request time**.

```nginx
events {}
http {
    resolver 127.0.0.11 valid=10s;
    server {
        listen 80;

        location /ws/ {
            set $api_upstream http://api:8000;
            proxy_pass $api_upstream;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 3600s;
        }

        location /api/ {
            set $api_upstream http://api:8000;
            rewrite ^/api/(.*) /$1 break;   # strip /api/ prefix before forwarding
            proxy_pass $api_upstream;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location / {
            set $frontend_upstream http://frontend;
            proxy_pass $frontend_upstream;
            proxy_set_header Host $host;
        }
    }
}
```

**Key rule:** If the target of `proxy_pass` is a Docker Compose service name, always use the `set $var` variable pattern. `upstream {}` blocks require the upstream to be resolvable at nginx startup — unsafe in any dynamic Docker environment.

### Secondary issue: 404 after nginx forwarding

FastAPI routes are registered as `/documentos` (no prefix). Nginx was forwarding `/api/documentos` verbatim. The `rewrite ^/api/(.*) /$1 break;` strips the `/api/` prefix before the request reaches FastAPI.

---

## Problem 2: Worker crash — `ModuleNotFoundError: No module named 'api'`

### Symptom

```
ModuleNotFoundError: No module named 'api'
```

Celery worker container exits immediately after starting.

### Root Cause

`COPY api/ .` copies the **contents** of `api/` flat into `/app/`. So `/app/main.py`, `/app/config.py`, etc. exist at the top level. The Python code uses `from api.config import settings` — expecting `api` to be a subdirectory package at `/app/api/`. The flat copy is structurally incompatible with package-qualified imports.

This is a subtle Docker COPY semantic: `COPY src/ dst/` copies the *contents* of `src/` into `dst/`. To preserve the directory as a named package, the destination must include the package name.

### Fix

```dockerfile
# Before (broken — flattens contents into /app/)
COPY api/ .
RUN pip install --no-cache-dir ".[dev]"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# After (correct — code lives at /app/api/ matching from api.* imports)
COPY api/ api/
RUN pip install --no-cache-dir "./api[dev]"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

Worker CMD must also be fully qualified:

```dockerfile
CMD ["celery", "-A", "api.celery_app", "worker", "--loglevel=info"]
```

**Rule of thumb:** The COPY destination should mirror the import path. If imports are `from api.X import Y`, use `COPY api/ api/`. If you use `.` as destination, every top-level `from pkg.X` must reference a package that lives directly in the working directory, not inside a renamed subdirectory.

---

## Problem 3: ARM64 R package compilation failure (`sf` / `s2`)

### Symptom

Docker build succeeds, but at runtime `library(sf)` fails — `sf` is not installed.

### Root Cause

`r-base:4.4.2` is Debian Bookworm with no pre-compiled ARM64 binaries for geospatial R packages. The `sf` dependency `s2` requires compiling Google's S2 geometry C++ library from source, which fails on arm64/Debian. The critical trap: **`install.packages()` prints a warning but returns successfully**, so the Docker build layer exits 0 with `sf` simply absent.

### Fix

Switch base image to `rocker/r-ver:4.4.2` (Ubuntu 24.04 + Posit Package Manager binary repository). Add explicit post-install validation to fail the build loudly instead of silently:

```dockerfile
FROM rocker/r-ver:4.4.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev libproj-dev libgeos-dev libudunits2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN Rscript -e " \
    pkgs <- c('sf','terra','ggplot2','dplyr','tidyr','tmap','leaflet','spdep'); \
    install.packages(pkgs); \
    missing <- setdiff(pkgs, rownames(installed.packages())); \
    if (length(missing) > 0) stop(paste('Failed to install:', paste(missing, collapse=', ')))"

WORKDIR /workspace
RUN useradd -m -u 1001 estudiante   # UID 1001: rocker/r-ver already has UID 1000
USER estudiante
```

**Note:** `rocker/geospatial` was tried first but is amd64-only. `rocker/r-ver` supports ARM64 and P3M provides pre-compiled geospatial binaries.

**Rule:** For production R workloads on ARM64, always use `rocker/r-ver` or a rocker-derived image. Use `r-base` only for pure-R scripts with zero compiled dependencies.

---

## Problem 4: Exec image name mismatch

### Symptom

Execution pool fails to launch containers; API logs show image-not-found errors.

### Root Cause

`api/config.py` had hardcoded defaults `senda-python-geo` / `senda-r-geo` but `docker-compose.yml` builds images named `senda-exec-python` / `senda-exec-r`.

### Fix

```python
# api/config.py
exec_python_image: str = "senda-exec-python"
exec_r_image: str = "senda-exec-r"
```

Update `.env` and `.env.example` to match. After the API image loads the new config, restart the API container to reinitialize the pool with fresh container IDs.

---

## Problem 5: Host port conflict

### Symptom

```
Error response from daemon: driver failed programming external connectivity on endpoint:
Bind for 0.0.0.0:3000 failed: port is already allocated
```

### Root Cause

`docker-compose.yml` bound `0.0.0.0:3000:80` for the frontend service. Another process on the host was already using port 3000.

### Fix

Remove the `ports:` binding from the frontend service. nginx handles all ingress routing; direct frontend port exposure was unnecessary. Only nginx needs a host port binding.

---

## Prevention

### Nginx in Docker Compose

- Always add `resolver 127.0.0.11 valid=10s;` in `http {}` when proxying to Docker service names
- Always use `set $var http://servicename:port;` + `proxy_pass $var;` — never bare `proxy_pass http://servicename`
- Smoke test: start nginx alone (without upstreams) and assert it stays running — any crash means eager DNS resolution is still present

### Dockerfile COPY for Python packages

- Before writing `COPY`, check: "what does the import look like?" If `from api.X import Y`, destination must be `api/`
- Smoke test: `docker run <image> python -c "from api.main import app"` — catches COPY path mismatches immediately

### ARM64 R packages

- End every `install.packages()` with a `setdiff` validation that calls `stop()` on missing packages — turns silent failure into a loud build failure
- Use `rocker/r-ver` for any image that needs geospatial R packages (`sf`, `terra`, `s2`, `tmap`)

### Config/image name consistency

- Define image names in one place (`.env`) and reference from both `docker-compose.yml` (via `${VAR}`) and Python config (`os.environ["VAR"]`)
- Any PR touching `docker-compose.yml` `image:` keys must simultaneously update all config.py / .env references

### Port binding

- Only the ingress service (nginx) needs `ports:` in docker-compose; all other services should use `expose:` only
- Add `make check-ports` target that runs `lsof -i :<port>` for each bound port as a pre-flight check
