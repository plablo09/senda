from __future__ import annotations

import asyncio
import json
import logging

import litellm

from api.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_MESSAGE = (
    "No pudimos obtener retroalimentación en este momento. Intenta revelar una pista."
)

_LLM_TIMEOUT_SECONDS = 15.0
_LLM_SEMAPHORE = asyncio.Semaphore(6)  # cap concurrent LLM calls

_SYSTEM_PROMPT = """\
Eres un tutor de análisis estadístico y geográfico. Tu rol es guiar al estudiante
mediante preguntas socráticas cuando su código produce un error. No reveles nunca
la solución completa.

Responde ÚNICAMENTE con un objeto JSON válido con exactamente estos campos:
- diagnostico: descripción breve del error en español (1-2 oraciones)
- pregunta_guia: una pregunta socrática que ayude al estudiante a encontrar el error por sí mismo
- referencia_concepto: nombre del concepto estadístico o geográfico relevante
- mostrar_pista: true si el error es difícil y conviene mostrar la pista, false si el estudiante puede resolverlo solo

No incluyas texto fuera del objeto JSON.\
"""


async def generar_retroalimentacion(
    codigo_estudiante: str,
    error_output: str,
    ejercicio_id: str,
) -> tuple[str, str | None, bool, str | None]:
    """
    Call the LLM and return (diagnostico, pregunta_guia, mostrar_pista, referencia_concepto).
    Returns a fallback tuple on any failure.
    """
    user_message = (
        f"Ejercicio: {ejercicio_id}\n\n"
        f"Código del estudiante:\n```\n{codigo_estudiante}\n```\n\n"
        f"Error producido:\n```\n{error_output}\n```"
    )

    kwargs: dict = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key

    try:
        async with _LLM_SEMAPHORE:
            response = await asyncio.wait_for(
                litellm.acompletion(**kwargs),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        content = response.choices[0].message.content or ""
        data = json.loads(content)
        diagnostico = str(data.get("diagnostico", _FALLBACK_MESSAGE))
        pregunta_guia = data.get("pregunta_guia")
        mostrar_pista = bool(data.get("mostrar_pista", True))
        referencia_concepto = data.get("referencia_concepto")
        return diagnostico, pregunta_guia, mostrar_pista, referencia_concepto
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("LLM response parse error: %s", exc)
        return _FALLBACK_MESSAGE, None, False, None
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return _FALLBACK_MESSAGE, None, False, None
