from __future__ import annotations

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    codigo_estudiante: str
    error_output: str
    session_id: str | None = None


class FeedbackResponse(BaseModel):
    retroalimentacion: str
    pregunta_guia: str | None = None
    mostrar_pista: bool = True
    silencio: bool = False
    limite: bool = False
