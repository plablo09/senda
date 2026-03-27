from __future__ import annotations
import json
import logging
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from api.dependencies.auth import CurrentUser
from api.limiter import limiter
from api.schemas.ejecutar import EjecucionRequest, EjecucionResponse, OutputChunkResponse
from api.services.auth_service import verify_access_token
from api.services.execution_pool import execution_pool

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/ejecutar", response_model=EjecucionResponse)
@limiter.limit("30/minute")
async def ejecutar_http(
    request: Request, payload: EjecucionRequest, current_user: CurrentUser
) -> EjecucionResponse:
    """HTTP endpoint for code execution — collects all output chunks and returns JSON.
    Useful for agents, CI pipelines, and curl. The WebSocket endpoint at /ws/ejecutar
    remains available for interactive browser use.
    """
    chunks = []
    async for chunk in execution_pool.execute(payload.language, payload.code):
        chunks.append(OutputChunkResponse(tipo=chunk.tipo, contenido=chunk.contenido))
    return EjecucionResponse(chunks=chunks)


@router.websocket("/ws/ejecutar")
async def ejecutar(websocket: WebSocket):
    await websocket.accept()

    # Auth check: cookie first, then Authorization: Bearer header
    token = websocket.cookies.get("access_token")
    if not token:
        auth_header = websocket.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        await websocket.close(code=4008)
        return
    try:
        await verify_access_token(token)
    except Exception:
        await websocket.close(code=4008)
        return

    try:
        data = await websocket.receive_text()
        payload = json.loads(data)

        session_id = payload.get("session_id", str(id(websocket)))
        exercise_id = payload.get("exercise_id", "desconocido")
        language = payload.get("language", "python")
        code = payload.get("code", "")

        async for chunk in execution_pool.execute(language, code):
            await websocket.send_json({
                "tipo": chunk.tipo,
                "contenido": chunk.contenido,
                "exercise_id": exercise_id,
            })

    except WebSocketDisconnect:
        logger.info("Cliente desconectado del WebSocket")
    except json.JSONDecodeError:
        await websocket.send_json({"tipo": "error", "contenido": "Formato de mensaje inválido."})
    except Exception as exc:
        logger.exception("Error en WebSocket de ejecución")
        try:
            await websocket.send_json({"tipo": "error", "contenido": "Error interno del servidor."})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
