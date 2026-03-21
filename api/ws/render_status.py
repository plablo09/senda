from __future__ import annotations
import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/documentos/{documento_id}/estado")
async def render_status(websocket: WebSocket, documento_id: str):
    await websocket.accept()
    redis_client = aioredis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"render:{documento_id}")

    async def forward_redis():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"].decode())
                    # Stop after terminal status
                    data = json.loads(message["data"])
                    if data.get("status") in ("listo", "fallido"):
                        break
        except Exception:
            pass

    async def drain_client():
        """Keep connection alive — consume any client messages (we don't use them)."""
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(forward_redis(), drain_client())
    except Exception:
        logger.exception("Error en WebSocket de estado de render")
    finally:
        await pubsub.unsubscribe(f"render:{documento_id}")
        await redis_client.aclose()
        try:
            await websocket.close()
        except Exception:
            pass
