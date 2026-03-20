from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentoCreate(BaseModel):
    titulo: str
    ast: dict | None = None


class DocumentoUpdate(BaseModel):
    titulo: str | None = None
    ast: dict | None = None


class DocumentoResponse(BaseModel):
    id: uuid.UUID
    titulo: str
    ast: dict | None
    qmd_source: str | None
    estado_render: str
    url_artefacto: str | None
    error_render: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
