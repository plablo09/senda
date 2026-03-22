---
title: "feat: Block Editor — Teacher Authoring (Phase 2)"
type: feat
status: completed
date: 2026-03-20
origin: docs/plans/2026-03-20-001-feat-senda-education-platform-plan.md
---

# Block Editor — Teacher Authoring (Phase 2)

## Overview

Build the teacher-facing React + BlockNote editor so teachers can author interactive geographic/statistical lessons in Spanish without ever touching `.qmd` syntax. On save, the server serializes the block AST to `.qmd`, renders it via Quarto, and pushes a "Tu documento está listo" notification back to the browser. The teacher receives a shareable student link pointing to the rendered HTML.

This plan covers all work in Phase 2 of the platform plan (see origin: `docs/plans/2026-03-20-001-feat-senda-education-platform-plan.md`, §Phase 2), plus the backend prerequisites that SpecFlow analysis identified as blockers.

---

## Problem Statement

The Phase 1 render pipeline is complete and correct, but there is no teacher-facing interface. Teachers currently have no way to author lessons. Several backend pieces also need to land before the editor can deliver its primary value:

1. `url_artefacto` is stored as an internal MinIO hostname (`http://minio:9000/...`) — browsers can't reach it (tracked in `todos/008`)
2. The QMD serializer has no handlers for `nota`, `ecuacion`, or `cargador_datos` blocks — they are silently dropped
3. There is no WebSocket endpoint for push notifications when rendering completes
4. There is no dataset endpoint for `CargadorDatosNode`

### Clarifications incorporated (2026-03-20)

**1. Equation editor:** Lessons on geographic and statistical analysis routinely contain mathematical notation (regression formulas, coordinate projections, summary statistics). The editor must support LaTeX equations — both inline (`$...$`) and block-level (`$$...$$`). Because many teachers are domain experts but not LaTeX-fluent, the `EcuacionNode` UI provides a symbol toolbar (common Greek letters, operators, integrals, summation) so teachers can build equations without memorizing syntax. A live KaTeX preview renders the equation as the teacher types.

**2. Geographic file formats:** The platform's primary use case is geographic and statistical analysis. Supported dataset formats are: CSV (start here — simplest), GeoJSON, zipped shapefiles (.zip containing .shp/.dbf/.prj), and GeoPackage (.gpkg). The upload endpoint and storage layer are designed generically from day one so adding new formats is a one-line MIME-type addition, not a refactor.

**3. Dataset reuse and visibility:** Datasets are independent resources, not document-scoped. A teacher uploads a dataset once and can reference it in any of their documents. An optional `es_publico` flag lets teachers share datasets with all other teachers (deferred to a later sprint, but the data model must support it now). The `CargadorDatosNode` UI lets teachers either upload a new file or pick from their existing dataset library.

---

## Decisions Made (Resolving SpecFlow Open Questions)

These decisions are made upfront to avoid implementation-time ambiguity.

| Question | Decision |
|---|---|
| `pista` / `solución` as standalone blocks? | No — they remain fields (`hints[]`, `solutionCode`) inside `EjercicioNode`. No standalone serialization path. |
| `nota` QMD output | `::: {.callout-<nivel>}` where `nivel` ∈ `note \| tip \| warning \| important` |
| `cargador_datos` load time | Student runtime (the code block runs `pd.read_csv(url)` etc. when the student clicks Ejecutar). No render-time MinIO access needed from worker. |
| Render notification mechanism | New WebSocket endpoint `/ws/documentos/{id}/estado` backed by Redis pub/sub. Celery publishes on completion; FastAPI subscribes and forwards to the connected browser. |
| Shareable student link URL | nginx-proxied URL via a new `STORAGE_PUBLIC_ENDPOINT` setting (resolves todo 008). Pattern: `http://localhost:9000/senda-documentos/{id}/index.html` in dev, overridable for prod. |
| Dataset scope | **Independent from documents.** Scoped to a teacher (once auth lands). Stored at `datasets/{uuid}/{filename}` in MinIO. Deleting a document does NOT delete datasets. |
| Dataset reuse | A dataset can be referenced in multiple documents via its ID. `CargadorDatosNode` shows "Subir nuevo" + "Seleccionar existente" (from teacher's dataset library). |
| Dataset visibility | `es_publico: bool` field in the `Dataset` model. Default `false`. Cross-teacher sharing (showing public datasets from other teachers) is **deferred** to a later sprint but the column must exist now. |
| Dataset formats — MVP | CSV only for Phase 2. |
| Dataset formats — designed for | GeoJSON, zipped shapefile (.zip), GeoPackage (.gpkg) — accepted MIME types list is extensible; adding a new format requires no schema changes. |
| Dataset size limit | 50 MB. MVP accepted type: `text/csv`. Architecture accepts: `application/geo+json`, `application/zip`, `application/geopackage+sqlite3`. |
| Equation support | `EcuacionNode` with KaTeX live preview + symbol toolbar for LaTeX-unfamiliar teachers. Inline (`$...$`) and block (`$$...$$`) modes. Serializes to native Quarto LaTeX math syntax. |
| Auto-save | No. Explicit "Guardar" only. Unsaved-changes indicator + `beforeunload` warning. |
| Save error recovery | Toast error + editor stays dirty. No `localStorage` backup in Phase 2. |
| Render failure display | Dashboard badge "Fallido" (red). Preview panel: "El documento no pudo procesarse" + collapsible "Ver detalles" with raw `error_render`. |
| WebSocket fallback | If WS disconnects, poll `GET /api/documentos/{id}` every 3 seconds until `estado_render` is terminal. |
| Shareable link UX | Read-only text input + "Copiar enlace" button (Clipboard API). |
| Stale "procesando" recovery | Documents stuck in "procesando" for > 10 minutes are reset to "fallido" with `error_render = "Tiempo de procesamiento agotado"`. Implemented as a Celery beat task. |
| Document delete | Shows Spanish confirmation dialog. Deletes DB row + MinIO artifacts (rendered HTML + datasets). |
| Dashboard delete action | Yes, with confirmation. |
| Concurrent edits | Last write wins; no optimistic locking in Phase 2 (no auth yet). Explicitly out of scope. |
| iframe sandbox | `sandbox="allow-scripts allow-same-origin allow-forms"` |

---

## Technical Approach

### Frontend Stack

- **React 19 + Vite 6 + TypeScript** (strict mode)
- **BlockNote 0.47** with `@blocknote/core`, `@blocknote/react`, `@blocknote/mantine`
- **React Router v7** for `Inicio` / `Editor` / `Vista` pages
- **Vitest** for unit tests (`serializer.ts` primarily)
- **ESLint + Prettier**
- All UI strings in `frontend/src/i18n/es.json`; accessed via a thin `t()` helper

### Vite Docker Setup

Dev: Vite dev server on port 5173, volume-mounted source, hot-reload.
Prod: multi-stage build → static `dist/` → nginx:alpine serves on port 80.

```dockerfile
# docker/Dockerfile.frontend (new)
FROM node:22-alpine AS dev
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.27-alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

`vite.config.ts` critical settings:
```typescript
server: {
  host: "0.0.0.0",   // mandatory inside Docker
  port: 5173,
  strictPort: true,
  allowedHosts: ["frontend", ".localhost"],
}
```
No proxy block needed in the Vite config — nginx handles `/api/` and `/ws/` routing in both dev and prod.

### Backend Additions

1. **`api/services/storage.py`** — add `STORAGE_PUBLIC_ENDPOINT` (resolves todo 008); add `delete_document_artifacts()` helper
2. **`api/services/qmd_serializer.py`** — add `nota`, `ecuacion`, and `cargador_datos` block serializers + tests (TDD)
3. **`api/routers/datasets.py`** — `POST /datasets` (upload), `GET /datasets` (list teacher's + public), `DELETE /datasets/{id}`
4. **`api/models/dataset.py`** — new `Dataset` model (id, filename, url, mimetype, es_publico, created_at) — no `documento_id` FK; documents reference datasets by URL embedded in block props
5. **`api/routers/documentos.py`** — extend DELETE to clean up MinIO document artifacts only (datasets are independent)
6. **`api/ws/render_status.py`** — new `/ws/documentos/{id}/estado` endpoint with Redis pub/sub
7. **`api/tasks/render_task.py`** — publish to Redis on completion; add stale-procesando beat task
8. **`api/celery_app.py`** — add stale procesando beat schedule
9. **`nginx/dev.conf`** — update `location /` to forward to Vite on port 5173 in dev; add MinIO proxy at `/artefactos/`

### BlockNote Custom Nodes

All custom nodes use `createReactBlockSpec` with `content: "none"` (structured props, not inline rich text).

```typescript
// EjercicioNode — exercise block
{
  type: "ejercicio",
  propSchema: {
    language: { default: "python", values: ["python", "r"] },
    exerciseId: { default: "" },
    caption: { default: "" },
    starterCode: { default: "" },
    solutionCode: { default: "" },
    hints: { default: "[]" },  // JSON-encoded string[] — BlockNote props are strings
  },
  content: "none"
}

// NotaNode — callout block
{
  type: "nota",
  propSchema: {
    nivel: { default: "note", values: ["note", "tip", "warning", "important"] },
    titulo: { default: "" },
    contenido: { default: "" },
  },
  content: "none"
}

// CargadorDatosNode — dataset loader block
{
  type: "cargadorDatos",
  propSchema: {
    datasetId: { default: "" },   // Dataset.id (for display / future delete protection)
    filename: { default: "" },
    url: { default: "" },         // MinIO public URL embedded at save time
    mimetype: { default: "text/csv" },
    language: { default: "python", values: ["python", "r"] },
    variableName: { default: "datos" },
  },
  content: "none"
}

// EcuacionNode — LaTeX math block
{
  type: "ecuacion",
  propSchema: {
    latex: { default: "" },       // raw LaTeX source, e.g. "\\bar{x} = \\frac{1}{n}\\sum x_i"
    modo: { default: "bloque", values: ["bloque", "linea"] },
  },
  content: "none"
}
```

### `serializer.ts` Contract

The `serializer.ts` function maps BlockNote `Block[]` to the `ast` payload the backend expects:

```typescript
// Input: editor.document (BlockNote Block[])
// Output: AST payload for POST/PUT /api/documentos
{
  execution_url: string,   // ws://host/ws/ejecutar
  blocks: [
    // text block (standard BlockNote paragraph/heading → joined as markdown)
    { type: "text", text: "## Heading\n\nParagraph..." },

    // exercise block
    {
      type: "exercise",
      attrs: {
        language: "python",
        exerciseId: "ex_abc",
        caption: "Título del ejercicio",
        starterCode: "...",
        solutionCode: "...",
        hints: ["hint 1", "hint 2"]
      }
    },

    // nota block
    {
      type: "nota",
      attrs: {
        nivel: "tip",
        titulo: "Título opcional",
        contenido: "Texto de la nota"
      }
    },

    // ecuacion block
    {
      type: "ecuacion",
      attrs: {
        latex: "\\bar{x} = \\frac{1}{n}\\sum_{i=1}^{n} x_i",
        modo: "bloque"   // or "linea"
      }
    },

    // cargadorDatos block
    {
      type: "cargadorDatos",
      attrs: {
        url: "http://localhost:9000/senda-documentos/datasets/uuid/datos.csv",
        filename: "datos.csv",
        mimetype: "text/csv",
        language: "python",
        variableName: "datos"
      }
    }
  ]
}
```

### Render Notification Flow

```
Teacher browser
  ├── POST /api/documentos  →  DB insert, render enqueued
  └── WS /ws/documentos/{id}/estado
        │  subscribe to Redis channel render:{id}
        ▼
FastAPI WS endpoint  ←──  Redis pub/sub  ←──  Celery task publishes
                                                  { status: "listo"|"fallido",
                                                    url_artefacto: "...",
                                                    error_render: "..." }
```

The WebSocket uses a per-document channel key `render:{documento_id}`. The Celery task publishes immediately after committing the final estado to the DB.

---

## Implementation Units

### Unit 1 — Backend: Public artifact URL (resolves todo 008)

**Goal:** `url_artefacto` must be browser-reachable. Add `STORAGE_PUBLIC_ENDPOINT` setting and update `upload_html()` to use it.

**Files:**
- `api/config.py` — add `storage_public_endpoint: str = "http://localhost:9000"`
- `api/services/storage.py` — use `settings.storage_public_endpoint` in `upload_html()` return value
- `.env.example` — document `STORAGE_PUBLIC_ENDPOINT`
- `nginx/dev.conf` — add MinIO proxy at `location /artefactos/` → `http://minio:9000/senda-documentos/`

**Test:** `GET url_artefacto` from a browser returns the rendered HTML (not connection refused).

**Execution note:** Fix first — all other units depend on a working shareable link.

---

### Unit 2 — Backend: QMD serializer extensions (TDD)

**Goal:** `nota`, `ecuacion`, and `cargadorDatos` blocks serialize to correct QMD. All new block types have test coverage.

**Files:**
- `api/services/qmd_serializer.py` — add `_serialize_nota()`, `_serialize_ecuacion()`, `_serialize_cargador_datos()` handlers
- `api/tests/unit/test_qmd_serializer.py` — new test cases for all three block types

**`nota` → QMD:**
```
::: {.callout-tip}
## Título opcional
Texto de la nota
:::
```

**`ecuacion` → QMD:**
```
# modo: "bloque"
$$
\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i
$$

# modo: "linea" — wrapped inline in surrounding text paragraph
$\bar{x} = \frac{1}{n}\sum x_i$
```
Quarto renders both natively via MathJax/KaTeX — no extra extensions needed.

**`cargadorDatos` → QMD:**
```python
# Python (text/csv):
datos = pd.read_csv("http://storage/datasets/uuid/datos.csv")
# Python (GeoJSON):
datos = gpd.read_file("http://storage/datasets/uuid/datos.geojson")
# R (CSV):
datos <- read.csv("http://storage/datasets/uuid/datos.csv")
# R (GeoJSON):
datos <- sf::st_read("http://storage/datasets/uuid/datos.geojson")
```
The serializer picks the correct read function based on `mimetype` and `language`. The code block is tagged `#| exercise: false` so senda-live.js does not make it interactive.

**Execution note:** TDD — write failing tests first, then implement.

**Patterns to follow:** `api/services/qmd_serializer.py:53-59` (existing block dispatch), `api/tests/unit/test_qmd_serializer.py` (existing test structure).

---

### Unit 3 — Backend: Dataset endpoint

**Goal:** Datasets are independent resources. Teachers upload once, reference in many documents. Architecture supports geographic formats from day one; MVP ships CSV only.

**Files:**
- `api/models/dataset.py` — new SQLAlchemy model
- `api/schemas/dataset.py` — `DatasetResponse`, `DatasetListResponse`
- `api/routers/datasets.py` — `POST /datasets`, `GET /datasets`, `DELETE /datasets/{id}`
- `api/main.py` — register datasets router at `/datasets`

**New model:**
```python
# api/models/dataset.py
class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    filename = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)       # public MinIO URL
    mimetype = Column(String(100), nullable=False)
    es_publico = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC))
    # teacher_id will be added when auth lands — intentionally omitted now
```

**Endpoints:**
```python
# Upload new dataset (multipart/form-data)
POST /datasets
  → validate mimetype ∈ ACCEPTED_MIMETYPES, size ≤ 50MB
  → upload to MinIO at datasets/{uuid}/{filename}
  → insert Dataset row
  → return DatasetResponse {id, filename, url, mimetype, es_publico, created_at}

# List available datasets (own + public, once auth lands; all for now)
GET /datasets
  → return list[DatasetResponse] ordered by created_at DESC

# Delete dataset
DELETE /datasets/{id}
  → delete MinIO object
  → delete DB row
  → 204
```

**Accepted MIME types (extensible list in `config.py`):**
```python
DATASET_ACCEPTED_MIMETYPES = {
    "text/csv",                          # CSV — Phase 2 MVP
    "application/geo+json",              # GeoJSON — Phase 2 ready
    "application/zip",                   # Zipped shapefile — Phase 2 ready
    "application/geopackage+sqlite3",    # GeoPackage — Phase 2 ready
}
```

**Note:** `DELETE /documentos/{id}` does NOT cascade to datasets. Datasets are independent.

---

### Unit 4 — Backend: Render notification WebSocket

**Goal:** Browser receives a push when `render_documento` completes or fails.

**Files:**
- `api/ws/__init__.py`
- `api/ws/render_status.py` — `/ws/documentos/{id}/estado` endpoint with `redis.asyncio` pub/sub
- `api/tasks/render_task.py` — publish `{status, url_artefacto, error_render}` to `render:{id}` after final DB commit
- `api/celery_app.py` — add stale-procesando beat task (reset documents > 10 min in "procesando" to "fallido")
- `api/main.py` — register WS router

**WebSocket message schema:**
```json
{ "status": "listo", "url_artefacto": "http://...", "error_render": null }
{ "status": "fallido", "url_artefacto": null, "error_render": "Quarto render failed: ..." }
```

**Redis channel:** `render:{documento_id}`

**Celery publish (in `render_task.py`, after each terminal commit):**
```python
import redis as redis_sync
_r = redis_sync.from_url(settings.redis_url)
_r.publish(f"render:{documento_id}", json.dumps({
    "status": doc.estado_render,
    "url_artefacto": doc.url_artefacto,
    "error_render": doc.error_render,
}))
```

**Stale beat task** (new, in `render_task.py`):
```python
@celery_app.task
def reset_stale_procesando():
    """Reset documents stuck in 'procesando' for > 10 minutes."""
```
Add to beat_schedule with `schedule=300.0` (run every 5 min).

---

### Unit 5 — Frontend: Scaffold

**Goal:** `frontend/` directory exists, Vite + React + TypeScript builds and hot-reloads through nginx.

**Files:**
- `frontend/` — created via `npm create vite@latest frontend -- --template react-ts`
- `frontend/package.json` — add `@blocknote/core`, `@blocknote/react`, `@blocknote/mantine`, `react-router-dom`, `@mantine/core`, `@mantine/hooks`
- `frontend/vite.config.ts` — `host: "0.0.0.0"`, port 5173, `allowedHosts`
- `frontend/tsconfig.json` — `"strict": true`
- `frontend/.eslintrc.cjs` — ESLint + Prettier config
- `docker/Dockerfile.frontend` — replace stub with multi-stage build (dev target for docker-compose)
- `docker-compose.yml` — frontend service: `target: dev`, volume mount `./frontend:/app`, `node_modules` volume

**Nginx dev.conf update:**
```nginx
location / {
    set $frontend_upstream http://frontend:5173;
    proxy_pass $frontend_upstream;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";  # needed for Vite HMR websocket
    proxy_set_header Host $host;
}
```
The HMR WebSocket that Vite injects into the page (`/@vite/client`) uses the same upgrade mechanism as a regular WebSocket — the nginx `location /` block must support it.

**Verification:** `docker compose up` → `http://localhost:8080` shows the Vite default React page.

---

### Unit 6 — Frontend: API client

**Goal:** Typed TypeScript client for all backend endpoints used by the editor.

**Files:**
- `frontend/src/api/client.ts` — fetch wrapper with error handling
- `frontend/src/api/documentos.ts` — `listar()`, `crear()`, `obtener()`, `actualizar()`, `eliminar()`
- `frontend/src/api/datasets.ts` — `subir(documentoId, file)`
- `frontend/src/api/types.ts` — `Documento`, `Dataset`, `EstadoRender` TypeScript types

**Key type:**
```typescript
export type EstadoRender = "pendiente" | "procesando" | "listo" | "fallido";

export interface Documento {
  id: string;
  titulo: string;
  ast: DocumentoAST | null;
  qmd_source: string | null;
  estado_render: EstadoRender;
  url_artefacto: string | null;
  error_render: string | null;
  created_at: string;
  updated_at: string;
}
```

---

### Unit 7 — Frontend: `serializer.ts` (TDD)

**Goal:** `blockNoteToAST(blocks, executionUrl)` produces the exact payload `qmd_serializer.py` consumes.

**Files:**
- `frontend/src/editor/serializer.ts`
- `frontend/src/editor/__tests__/serializer.test.ts` — vitest tests mirroring the Python serializer tests

**Key cases to test:**
- Standard BlockNote paragraph → `{type: "text", text: "..."}`
- Heading blocks → prefixed with `## ` / `### ` etc.
- `ejercicio` block → `{type: "exercise", attrs: {..., hints: string[]}}`
- `nota` block → `{type: "nota", attrs: {...}}`
- `cargadorDatos` block → `{type: "cargadorDatos", attrs: {...}}`
- Empty document → `{execution_url: ..., blocks: []}`
- `exerciseId` auto-generated if empty (UUID v4)

**Execution note:** TDD — write tests first against the schema defined in this plan, then implement.

**Patterns to follow:** `api/tests/unit/test_qmd_serializer.py` for test structure philosophy; mirror the Python tests in TypeScript where possible.

---

### Unit 8 — Frontend: Custom block nodes

**Goal:** BlockNote schema extended with `EjercicioNode`, `NotaNode`, `CargadorDatosNode`. All render correctly in the editor. All UI text in Spanish.

**Files:**
- `frontend/src/editor/nodes/EjercicioNode.tsx`
- `frontend/src/editor/nodes/NotaNode.tsx`
- `frontend/src/editor/nodes/CargadorDatosNode.tsx`
- `frontend/src/editor/schema.ts` — `BlockNoteSchema.create({ blockSpecs: {...defaultBlockSpecs, ejercicio, nota, cargadorDatos} })`
- `frontend/src/i18n/es.json` — all Spanish strings for block labels, placeholders, buttons

**EjercicioNode UI:**
- Language selector: `<select>` with "Python" / "R"
- Caption text input: "Título del ejercicio"
- Starter code textarea: "Código inicial"
- Solution code textarea: "Solución" (collapsed by default, toggle button "Mostrar solución")
- Hints textarea list: "Pistas" (add/remove hint buttons)

**NotaNode UI:**
- Level selector: "Nota" / "Consejo" / "Advertencia" / "Importante"
- Optional title input
- Content textarea

**CargadorDatosNode UI:**
- Two-mode selector: "Subir nuevo dataset" / "Seleccionar existente"
  - **Subir nuevo:** file input (CSV only for MVP, with help text listing future supported formats); on upload calls `POST /api/datasets`; updates block props with returned `{id, url, filename, mimetype}`
  - **Seleccionar existente:** dropdown populated from `GET /api/datasets`; on select updates block props
- Variable name input: "Nombre de variable" (default: "datos")
- Language selector: Python / R (determines which read function is emitted in QMD)
- Shows current filename + "Cambiar" link once a dataset is selected

**EcuacionNode UI:**
- LaTeX text input: "Fórmula LaTeX"
- Mode toggle: "Bloque" (centered, display) / "En línea" (inline within text)
- Live KaTeX preview rendered below the input as the teacher types
- Symbol toolbar with common mathematical symbols (no LaTeX knowledge required for basics):
  - Greek: α β γ δ μ σ π ∑ ∏
  - Operators: ± √ ∞ ∂ ∫ ≤ ≥ ≠ ≈
  - Structure buttons: Fracción (inserts `\frac{}{}`), Índice (`_{}`), Exponente (`^{}`), Raíz (`\sqrt{}`)
- Install: `npm install katex` + `@types/katex` for the preview renderer

**Vite ESM gotcha:** Use `import type` for all BlockNote type-only imports.

---

### Unit 9 — Frontend: Editor page

**Goal:** Full authoring experience at `/editor/:id?` — create and edit documents.

**Files:**
- `frontend/src/pages/Editor.tsx`
- `frontend/src/editor/SendaEditor.tsx` — BlockNote `<BlockNoteView>` wrapper with toolbar

**Behaviour:**
- On mount with no `id`: blank editor, title input focused
- On mount with `id`: fetch document, load `ast` as `initialContent` into BlockNote
- "Guardar" button:
  - Calls `blockNoteToAST(editor.document, executionUrl)` to get AST payload
  - `crear()` if no id, `actualizar()` if id exists
  - On success: navigate to `/editor/{id}`, connect to `/ws/documentos/{id}/estado`
  - On error: show Spanish toast "No se pudo guardar el documento. Intenta de nuevo."
- Render status bar (below title): shows `estado_render` badge
  - `pendiente` → grey "Pendiente"
  - `procesando` → spinner "Procesando..."
  - `listo` → green "Listo" + "Copiar enlace" button + URL input
  - `fallido` → red "Fallido" + "Ver detalles" collapsible
- Preview panel (right side, collapsible):
  - "Actualizar vista previa" button → sets iframe `src` to `url_artefacto`
  - iframe with `sandbox="allow-scripts allow-same-origin allow-forms"`
- Unsaved changes indicator (dot on "Guardar" button when editor has changes since last save)
- `beforeunload` listener fires warning if dirty

**WebSocket status subscription** (extracted to hook `useRenderStatus(documentoId)`):
- Connects on save (after we have an ID)
- On message: update `estadoRender` state → triggers UI update
- On disconnect: start polling `GET /api/documentos/{id}` every 3 seconds
- On terminal status received: stop polling/subscription

---

### Unit 10 — Frontend: Dashboard (Inicio)

**Goal:** Teacher landing page at `/` showing all lessons.

**Files:**
- `frontend/src/pages/Inicio.tsx`
- `frontend/src/components/LeccionCard.tsx`
- `frontend/src/components/ConfirmDialog.tsx`

**Behaviour:**
- On mount: `GET /api/documentos` → list of lessons ordered by `created_at DESC`
- Each card shows: `titulo`, `estado_render` badge, `created_at` date, "Editar" button, "Eliminar" button
- "Nueva lección" button → navigate to `/editor`
- "Eliminar": show `ConfirmDialog` ("¿Eliminar esta lección? Esta acción no se puede deshacer.") → on confirm: `eliminar(id)` → remove from list
- Estado badges: same colour coding as Editor page
- Empty state: "Aún no has creado ninguna lección. ¡Crea la primera!"

---

## System-Wide Impact

### Interaction Graph (Phase 2 additions)

```
Teacher clicks "Guardar":
  POST/PUT /api/documentos
    → DB insert/update (titulo, ast, estado_render="pendiente")
    → render_documento.delay(documento_id)
      → Worker: estado_render="procesando" + commit
      → Worker: qmd_serializer.serialize_document(ast)
      → Worker: quarto render subprocess
      → Worker: upload_html() → MinIO at storage_public_endpoint path
      → Worker: estado_render="listo" + url_artefacto + commit
      → Worker: redis.publish("render:{id}", {status, url_artefacto})
        → FastAPI WS /ws/documentos/{id}/estado sends JSON to browser
          → React: toast "Tu documento está listo" + link appears

Teacher adds CargadorDatosNode file:
  POST /api/datasets/{documento_id} (multipart)
    → MinIO upload at datasets/{doc_id}/{uuid}_{filename}
    → Dataset DB row insert
    → Returns {id, url, filename}
      → BlockNote block props updated with url/filename
        → Serialized as cargadorDatos block in next Guardar
```

### Error Propagation

- `POST /api/datasets` 413 (too large) or 422 (bad MIME) → frontend shows Spanish toast; block stays in "sin archivo" state
- `render_documento` `RenderError` → `estado_render="fallido"`, `error_render=str(exc)` committed; Redis publish with status "fallido"; frontend shows red badge + "Ver detalles"
- `render_documento` `Exception` (transient, retries remaining) → `estado_render="pendiente"` committed; browser stays in "procesando" spinner; Redis publish only on final terminal state
- Celery pub: Redis publish happens after all DB commits, so the browser never receives "listo" before the row is actually committed
- WebSocket disconnect during render → fallback poll picks up terminal state on next 3-second tick

### State Lifecycle Risks

- **Stale "procesando":** If the worker dies after committing "procesando" but before the final commit, the document is stuck. Mitigated by the new `reset_stale_procesando` beat task (runs every 5 min, resets documents > 10 min in "procesando").
- **Dataset orphan on document delete:** The `CASCADE` on `datasets.documento_id` handles the DB row. The `DELETE /documentos/{id}` endpoint must also delete MinIO objects. If the MinIO delete fails after the DB row is deleted, the MinIO object is orphaned but harmless.
- **Double-render on retry:** If a teacher saves the same document quickly twice, two render tasks are enqueued. The second task overwrites the first's output. Last write wins — acceptable for Phase 2.

### API Surface Parity

New endpoints:
- `POST /datasets/{documento_id}` — dataset upload
- `WS /ws/documentos/{id}/estado` — render status push
- `DELETE /documentos/{id}` — extended to clean MinIO artifacts + datasets (existing endpoint, new behaviour)

---

## Acceptance Criteria

### Functional

- [ ] `docker compose up --build` starts the full stack including a hot-reloading Vite dev server at `http://localhost:8080`
- [ ] Teacher can create a lesson with title + at least one EjercicioNode (Python or R) and click "Guardar"
- [ ] After saving, `estado_render` transitions from "pendiente" → "procesando" → "listo"/"fallido" visible in the UI
- [ ] "Tu documento está listo" toast appears when render completes (WebSocket push)
- [ ] If WebSocket disconnects, status polling continues until terminal state
- [ ] `url_artefacto` in `DocumentoResponse` is a browser-reachable URL (not `http://minio:9000`)
- [ ] "Copiar enlace" copies `url_artefacto` to clipboard; student can open the rendered document in a new tab
- [ ] Teacher can add a NotaNode (with nivel = tip/note/warning/important); rendered QMD contains the correct callout syntax
- [ ] Teacher can add an EcuacionNode; live KaTeX preview renders correctly in the editor; rendered QMD contains `$$...$$` or `$...$` syntax
- [ ] Symbol toolbar inserts correct LaTeX snippets into the equation input
- [ ] Teacher can upload a CSV file via CargadorDatosNode ("Subir nuevo dataset"); rendered document contains a code cell with the correct `pd.read_csv()` / `read.csv()` call
- [ ] Teacher can reuse a previously uploaded dataset via "Seleccionar existente" dropdown
- [ ] `GET /api/datasets` returns the teacher's dataset library
- [ ] Dataset is not deleted when the associated document is deleted
- [ ] `Dataset` model has `es_publico` column (default false); field appears in `DatasetResponse`
- [ ] Uploading a file with an unsupported MIME type returns HTTP 422 with a Spanish error message
- [ ] Uploading a file over 50 MB returns HTTP 413 with a Spanish error message
- [ ] Teacher can load an existing lesson from the dashboard and edit it
- [ ] Teacher can delete a lesson with confirmation; MinIO artifacts are removed
- [ ] If "Guardar" fails (network error), a Spanish error toast is shown and the editor stays dirty
- [ ] If `estado_render="fallido"`, the error is accessible via "Ver detalles"
- [ ] All UI text is in Spanish (no English visible to teachers)
- [ ] `blockNoteToAST()` unit tests pass covering all block types
- [ ] QMD serializer unit tests pass for `nota` and `cargadorDatos` block types

### Non-Functional

- [ ] TypeScript strict mode — no `any` types in frontend source
- [ ] ESLint passes with no errors
- [ ] Vitest `serializer.test.ts` test suite passes
- [ ] `docker compose up --build` requires no manual steps beyond `.env` configuration

### Out of Scope for Phase 2

- Authentication / teacher login
- Real-time collaborative editing (last write wins)
- Rename lesson from dashboard
- Export to PDF
- Document versioning
- `localStorage` auto-backup of unsaved content

---

## Dependencies & Risks

| Dependency | Status | Risk |
|---|---|---|
| Unit 1 (public URL) must land before Units 5-10 can deliver value | Unit 1 is small | Low |
| BlockNote v0.47 custom block API | Stable — no breaking changes in minor releases | Low |
| Redis pub/sub for WS notifications | Redis already in stack (Celery broker) | Low |
| Quarto render working | Verified in Phase 1 smoke test | Low |
| MinIO accessible from browser (Unit 1) | Requires nginx proxy rule addition | Low |
| Vite HMR through nginx | Requires nginx upgrade headers for `location /` | Medium — easy to miss |
| `reset_stale_procesando` beat task | Needs Celery beat running; not currently running in docker-compose | Medium — add `celery beat` or add `-B` flag to worker CMD |

---

## Implementation Order

```
Unit 1 (public URL fix)          ← prerequisite for everything
Unit 2 (serializer extensions)   ← TDD, backend only, independent
Unit 3 (datasets endpoint)       ← backend only, independent
Unit 4 (render WS notification)  ← backend only, independent
Unit 5 (frontend scaffold)       ← unblocks Units 6-10
Unit 6 (API client)              ← depends on Unit 5
Unit 7 (serializer.ts)           ← TDD, depends on Unit 5; parallel with Unit 6
Unit 8 (custom block nodes)      ← depends on Units 5, 6, 3
Unit 9 (Editor page)             ← depends on Units 6, 7, 8, 4
Unit 10 (Dashboard)              ← depends on Units 6, 9
```

Units 2, 3, 4 can run in parallel with Unit 5 (backend vs frontend work).
Units 6 and 7 can run in parallel after Unit 5.
Unit 8 can start after Units 5 and 6. `EcuacionNode` requires `npm install katex`.
Units 9 and 10 are the integration layer — implement last.

**Key additions from clarifications:**
- Unit 2 now includes `ecuacion` serializer (block → `$$...$$` or `$...$`)
- Unit 3 dataset model is teacher-scoped (no `documento_id` FK) + `es_publico` column + geographic MIME types in config
- Unit 8 now includes `EcuacionNode` (KaTeX preview + symbol toolbar)
- Unit 8 `CargadorDatosNode` now has "upload new" + "select existing" dual-mode UI
- Unit 6 `api/datasets.ts` adds `listar()` for dataset library fetch

---

## Sources & References

### Origin

- **Origin document:** [docs/plans/2026-03-20-001-feat-senda-education-platform-plan.md](docs/plans/2026-03-20-001-feat-senda-education-platform-plan.md) — Phase 2 section (lines 798–816). Key decisions carried forward: BlockNote + React + Vite + TypeScript; all UI in Spanish; QMD serializer is the single source of truth; teacher/student role split.

### Internal References

- Existing serializer: `api/services/qmd_serializer.py:53-59` (block dispatch pattern)
- Serializer tests: `api/tests/unit/test_qmd_serializer.py` (TDD template)
- Execution WS: `api/routers/ejecutar.py` (WebSocket pattern to follow)
- Storage service: `api/services/storage.py:34` (URL construction to fix in Unit 1)
- Docker nginx config: `nginx/dev.conf` (runtime DNS pattern — must preserve `set $var` for new upstreams)
- Todo 008: `todos/008-pending-p2-storage-url-internal-hostname.md` (resolved by Unit 1)
- Infrastructure learnings: `docs/solutions/runtime-errors/docker-compose-stack-startup-failures.md`

### External References

- BlockNote docs: https://www.blocknotejs.org/docs/custom-schemas/custom-blocks
- BlockNote `createReactBlockSpec`: v0.47 — import types with `import type { ... }` to avoid Vite ESM issues
- Vite Docker: `server.host: "0.0.0.0"` is mandatory; `allowedHosts` must include Docker service name
- Redis pub/sub (async): `redis.asyncio` — do NOT use archived `broadcaster` library (archived Aug 2025)
- FastAPI WebSocket: `asyncio.gather(forward_redis(), drain_client())` pattern for bidirectional keep-alive
