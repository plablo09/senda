---
status: pending
priority: p2
issue_id: "009"
tags: [code-review, python, schema, correctness]
dependencies: []
---

# estado_render is unvalidated free-text string — add Literal type and DB constraint

## Problem Statement

`estado_render` is a `String(50)` column with no validation at the DB level, ORM level, or schema level. The valid values (`pendiente`, `procesando`, `listo`, `fallido`) exist only in code comments and task logic. A typo silently persists an invalid state; queries filtering by state miss rows; OpenAPI schema gives no hint of valid values to API consumers.

## Findings

- `api/models/documento.py:22` — `estado_render = Column(String(50), default="pendiente")`
- `api/schemas/documento.py:24` — `estado_render: str | None`

## Proposed Solutions

### Option A: Pydantic Literal in schema + SQLAlchemy CHECK constraint (recommended)
```python
# api/schemas/documento.py
from typing import Literal
EstadoRender = Literal["pendiente", "procesando", "listo", "fallido"]

class DocumentoResponse(BaseModel):
    estado_render: EstadoRender | None
```

```python
# api/models/documento.py (via Alembic migration)
from sqlalchemy import CheckConstraint
__table_args__ = (
    CheckConstraint(
        "estado_render IN ('pendiente', 'procesando', 'listo', 'fallido')",
        name="ck_documento_estado_render"
    ),
)
```

- **Pros:** Validated at API, ORM, and DB layers; visible in OpenAPI spec; typos caught at write time
- **Effort:** Small (schema change + migration)
- **Risk:** Low

### Option B: Python Enum
```python
class EstadoRender(str, enum.Enum):
    PENDIENTE = "pendiente"
    ...
```

- **Pros:** Enum provides `.value` iteration and IDE completion
- **Cons:** Slightly more verbose; SQLAlchemy Enum column type needed
- **Effort:** Small-Medium
- **Risk:** Low

## Recommended Action

Option A — Literal is simpler, still discoverable in OpenAPI, requires less migration ceremony.

## Technical Details

- **Affected files:** `api/schemas/documento.py:24`, `api/models/documento.py:22`
- Needs an Alembic migration for the CHECK constraint

## Acceptance Criteria

- [ ] `DocumentoResponse.estado_render` is typed as `Literal["pendiente","procesando","listo","fallido"]`
- [ ] OpenAPI spec shows the valid values for `estado_render`
- [ ] A task writing `doc.estado_render = "typo"` is caught at the DB or schema layer

## Work Log

- 2026-03-20: Identified by architecture-strategist (P2-F), agent-native-reviewer (P2), kieran-python-reviewer (summary)
