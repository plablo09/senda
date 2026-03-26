from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EjecucionRequest(BaseModel):
    language: Literal["python", "r"]
    code: str = Field(max_length=50000)


class OutputChunkResponse(BaseModel):
    tipo: Literal["stdout", "stderr", "imagen", "error", "fin"]
    contenido: str


class EjecucionResponse(BaseModel):
    chunks: list[OutputChunkResponse]
