from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.llm_feedback import _FALLBACK_MESSAGE, generar_retroalimentacion


def _make_llm_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_successful_structured_response():
    """Valid JSON from LLM is parsed into (diagnostico, pregunta_guia, mostrar_pista)."""
    payload = {
        "diagnostico": "El error indica que la variable 'df' no está definida.",
        "pregunta_guia": "¿En qué línea declaras la variable 'df' por primera vez?",
        "referencia_concepto": "DataFrame de pandas",
        "mostrar_pista": True,
    }
    mock_response = _make_llm_response(json.dumps(payload))

    with patch("api.services.llm_feedback.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        diagnostico, pregunta_guia, mostrar_pista = await generar_retroalimentacion(
            codigo_estudiante="df.head()",
            error_output="NameError: name 'df' is not defined",
            ejercicio_id="ej-1",
        )

    assert diagnostico == payload["diagnostico"]
    assert pregunta_guia == payload["pregunta_guia"]
    assert mostrar_pista is True


@pytest.mark.asyncio
async def test_json_parse_failure_returns_fallback():
    """If the LLM returns invalid JSON, return the fallback message."""
    mock_response = _make_llm_response("Lo siento, no puedo ayudarte.")

    with patch("api.services.llm_feedback.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        diagnostico, pregunta_guia, mostrar_pista = await generar_retroalimentacion(
            codigo_estudiante="x = 1",
            error_output="SyntaxError",
            ejercicio_id="ej-2",
        )

    assert diagnostico == _FALLBACK_MESSAGE
    assert pregunta_guia is None
    assert mostrar_pista is False


@pytest.mark.asyncio
async def test_litellm_exception_returns_fallback():
    """If LiteLLM raises (network error, quota, etc.), return the fallback message."""
    with patch(
        "api.services.llm_feedback.litellm.acompletion",
        new=AsyncMock(side_effect=Exception("quota exceeded")),
    ):
        diagnostico, pregunta_guia, mostrar_pista = await generar_retroalimentacion(
            codigo_estudiante="import geopandas",
            error_output="ModuleNotFoundError",
            ejercicio_id="ej-3",
        )

    assert diagnostico == _FALLBACK_MESSAGE
    assert pregunta_guia is None
    assert mostrar_pista is False


@pytest.mark.asyncio
async def test_missing_fields_use_defaults():
    """Partial JSON response (missing optional fields) should not crash."""
    payload = {"diagnostico": "Error de tipo."}
    mock_response = _make_llm_response(json.dumps(payload))

    with patch("api.services.llm_feedback.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        diagnostico, pregunta_guia, mostrar_pista = await generar_retroalimentacion(
            codigo_estudiante="1 + 'a'",
            error_output="TypeError",
            ejercicio_id="ej-4",
        )

    assert diagnostico == "Error de tipo."
    assert pregunta_guia is None
    assert mostrar_pista is True  # default
