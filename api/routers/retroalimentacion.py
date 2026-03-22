from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.ejecucion_error import EjecucionError
from api.schemas.retroalimentacion import FeedbackRequest, FeedbackResponse
from api.services import feedback_rate_limiter, llm_feedback

router = APIRouter(tags=["retroalimentacion"])

logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]

_LIMITE_MENSAJE = (
    "Has alcanzado el límite de retroalimentación para este ejercicio. "
    "Intenta revelar la pista o consulta con tu profesor."
)


async def _log_error(
    db: AsyncSession,
    documento_id: str,
    ejercicio_id: str,
    session_id: str,
    error_tipo: str,
    error_output: str,
) -> None:
    try:
        entry = EjecucionError(
            documento_id=documento_id,
            ejercicio_id=ejercicio_id,
            session_id=session_id,
            error_tipo=error_tipo,
            error_output=error_output[:5000],  # guard against huge tracebacks
        )
        db.add(entry)
        await db.commit()
    except Exception as exc:
        logger.warning("Error logging ejecucion_error: %s", exc)


@router.post("/{ejercicio_id}", response_model=FeedbackResponse)
async def solicitar_retroalimentacion(
    ejercicio_id: str,
    payload: FeedbackRequest,
    request: Request,
    db: DbDep,
) -> FeedbackResponse:
    # Resolve session identity
    session_id = (
        payload.session_id
        or (request.client.host if request.client else "unknown")
    )

    # Check graduated intervention state
    decision = await feedback_rate_limiter.check_and_update(session_id, ejercicio_id)

    if decision.limite:
        return FeedbackResponse(
            retroalimentacion=_LIMITE_MENSAJE,
            silencio=True,
            limite=True,
            mostrar_pista=False,
        )

    if decision.silencio:
        return FeedbackResponse(
            retroalimentacion="",
            silencio=True,
            mostrar_pista=False,
        )

    # Call LLM (async, non-blocking)
    diagnostico, pregunta_guia, mostrar_pista = await llm_feedback.generar_retroalimentacion(
        codigo_estudiante=payload.codigo_estudiante,
        error_output=payload.error_output,
        ejercicio_id=ejercicio_id,
    )

    # Fire-and-forget error log — DB failure must not affect the response
    asyncio.create_task(
        _log_error(
            db=db,
            documento_id="unknown",  # no documento context at this layer yet
            ejercicio_id=ejercicio_id,
            session_id=session_id,
            error_tipo="stderr",
            error_output=payload.error_output,
        )
    )

    return FeedbackResponse(
        retroalimentacion=diagnostico,
        pregunta_guia=pregunta_guia,
        mostrar_pista=mostrar_pista,
    )
