from __future__ import annotations

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, model_validator

EstadoRender = Literal["pendiente", "procesando", "listo", "fallido"]


class DocumentoCreate(BaseModel):
    titulo: str
    ast: dict | None = None

    @model_validator(mode="after")
    def ast_schema_version(self) -> "DocumentoCreate":
        if self.ast is not None and "schemaVersion" not in self.ast:
            raise ValueError("ast debe incluir el campo 'schemaVersion'")
        return self


class DocumentoUpdate(BaseModel):
    titulo: str | None = None
    ast: dict | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DocumentoUpdate":
        if self.titulo is None and self.ast is None:
            raise ValueError("Se requiere al menos un campo: titulo o ast")
        return self


class DocumentoResponse(BaseModel):
    id: uuid.UUID
    titulo: str
    ast: dict | None
    qmd_source: str | None
    estado_render: EstadoRender
    url_artefacto: str | None
    error_render: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
