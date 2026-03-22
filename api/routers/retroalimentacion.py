from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from api.database import AsyncSessionLocal
from api.models.ejecucion_error import EjecucionError
from api.schemas.retroalimentacion import FeedbackRequest, FeedbackResponse
from api.services import feedback_rate_limiter, llm_feedback

router = APIRouter(tags=["retroalimentacion"])

logger = logging.getLogger(__name__)

_LIMITE_MENSAJE = (
    "Has alcanzado el límite de retroalimentación para este ejercicio. "
    "Intenta revelar la pista o consulta con tu profesor."
)


async def _log_error(
    documento_id: str | None,
    ejercicio_id: str,
    session_id: str,
    error_tipo: str,
    error_output: str,
) -> None:
    """Fire-and-forget DB write; opens its own session so it survives request teardown."""
    try:
        async with AsyncSessionLocal() as db:
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
) -> FeedbackResponse:
    session_id = payload.session_id  # required; always provided by browser

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
    diagnostico, pregunta_guia, mostrar_pista, referencia_concepto = (
        await llm_feedback.generar_retroalimentacion(
            codigo_estudiante=payload.codigo_estudiante,
            error_output=payload.error_output,
            ejercicio_id=ejercicio_id,
        )
    )

    # Fire-and-forget error log — DB failure must not affect the response
    asyncio.create_task(
        _log_error(
            documento_id=None,
            ejercicio_id=ejercicio_id,
            session_id=session_id,
            error_tipo="stderr",
            error_output=payload.error_output,
        )
    )

    return FeedbackResponse(
        retroalimentacion=diagnostico,
        pregunta_guia=pregunta_guia,
        referencia_concepto=referencia_concepto,
        mostrar_pista=mostrar_pista,
    )
