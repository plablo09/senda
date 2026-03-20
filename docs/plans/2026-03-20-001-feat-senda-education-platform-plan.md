---
title: "Senda — Interactive Geographic & Statistical Education Platform"
type: feat
status: active
date: 2026-03-20
---

# Senda — Interactive Geographic & Statistical Education Platform

## Overview

Senda is a web application that lets teachers — proficient in Python and R but unfamiliar with publishing tools like Quarto — create high-quality interactive educational materials for geographic and statistical analysis. Students consume those materials entirely in the browser, running Python and R code server-side (no install required), guided through errors and improvements by an LLM tutor.

The UI is in **Spanish** throughout (both teacher-facing and student-facing). Code and documentation are in English.

The platform is deployed on a **private OpenStack cloud** and is fully runnable **locally via docker-compose** for development.

---

## Problem Statement

Distance-learning educators in geographic and statistical disciplines face a painful gap: they are domain experts who can write Python and R, but they cannot produce the interactive, self-correcting study materials their remote students need without learning an entirely different publishing stack (Quarto, Pandoc, YAML, HTML). Existing platforms either require students to install software, are notebook-centric without a teacher/student role split, or lack LLM-powered tutoring.

**Critical constraint:** The geographic analysis domain requires libraries with native C/C++ system dependencies — `geopandas` (Python: GDAL, GEOS, PROJ) and `sf` (R: GDAL, GEOS, PROJ) — that cannot run in the browser via WebAssembly (Pyodide/WebR). Code execution must be server-side.

**Core user pain:**
> "Sé cómo escribir el ejercicio y la solución. Lo que no sé es cómo convertirlo en algo que el estudiante pueda ejecutar en su navegador y recibir ayuda cuando se atasca."

---

## Proposed Solution

### For Teachers (Authoring Side)

A browser-based **block editor** (in Spanish) where each block maps to a Quarto document construct. Teachers compose lessons by adding and configuring blocks — text, code exercises, hints, solutions, callouts, dataset loaders — without ever seeing `.qmd` syntax. On save, the server serializes the editor state to `.qmd`, renders it to HTML in a background job, and returns a shareable student link.

### For Students (Learning Side)

A Quarto-rendered HTML document served by the application. Code cells are interactive: students edit and run code in the browser, which executes server-side in an isolated Docker container that has the full geographic/statistical stack installed. Output (text, plots, maps) streams back and renders inline. On error, an LLM hint appears below the cell without revealing the solution.

---

## Technical Approach

### Why Not Pyodide/WebR?

`geopandas` requires GDAL, GEOS, and PROJ — native C/C++ libraries that are not compiled for WebAssembly and are not available in Pyodide's package repository. Similarly, `sf` in R requires GDAL/GEOS/PROJ at the system level. Server-side execution in a pre-configured Docker container is the only viable path.

### Why Not JupyterHub + Thebe?

JupyterHub + Thebe would give students a Jupyter experience bleeding through the Quarto shell — Jupyter widget chrome, notebook-centric mental model. A custom Quarto extension (Lua filter + JavaScript client) gives students a **pure Quarto document** with code cells that talk to our execution API. The teacher and student experience stays Quarto-native throughout.

### Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│              TEACHER WEB APP (en español)              │
│                                                        │
│  BlockNote editor (React + TypeScript)                 │
│  Nodos personalizados: Ejercicio, Pista, Solución,     │
│  Nota, CargadorDatos                                   │
│       ↓ guardar (JSON AST vía REST)                    │
│  FastAPI backend                                       │
│       ↓ encolar                                        │
│  Celery worker                                         │
│    ├─ serialize JSON AST → .qmd                        │
│    ├─ quarto render → HTML                             │
│    └─ upload HTML → MinIO / OpenStack Swift            │
│       ↓ WebSocket: "documento listo"                   │
│  Docente recibe enlace compartible                     │
└────────────────────────────────────────────────────────┘
                        ↓ link compartido
┌────────────────────────────────────────────────────────┐
│           DOCUMENTO ESTUDIANTE (en español)            │
│                                                        │
│  HTML renderizado por Quarto (servido por FastAPI)     │
│  Extensión Senda (.lua filter + JS bundle)             │
│  ├── Editor CodeMirror por celda de ejercicio          │
│  ├── "Ejecutar" → WebSocket → Execution API            │
│  │      → Docker container (Python + R + geo stack)    │
│  │      ← stdout / stderr / imágenes (stream)          │
│  └── En error → POST /api/retroalimentacion            │
│         → Claude API → pista socrática inline          │
└────────────────────────────────────────────────────────┘
                        ↑
┌────────────────────────────────────────────────────────┐
│              EXECUTION API                             │
│                                                        │
│  FastAPI + WebSocket                                   │
│  Pool de contenedores pre-calentados                   │
│  ├── Python: geopandas, GDAL, PROJ, GEOS,             │
│  │          pandas, numpy, matplotlib,                 │
│  │          folium, plotly, scipy, scikit-learn        │
│  └── R: sf, terra, ggplot2, dplyr, tmap,              │
│         tidyr, leaflet, spdep                          │
│  Redis: session_id → container_id                     │
│  Límite de tiempo: 30 min inactividad → cleanup        │
└────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | **FastAPI** (Python 3.12) | Team knows Python; async WebSocket support; subprocess calls to Quarto CLI |
| Background jobs | **Celery** + Redis | Quarto rendering is CPU-bound (~5–30s); must be async |
| Database | **PostgreSQL** | JSONB columns for editor AST; text columns for `.qmd` source |
| Block editor | **BlockNote** (React + TypeScript) | Notion-like UX; custom node support; built on Tiptap/ProseMirror |
| Frontend shell | **React + Vite + TypeScript** | Pairs naturally with BlockNote |
| Quarto integration | **Custom Lua filter + JS client** | Replaces quarto-live with server-side execution; keeps Quarto aesthetic |
| Execution runtime | **Docker SDK** (`docker-py`) + container pool | Isolated sessions; full native library support (GDAL, GEOS, PROJ) |
| Artifact storage | **MinIO** (local dev) / **OpenStack Swift** (prod) | S3-compatible API; runs locally via docker-compose |
| LLM provider | **LiteLLM** abstraction layer | Single API for 100+ providers; swap via env vars — Ollama locally, any cloud provider in production |
| LLM (local/dev) | **Ollama** + Llama 3.2 (3B/8B) | Free, runs in Docker, no API key, included in docker-compose |
| LLM (production) | Configurable (Anthropic, OpenAI, Groq, Gemini…) | Set `LLM_MODEL` + `LLM_API_KEY` env vars; no code changes needed |
| Deployment | **Docker Compose** — any target | Single VM, multi-VM, or OpenStack; same images everywhere, only env vars differ |
| Reverse proxy | **Nginx** | Handles HTTPS, WebSocket upgrade, static file serving |

### Custom Quarto Extension: `senda-live`

This is the key technical innovation — a Quarto extension that provides the same interactive cell experience as `quarto-live` but executes code server-side.

**Lua filter** (`_extensions/senda/live/filter.lua`):
- Transforms fenced code cells with `#| exercise: ...` options into HTML with `data-senda-*` attributes
- Injects the `senda-live.js` bundle and CodeMirror into the rendered HTML
- Sets `data-execution-url` attribute from a document-level parameter (the WebSocket endpoint)

**JavaScript client** (`senda-live.js`):
- Finds all `[data-senda-exercise]` elements on page load
- Wraps each in a CodeMirror 6 editor (preserving starter code)
- On "Ejecutar": opens a WebSocket to the Execution API, streams output tokens, renders plots from base64 PNG responses
- On error: POSTs to `/api/retroalimentacion`, renders LLM hint inline
- Shows/hides hints and solutions on demand

**Document format** (teacher-authored, same structure as quarto-live):

````markdown
---
title: "Análisis Espacial con GeoPandas"
format: senda-html
params:
  execution_url: "wss://senda.example.com/ws/ejecutar"
---

## Ejercicio 1

Carga el shapefile de municipios e inspecciona su sistema de coordenadas.

```{python}
#| exercise: ex_crs
#| caption: "Carga el archivo e imprime el CRS"
import geopandas as gpd
gdf = gpd.read_file("data/municipios.shp")
____
```

```{python}
#| exercise: ex_crs
#| solution: true
import geopandas as gpd
gdf = gpd.read_file("data/municipios.shp")
print(gdf.crs)
```

```{python}
#| exercise: ex_crs
#| hint: true
# Usa el atributo .crs del GeoDataFrame
```
````

### Execution API: Container Pool

```python
# api/services/execution_pool.py (pseudocode)

class ContainerPool:
    """
    Maintains a pool of pre-warmed Docker containers.
    Each student session gets one container for its duration.
    Containers are returned to the pool (or destroyed) on session end.
    """
    async def acquire(self, session_id: str, language: str) -> Container:
        # Get a warm container, or spin up a new one if pool is empty
        ...

    async def execute(self, session_id: str, code: str) -> AsyncIterator[OutputChunk]:
        # docker exec into the container, stream stdout/stderr
        ...

    async def release(self, session_id: str):
        # Return container to pool; reset working directory
        ...
```

**Session → container mapping in Redis:**
```
session:{session_id}:container_id  → "abc123"   TTL: 30min
session:{session_id}:language      → "python"   TTL: 30min
```

**Container images:**

```dockerfile
# docker/Dockerfile.python-geo
FROM python:3.12-slim

RUN apt-get install -y gdal-bin libgdal-dev libproj-dev libgeos-dev

RUN pip install \
    geopandas==1.x \
    pandas numpy matplotlib scipy scikit-learn statsmodels \
    folium plotly pyproj shapely fiona \
    jupyter-client ipykernel   # for code execution protocol
```

```dockerfile
# docker/Dockerfile.r-geo
FROM r-base:4.4

RUN apt-get install -y libgdal-dev libproj-dev libgeos-dev

RUN Rscript -e "install.packages(c('sf','terra','ggplot2','dplyr','tmap','leaflet','spdep'))"
```

### `.qmd` Serializer

The serializer converts the BlockNote JSON AST to a valid `.qmd` string. Front matter is built with PyYAML (never raw f-strings) to avoid YAML injection:

```python
# api/services/qmd_serializer.py

import yaml

def build_front_matter(doc: dict) -> str:
    fm = {
        "title": doc["title"],
        "format": "senda-html",
        "params": {
            "execution_url": doc["execution_url"],  # injected at render time
        },
    }
    return f"---\n{yaml.dump(fm, allow_unicode=True)}---\n"

def serialize_exercise(node: dict) -> str:
    lang = node["attrs"]["language"]  # "python" or "r"
    exercise_id = node["attrs"]["exerciseId"]
    starter = node["attrs"]["starterCode"]
    solution = node["attrs"].get("solutionCode", "")
    hints = node["attrs"].get("hints", [])

    parts = [
        f"```{{{lang}}}",
        f"#| exercise: {exercise_id}",
        f"#| caption: \"{node['attrs']['caption']}\"",
        starter,
        "```",
    ]
    if solution:
        parts += [f"```{{{lang}}}", f"#| exercise: {exercise_id}",
                  "#| solution: true", solution, "```"]
    for hint in hints:
        parts += [f"```{{{lang}}}", f"#| exercise: {exercise_id}",
                  "#| hint: true", hint, "```"]
    return "\n".join(parts)
```

### LLM Feedback (Student-Side Only)

The LLM integration is **student-facing only** — it guides students through errors without revealing answers. Teacher authoring uses no LLM assistance.

#### Provider Abstraction via LiteLLM

[LiteLLM](https://docs.litellm.ai/) provides a unified Python API across all major LLM providers. The same `litellm.completion()` call works regardless of whether the backend is Ollama running locally or Claude in production. The provider is selected entirely through environment variables — no code changes required.

```python
# api/services/llm_feedback.py

import litellm
from api.config import settings

async def get_socratic_feedback(exercise: Exercise, payload: FeedbackRequest) -> Feedback:
    response = await litellm.acompletion(
        model=settings.LLM_MODEL,           # e.g. "ollama/llama3.2" or "anthropic/claude-haiku-4-5-20251001"
        api_base=settings.LLM_API_BASE,     # "http://ollama:11434" locally, None for cloud providers
        api_key=settings.LLM_API_KEY,       # None for Ollama, set for cloud providers
        messages=[
            {"role": "system", "content": SOCRATIC_TUTOR_SYSTEM_PROMPT_ES},
            {"role": "user", "content": build_prompt(exercise, payload)},
        ],
        response_format={"type": "json_object"},  # structured output (supported by most providers)
    )
    return parse_feedback(response)
```

#### Configuration by Environment

```bash
# .env.local  — development (free, no API key)
LLM_MODEL=ollama/llama3.2
LLM_API_BASE=http://ollama:11434
LLM_API_KEY=

# .env.production  — Anthropic
LLM_MODEL=anthropic/claude-haiku-4-5-20251001
LLM_API_BASE=
LLM_API_KEY=sk-ant-...

# .env.production  — OpenAI
LLM_MODEL=gpt-4o-mini
LLM_API_BASE=
LLM_API_KEY=sk-...

# .env.production  — Groq (free tier available)
LLM_MODEL=groq/llama-3.1-8b-instant
LLM_API_BASE=
LLM_API_KEY=gsk_...
```

#### Ollama in docker-compose (Local Dev)

Ollama runs as a service in docker-compose. On first startup it pulls the configured model:

```yaml
# docker-compose.yml (addition)
  ollama:
    image: ollama/ollama
    volumes:
      - ollama_data:/root/.ollama
    # GPU passthrough (optional — works without GPU, just slower)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - capabilities: [gpu]
    entrypoint: >
      sh -c "ollama serve & sleep 3 && ollama pull llama3.2 && wait"
```

#### System Prompt

Spanish, Socratic, never reveals the answer:
> "Eres un tutor de análisis geográfico y estadístico. Cuando un estudiante comete un error, explica el concepto detrás del error usando una analogía sencilla, luego formula **una sola pregunta guía** que redirija su pensamiento. Nunca proporciones el código corregido. Mantén tus respuestas en menos de 80 palabras y en español."

#### Feedback Endpoint

```python
# api/routers/retroalimentacion.py

@router.post("/retroalimentacion/{exercise_id}")
async def get_feedback(exercise_id: str, payload: FeedbackRequest, request: Request):
    session_id = request.cookies.get("session_id")
    if not await rate_limiter.allow(session_id, exercise_id):
        raise HTTPException(429, "Demasiadas solicitudes. Intenta de nuevo en un momento.")

    exercise = await db.get_exercise(exercise_id)
    return await llm_feedback.get_socratic_feedback(exercise, payload)
```

### Local Development with docker-compose

The full stack runs locally with a single command:

```yaml
# docker-compose.yml (sketch)

services:
  api:
    build: docker/Dockerfile.api
    environment:
      DATABASE_URL: postgresql://senda:senda@db/senda
      REDIS_URL: redis://redis:6379
      STORAGE_ENDPOINT: http://minio:9000
      LLM_MODEL: ${LLM_MODEL:-ollama/llama3.2}
      LLM_API_BASE: ${LLM_API_BASE:-http://ollama:11434}
      LLM_API_KEY: ${LLM_API_KEY:-}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Docker-in-Docker for container pool
    depends_on: [db, redis, minio]

  worker:
    build: docker/Dockerfile.worker  # includes Quarto CLI
    environment:
      DATABASE_URL: postgresql://senda:senda@db/senda
      REDIS_URL: redis://redis:6379
      STORAGE_ENDPOINT: http://minio:9000
    depends_on: [db, redis, minio]

  frontend:
    build: docker/Dockerfile.frontend
    ports:
      - "3000:3000"

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: senda
      POSTGRES_USER: senda
      POSTGRES_PASSWORD: senda
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: senda
      MINIO_ROOT_PASSWORD: senda_dev
    ports:
      - "9000:9000"
      - "9001:9001"  # MinIO console
    volumes:
      - minio_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "8080:80"
    volumes:
      - ./nginx/dev.conf:/etc/nginx/nginx.conf

  # Pre-warmed geo execution containers (started once, reused)
  exec-python:
    build: docker/Dockerfile.python-geo
    command: sleep infinity  # kept alive, code exec'd via docker exec
    deploy:
      replicas: 3  # small local pool

  exec-r:
    build: docker/Dockerfile.r-geo
    command: sleep infinity
    deploy:
      replicas: 2

  ollama:
    image: ollama/ollama
    volumes:
      - ollama_data:/root/.ollama
    entrypoint: >
      sh -c "ollama serve & sleep 3 && ollama pull llama3.2 && wait"
```

**One command to run everything:**
```bash
docker compose up --build
# Teacher app: http://localhost:8080
# MinIO console: http://localhost:9001
```

### Deployment Targets

The architecture is designed to run identically across all environments via docker-compose. There are no code or image changes between environments — only environment variables and the nginx config differ.

#### Tier 1: Single VM (Simplest Production Path)

Any Linux VM with Docker installed runs the full stack with `docker compose up`. This is the recommended starting point for production.

```
Single VM (recommended: 16 GB RAM, 4–8 vCPU)
├── docker-compose.yml (all services on one host)
│   ├── api, worker, frontend, nginx
│   ├── postgres, redis
│   ├── minio  ← object storage on the VM's disk
│   ├── ollama ← LLM on the VM (uses ~5–8 GB RAM for llama3.2 8B)
│   └── exec-python × N, exec-r × N  ← geo execution containers
└── nginx with Let's Encrypt (certbot) for HTTPS
```

**Environment variables that change from local dev:**

```bash
# .env.vm
DATABASE_URL=postgresql://senda:STRONG_PASSWORD@db/senda
DOMAIN=senda.example.com
STORAGE_ENDPOINT=http://minio:9000          # MinIO still on the VM
# Or point to external object storage:
# STORAGE_ENDPOINT=https://object.openstack.example.com
LLM_MODEL=ollama/llama3.2                   # Ollama on the same VM
# Or switch to a cloud provider:
# LLM_MODEL=anthropic/claude-haiku-4-5-20251001
# LLM_API_KEY=sk-ant-...
```

**VM sizing guide:**

| Students (concurrent) | vCPU | RAM | Notes |
|---|---|---|---|
| Up to 10 | 4 | 8 GB | Use llama3.2 3B model; 2–3 exec containers |
| Up to 30 | 8 | 16 GB | llama3.2 8B; 5–6 exec containers |
| Up to 60 | 16 | 32 GB | Consider splitting services (Tier 2) |

**HTTPS on a single VM** — add Certbot to the nginx container or use a companion container:

```yaml
# docker-compose.yml addition for production VM
  certbot:
    image: certbot/certbot
    volumes:
      - certbot_certs:/etc/letsencrypt
      - certbot_www:/var/www/certbot
```

#### Tier 2: Multi-VM / OpenStack (Scalable)

When the single VM becomes a bottleneck, split services across VMs. The same Docker images are used — only the compose files and env vars change.

| Local / Single VM | Multi-VM / OpenStack |
|---|---|
| MinIO on the VM | OpenStack Swift (or MinIO on a dedicated storage VM) |
| nginx on localhost | OpenStack LBaaS + nginx VM |
| Docker socket on same host | Docker socket on a dedicated execution VM |
| All services in one compose | Services split across VM roles |
| `.env` file | OpenStack secrets or a secrets manager |

**Suggested VM roles for OpenStack:**

```
app-vm       → api, worker, frontend, nginx, redis
db-vm        → postgres
storage-vm   → minio (or use OpenStack Swift directly)
exec-vm      → exec-python × N, exec-r × N (+ docker.sock exposed only to app-vm)
llm-vm       → ollama (GPU VM optional; or use cloud LLM API)
```

No code changes are needed to move between tiers — docker-compose files are split and env vars are updated to point services at their new hosts.

---

## Development Workflow

### Branching Strategy: Trunk-Based Development

`main` is always deployable and protected. All work happens on short-lived feature branches (target: 1–3 days) that merge back via PR with squash merge.

```
main  ←  feat/block-editor-exercise-node   (squash merge)
      ←  fix/container-pool-cleanup
      ←  chore/setup-ci-pipeline
      ←  refactor/qmd-serializer-yaml
```

**Branch naming convention:** `feat/`, `fix/`, `refactor/`, `chore/` + kebab-case description.

No `develop` branch — the extra ceremony is not worth it at this team size. If a feature is too large to land in 3 days, break it into smaller PRs or hide it behind a feature flag.

### PR Workflow

- Every change to `main` requires a PR — no direct commits
- PRs are small and focused: one concern per PR
- **Squash merge** keeps `main` history linear and readable
- PR template (`.github/pull_request_template.md`) includes:
  - [ ] Tests pass locally (`make test`)
  - [ ] All new UI text is in Spanish
  - [ ] No API keys or secrets in the diff (`make lint-secrets`)
  - [ ] Relevant acceptance criteria from the plan checked off

### CI Pipeline (GitHub Actions)

Runs on every PR. All steps must pass before merge is allowed.

```
1. lint
   ├── ruff + black (Python)
   └── ESLint + Prettier (TypeScript)

2. unit tests
   ├── pytest (API: serializer, LLM proxy, render task)
   └── vitest (frontend: node serializers, editor utils)

3. build Docker images
   └── docker build for api, worker, frontend, python-geo, r-geo

4. integration smoke test
   └── docker compose up (full stack)
      → pytest tests/integration/ (render cycle, geo execution, LLM key isolation)
      → docker compose down
```

On merge to `main`, a deploy job runs:
```bash
ssh deploy@vm "cd /srv/senda && git pull && docker compose pull && docker compose up -d"
```

### Test Strategy

**Test-first where it pays off most:**

| Component | Approach | Why |
|---|---|---|
| `qmd_serializer.py` | TDD (write tests first) | Pure function; fast; regressions are silent and costly |
| `llm_feedback.py` | Unit test with mocked LiteLLM | Test prompt construction and response parsing without LLM cost |
| `execution_pool.py` | Integration test (needs Docker) | Container lifecycle can't be meaningfully mocked |
| BlockNote custom nodes | Unit test serializer functions | Pure TypeScript; fast feedback |
| Full editor flow | Playwright E2E | Validates the teacher authoring path end-to-end |
| `filter.lua` + `senda-live.js` | Integration test | Render known `.qmd` → assert CodeMirror + WebSocket URL injected |

**Test layout:**
```
api/
  tests/
    unit/
      test_qmd_serializer.py     ← TDD, fast, no Docker
      test_llm_feedback.py       ← mocked LiteLLM
    integration/
      test_render_cycle.py       ← needs full docker-compose stack
      test_execution_pool.py     ← needs Docker daemon
      test_llm_key_isolation.py  ← asserts no keys in student HTML
frontend/
  src/
    editor/__tests__/
      serializer.test.ts         ← vitest unit tests
  e2e/
    editor.spec.ts               ← Playwright
```

### Local Tooling: Makefile

All common developer commands are available via `make`:

```makefile
# Start full stack
up:         docker compose up --build
down:       docker compose down

# Testing
test:       docker compose run --rm api pytest tests/unit/
test-int:   docker compose run --rm api pytest tests/integration/
test-e2e:   pnpm --filter frontend exec playwright test

# Linting & formatting
lint:       docker compose run --rm api ruff check . && black --check .
fmt:        docker compose run --rm api ruff check --fix . && black .
lint-fe:    pnpm --filter frontend exec eslint . && prettier --check .
fmt-fe:     pnpm --filter frontend exec prettier --write .
lint-secrets: detect-secrets scan --baseline .secrets.baseline

# Utilities
shell-api:  docker compose exec api bash
shell-db:   docker compose exec db psql -U senda senda
logs:       docker compose logs -f api worker
logs-llm:   docker compose logs -f ollama
```

### Pre-commit Hooks

`.pre-commit-config.yaml` runs automatically on `git commit`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks: [ruff, ruff-format]
  - repo: https://github.com/Yelp/detect-secrets
    hooks: [detect-secrets]   # catches accidental API key commits
  - repo: https://github.com/pre-commit/mirrors-prettier
    hooks: [prettier]
```

### Dependency Philosophy: Docker is the Runtime

**The deployment target only needs Docker Engine + Docker Compose.** Nothing else — not Python, R, Node.js, Quarto, GDAL, Ollama, or any application dependency — is installed on the VM. Everything runs inside containers.

Local developer tooling is installed on developer machines for **faster feedback loops and IDE support**, not because the application requires them on the host.

| Tool | Installed on dev machine | Installed on deployment VM | Purpose |
|---|---|---|---|
| Docker + Compose | ✅ (already present) | ✅ (only requirement) | Runs everything |
| Python 3.12 + uv | ✅ recommended | ❌ | IDE type-checking, fast unit tests without Docker |
| Quarto | ✅ recommended | ❌ | Local `.qmd` preview; runs in worker container on server |
| pre-commit | ✅ recommended | ❌ | Git hooks on commit; CI enforces same checks |
| Node.js | ✅ (already present) | ❌ | Frontend dev server, IDE support |
| R, GDAL, geopandas | optional | ❌ | Only needed if you want to run geo code outside Docker |
| Ollama | optional | ❌ | Runs in Docker; install on host only if you want a local CLI |

**Deployment VM setup is three commands:**

```bash
# 1. Install Docker (once)
curl -fsSL https://get.docker.com | sh

# 2. Clone and configure
git clone <repo> /srv/senda
cp .env.example /srv/senda/.env   # fill in domain, passwords, LLM config

# 3. Start everything
cd /srv/senda && docker compose up -d
```

Any plain Linux VM — regardless of pre-installed software — is a valid deployment target.

### Developer Machine Setup (One-Time)

```bash
# Install missing tools (for dev experience — not required by the app)
brew install --cask quarto       # local document preview
brew install uv                  # Python package manager + virtualenv
brew install pre-commit          # git hooks

# Install Python 3.12 (plan targets 3.12; pyenv already present)
pyenv install 3.12.10
# Set per-project inside senda/: pyenv local 3.12.10

# After cloning the repo:
pre-commit install               # activates git hooks
docker compose up --build        # starts full stack; Ollama pulls llama3.2 on first run
```

**Node.js note:** v25.7.0 is the current/unstable release. Consider pinning to Node 22 LTS via `.nvmrc` for CI parity. Works as-is for local development.

---

## Directory Layout

```
senda/
├── api/                            # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── documentos.py           # CRUD for lessons
│   │   ├── retroalimentacion.py    # LLM proxy endpoint
│   │   └── renderizados.py         # render status + artifact URLs
│   ├── services/
│   │   ├── qmd_serializer.py       # JSON AST → .qmd string
│   │   ├── renderer.py             # quarto render subprocess wrapper
│   │   ├── execution_pool.py       # Docker container pool manager
│   │   └── llm_feedback.py         # LiteLLM wrapper (provider-agnostic)
│   ├── tasks/
│   │   └── render_task.py          # Celery: render + upload
│   ├── config.py                   # Settings (LLM_MODEL, LLM_API_BASE, LLM_API_KEY, etc.)
│   └── models/                     # SQLAlchemy models
├── frontend/                       # React + Vite teacher app (Spanish UI)
│   ├── src/
│   │   ├── editor/
│   │   │   ├── SendaEditor.tsx
│   │   │   └── nodes/
│   │   │       ├── EjercicioNode.tsx
│   │   │       ├── PistaNode.tsx
│   │   │       ├── SolucionNode.tsx
│   │   │       └── NotaNode.tsx
│   │   ├── pages/
│   │   │   ├── Inicio.tsx          # Dashboard (Spanish)
│   │   │   ├── Editor.tsx
│   │   │   └── Vista.tsx           # Preview
│   │   └── i18n/
│   │       └── es.json             # Spanish strings
├── _extensions/
│   └── senda/
│       └── live/                   # Custom Quarto extension
│           ├── _extension.yml
│           ├── filter.lua          # Transforms cells → HTML with data-senda attrs
│           └── senda-live.js       # CodeMirror + WebSocket client
├── _quarto.yml                     # Project config
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker           # Includes Quarto CLI
│   ├── Dockerfile.frontend
│   ├── Dockerfile.python-geo       # Execution container: Python + geo stack
│   └── Dockerfile.r-geo            # Execution container: R + geo stack
├── docker-compose.yml
├── nginx/
│   ├── dev.conf
│   └── prod.conf
├── .gitignore
└── AGENTS.md
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Local Stack + Render Pipeline)

**Goal:** Full docker-compose stack runs locally. A `.qmd` with the custom `senda-live` extension renders, and a student can run a simple Python cell (non-geo first) via the execution API.

**Tasks:**
- `docker-compose.yml` with all services: API, worker, frontend, db, redis, minio, nginx, exec-python, exec-r
- FastAPI app scaffold with health check endpoint
- PostgreSQL schema: `documentos` (id, titulo, ast JSONB, qmd_source TEXT, estado_render, url_artefacto)
- Celery + Redis; `render_task.py` calling `quarto render` subprocess
- MinIO bucket setup + upload logic (S3-compatible, identical API to OpenStack Swift)
- `_extensions/senda/live/` scaffold: Lua filter that marks cells with `data-senda-*` attributes
- `senda-live.js`: CodeMirror 6 editor + WebSocket client (basic: send code, receive stdout)
- Execution API WebSocket endpoint: `docker exec` into pre-warmed container, stream output
- Redis session → container mapping with 30-min TTL
- Docker images: `Dockerfile.python-geo` (with geopandas + GDAL), `Dockerfile.r-geo` (with sf)
- Quarto installed in `Dockerfile.worker` via official installer
- `.gitignore`, `AGENTS.md`, `pyproject.toml` with `uv`
- End-to-end test: write `.qmd` → render → open in browser → run `import geopandas; print(geopandas.__version__)` → see output

**Success criteria:**
- `docker compose up --build` starts the full stack with no manual steps
- A Python cell with `import geopandas as gpd` executes successfully
- An R cell with `library(sf)` executes successfully
- Quarto render completes in < 45 seconds

### Phase 2: Block Editor (Teacher Authoring)

**Goal:** Teachers can build a full lesson in Spanish without seeing `.qmd` syntax.

**Tasks:**
- React + Vite + TypeScript scaffold (`frontend/`)
- BlockNote integration with custom Spanish-labeled nodes: `EjercicioNode`, `PistaNode`, `SolucionNode`, `NotaNode`, `CargadorDatosNode`
- `EjercicioNode` UI: language selector (Python/R), caption field (Spanish label: "Título del ejercicio"), starter code editor, hidden solution editor, hint textarea
- `serializer.ts` — BlockNote JSON AST → API payload
- `qmd_serializer.py` — API payload → `.qmd` string (PyYAML for front matter)
- Teacher dashboard (`Inicio.tsx`): lesson list, create new, open existing — all in Spanish
- Live preview panel: iframe showing last rendered artifact + "Actualizar vista previa" button
- Dataset upload: teacher uploads CSV/GeoJSON → stored in MinIO → URL embedded in document setup cell
- WebSocket notification: "Tu documento está listo" toast when render completes

**Success criteria:**
- A teacher with no Quarto knowledge creates a 3-exercise lesson in < 20 minutes
- All UI text is in Spanish (no English visible to users)
- Rendered document has correct exercise structure with CodeMirror editors

### Phase 3: LLM Student Guidance

**Goal:** Students receive Socratic guidance in Spanish when their code fails.

**Tasks:**
- `retroalimentacion.py` router + `llm_feedback.py` service using LiteLLM
- Structured output schema via `response_format: json_object`: `{ diagnostico: str, pregunta_guia: str, referencia_concepto: str, mostrar_pista: bool }`
- Rate limiter: 10 feedback requests per exercise per session (Redis token bucket)
- Frontend: LLM hint renders below code cell on error; "Pedir ayuda" button for proactive hints
- System prompt tuned for geographic/statistical concepts in Spanish
- API key (if set) never sent to browser (validated in integration test; Ollama has no key to leak)
- Ollama service in docker-compose pulls `llama3.2` model automatically on first start
- LLM provider documented in `AGENTS.md`: set `LLM_MODEL` / `LLM_API_BASE` / `LLM_API_KEY` to switch providers
- Teacher view: error frequency heatmap per exercise (aggregate, no individual student data)

**Success criteria:**
- LLM hint appears within 5 seconds of a code execution error
- Hint text is in Spanish and does not reveal solution code
- Rate limiting prevents hint abuse (tested with a script)

### Phase 4: Polish, Scale Readiness & OpenStack Deploy

**Goal:** Production-ready deployment on the private OpenStack cloud.

**Tasks:**
- Replace MinIO with OpenStack Swift in prod environment (env var switch, same S3-compatible API)
- `nginx/prod.conf`: HTTPS termination, WebSocket proxying
- OpenStack Heat template for infrastructure (VM sizing, security groups, load balancer)
- Container pool auto-scaling: dynamically add/remove geo containers based on active sessions
- Document versioning: publish new version; student links stay on the version they started
- Student session persistence: IndexedDB stores exercise progress locally
- Export to PDF: `quarto render --to pdf` with static placeholder for interactive cells
- Smoke test suite that runs against the docker-compose stack as a pre-deploy gate

---

## System-Wide Impact

### Interaction Graph

```
Teacher saves document:
  POST /documentos → stores AST in PostgreSQL
  → Celery task queued (Redis)
    → qmd_serializer.py: AST → .qmd
    → quarto render subprocess (Docker worker, ~10–30s)
    → Upload HTML to MinIO/Swift
    → Update documento.url_artefacto + estado_render = "listo"
    → WebSocket: "Documento listo" → teacher UI updates

Student opens document:
  Nginx serves rendered HTML from MinIO/Swift
  senda-live.js initializes CodeMirror editors

Student clicks "Ejecutar":
  WebSocket → Execution API
  → acquire container from pool (Redis session mapping)
  → docker exec: run code, stream stdout/stderr/plots
  → base64 PNG plots rendered inline

Student code throws error:
  JS intercepts error output
  → POST /api/retroalimentacion/{exercise_id}
  → rate check (Redis)
  → fetch exercise context from PostgreSQL
  → LiteLLM → Ollama (dev) or cloud provider (prod) → structured hint
  → hint rendered inline in Spanish
```

### Error Propagation

- **Quarto render failure:** Celery catches non-zero exit; stores `estado_render: fallido` + stderr; WebSocket notifies teacher. Student link stays on last successful version.
- **Container exec timeout (> 30s):** Execution API kills the `docker exec`, returns `{"tipo": "timeout", "mensaje": "La ejecución superó el tiempo límite de 30 segundos."}`. Container is recycled (not returned to pool).
- **LLM API error:** Returns hardcoded fallback in Spanish: "No pudimos obtener retroalimentación en este momento. Intenta revelar una pista.". Never surfaces raw API errors.
- **Container pool exhausted:** Execution API queues the request (Redis queue); student sees "Preparando entorno de ejecución..." spinner. Max queue wait: 60 seconds, then error.
- **MinIO/Swift upload failure:** Celery retries 3× with exponential backoff. On final failure, `estado_render: fallido`; teacher notified.

### State Lifecycle Risks

- **Orphaned containers:** If the API crashes while a container is in use, the container remains running. A background Celery beat task every 5 minutes checks Redis for session TTL vs. running containers and kills stale ones.
- **Orphaned artifacts:** If MinIO upload succeeds but the DB update fails, the artifact exists without a record. A nightly cleanup task removes MinIO objects with no DB referrer older than 24 hours.
- **Editor AST vs `.qmd` drift:** AST is the source of truth. `.qmd` is always derived. Never manually edit `.qmd` files outside the API.
- **Docker-in-Docker security:** The API container mounts `/var/run/docker.sock`. Scope this carefully — the API should only be able to start/stop pre-defined image names, not arbitrary containers.

### Integration Test Scenarios

1. **Full render cycle:** POST document AST → wait for Celery → GET artifact URL → fetch HTML → assert CodeMirror cell present and `data-senda-exercise` attribute set.
2. **Geo library execution:** Open WebSocket → send `import geopandas as gpd; print(gpd.__version__)` → assert version string in output (no ImportError).
3. **LLM key isolation:** Fetch rendered student HTML → assert no API key patterns (`sk-ant-`, `sk-`, `gsk_`) present anywhere in the response body.
4. **Rate limiting:** POST 11 consecutive feedback requests → assert 12th returns HTTP 429.
5. **Container cleanup:** Create session → force TTL expiry in Redis → trigger cleanup task → assert container no longer running via `docker ps`.

---

## Acceptance Criteria

### Functional

- [ ] Teacher can create, edit, and publish a lesson with: prose text, Python exercise, R exercise, hint, and solution — all in Spanish UI
- [ ] Student document loads in browser with no installation (Chrome, Firefox, Safari)
- [ ] `geopandas` and `sf` execute correctly (not available in browser; runs server-side)
- [ ] LLM hint appears on code error within 5 seconds in Spanish (Ollama locally, cloud provider in production)
- [ ] LLM hint never reveals solution code
- [ ] Teacher receives shareable student link within 60 seconds of saving
- [ ] `docker compose up --build` runs the full stack locally with no additional setup

### Non-Functional

- [ ] LLM feedback rate-limited to 10 requests per exercise per session
- [ ] LLM API key (if configured) never present in student HTML (grep assertion in CI)
- [ ] All user-facing text is in Spanish (no English visible to teachers or students)
- [ ] All API endpoints require authentication
- [ ] Execution containers run with `--read-only` filesystem (write only to `/tmp`)
- [ ] Container exec timeout enforced at 30 seconds

### Quality Gates

- [ ] `pytest` suite covering serializer, feedback proxy, render task, and container pool
- [ ] TypeScript strict mode (`"strict": true` in `tsconfig.json`)
- [ ] `ruff` + `black` for Python; ESLint + Prettier for TypeScript/React
- [ ] docker-compose stack passes smoke tests before any OpenStack deploy

---

## Dependencies & Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Quarto CLI | >= 1.4 | Installed in `Dockerfile.worker` via official script |
| GDAL | >= 3.8 | System dependency in geo execution images |
| Python | 3.12 | Match between API and execution containers |
| `geopandas` | >= 1.0 | Requires GDAL/GEOS/PROJ |
| `sf` (R) | >= 1.0 | Requires GDAL/GEOS/PROJ |
| Node.js | 20 LTS | For Vite + React build |
| Redis | 7+ | Celery broker + session/rate-limit store |
| PostgreSQL | 16+ | Primary database |
| Docker | 24+ | Container pool management |
| MinIO | Latest | Local S3-compatible storage |
| OpenStack Swift | Yoga+ | Production object storage |
| `litellm` | >= 1.40 | LLM provider abstraction; `pip install litellm` |
| Ollama | Latest | Local LLM server; runs in Docker; no API key required |
| Llama 3.2 (3B or 8B) | Latest | Default local model; pulled automatically by Ollama on first start |

---

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Container pool exhaustion under sudden load | Medium | High | Queue with timeout; pre-warm more containers; add observability to pool utilization |
| Docker-in-Docker security vulnerability (API mounts docker.sock) | Medium | High | Allowlist allowed image names in API; consider Rootless Docker or gVisor for exec containers |
| GDAL version mismatch between Python and R containers | Low | Medium | Pin same GDAL version in both Dockerfiles; test both in CI |
| Long Quarto render blocks worker | Low | Medium | Celery task timeout (90s); concurrent workers |
| Student runs infinite loop (resource exhaustion) | Medium | Medium | 30s exec timeout; container CPU/memory limits (`--cpus 0.5 --memory 512m`) |
| OpenStack Swift API differences from MinIO | Low | Medium | Use `boto3` with endpoint override — same code path for both; integration test against both |
| Local Ollama model quality for domain-specific Spanish hints | Medium | Low | Llama 3.2 8B handles geographic/statistical tutoring well; upgrade to 3.2 70B or a cloud provider if quality is insufficient |
| Ollama cold start (model not yet pulled) | Low | Low | `entrypoint` in docker-compose pulls model on first start; subsequent starts use cached volume |
| LLM provider API key misconfiguration in production | Low | Medium | `api/config.py` validates required env vars on startup; fail fast with a clear error |

---

## Future Considerations

- **Collaborative authoring:** Multiple teachers co-editing (Yjs CRDT)
- **LMS export:** SCORM / LTI 1.3 for Moodle/Canvas integration
- **Self-hosted LLM in production:** Ollama on an OpenStack VM for air-gapped or privacy-sensitive deployments — already supported, just point `LLM_API_BASE` at the VM
- **Student progress persistence:** Server-side session storage for students who pause and resume
- **Curriculum organization:** Group documents into courses with ordered lessons and prerequisites
- **Execution scaling:** Move from `docker exec` pool to Kubernetes Jobs for better isolation and scheduling

---

## Sources & References

### Internal

- `README.md` — project name "senda"; description in Spanish confirms bilingual team and Spanish-language product

### External

- **Quarto docs:** https://quarto.org/docs/guide/
- **Quarto extensions:** https://quarto.org/docs/extensions/
- **CodeMirror 6:** https://codemirror.net/ (used in `senda-live.js`)
- **BlockNote docs:** https://www.blocknotejs.org/docs
- **Tiptap (BlockNote foundation):** https://tiptap.dev/docs
- **docker-py SDK:** https://docker-py.readthedocs.io/
- **LiteLLM docs:** https://docs.litellm.ai/
- **Ollama:** https://ollama.com/
- **Ollama Docker image:** https://hub.docker.com/r/ollama/ollama
- **MinIO Python SDK:** https://min.io/docs/minio/linux/developers/python/minio-py.html
- **OpenStack Swift:** https://docs.openstack.org/swift/latest/

### Competitive Landscape

| Platform | Gap vs. Senda |
|---|---|
| Posit Cloud | Server-based but no teacher authoring UI, no LLM, not self-hosted |
| JupyterLite | Browser-only (Pyodide), no geo stack, notebook UX not Quarto |
| Thebe + BinderHub | Jupyter-centric UX, complex ops, not geo-optimized |
| JupyterHub | Great execution backend but forces Jupyter notebook interface |
| quarto-live | WASM only, no geopandas/sf, no LLM, no authoring UI |
