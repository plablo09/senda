from __future__ import annotations

import asyncio
from datetime import datetime, UTC

from sqlalchemy import delete

from api.celery_app import celery_app
from api.database import AsyncSessionLocal
from api.models.sesion_refresh import SesionRefresh


@celery_app.task
def cleanup_expired_sessions() -> None:
    """Delete expired and revoked refresh token rows from sesiones_refresh."""

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SesionRefresh).where(
                    (SesionRefresh.expires_at < datetime.now(UTC))
                    | SesionRefresh.revoked_at.isnot(None)
                )
            )
            await session.commit()

    asyncio.run(_run())

