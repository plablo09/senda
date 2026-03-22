from __future__ import annotations
import asyncio
import json as _json

import redis as redis_sync

from api.celery_app import celery_app


def _publish_render_status(documento_id: str, status: str, url_artefacto: str | None, error_render: str | None) -> None:
    """Publish render completion to Redis pub/sub channel."""
    try:
        from api.config import settings
        r = redis_sync.from_url(settings.redis_url)
        r.publish(f"render:{documento_id}", _json.dumps({
            "status": status,
            "url_artefacto": url_artefacto,
            "error_render": error_render,
        }))
        r.close()
    except Exception:
        pass  # best-effort — DB is already committed


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def render_documento(self, documento_id: str):
    """
    Celery task: fetch documento → serialize to .qmd → quarto render → upload to MinIO → update DB.
    """
    from api.database import AsyncSessionLocal
    from api.models.documento import Documento
    from api.services.qmd_serializer import serialize_document
    from api.services.renderer import render_qmd, RenderError
    from api.services.storage import upload_html, ensure_bucket_exists
    from sqlalchemy import select

    async def _run():
        async with AsyncSessionLocal() as session:
            # Fetch documento
            result = await session.execute(select(Documento).where(Documento.id == documento_id))
            doc = result.scalar_one_or_none()
            if not doc:
                return

            # Mark as processing
            doc.estado_render = "procesando"
            await session.commit()

            try:
                # Serialize AST → .qmd
                qmd_source = serialize_document(doc.ast or {}, titulo=doc.titulo)
                doc.qmd_source = qmd_source

                # Render
                ensure_bucket_exists()
                html_bytes = render_qmd(qmd_source, str(doc.id))

                # Upload
                url = upload_html(str(doc.id), html_bytes)

                # Update
                doc.url_artefacto = url
                doc.estado_render = "listo"
                doc.error_render = None
                await session.commit()
                _publish_render_status(documento_id, "listo", doc.url_artefacto, None)
            except RenderError as exc:
                # Permanent failure — commit terminal state immediately
                doc.estado_render = "fallido"
                doc.error_render = str(exc)
                await session.commit()
                _publish_render_status(documento_id, "fallido", None, doc.error_render)
            except Exception as exc:
                if self.request.retries >= self.max_retries:
                    # All retries exhausted — commit terminal state
                    doc.estado_render = "fallido"
                    doc.error_render = f"Error inesperado: {exc}"
                    await session.commit()
                    _publish_render_status(documento_id, "fallido", None, doc.error_render)
                else:
                    # Transient failure — reset so retry starts clean
                    doc.estado_render = "pendiente"
                    doc.error_render = None
                    await session.commit()
                    raise self.retry(exc=exc)

    asyncio.run(_run())


@celery_app.task
def reset_stale_procesando():
    """Reset documents stuck in 'procesando' for > 10 minutes to 'fallido'."""
    from datetime import datetime, UTC, timedelta
    from api.database import AsyncSessionLocal
    from api.models.documento import Documento
    from sqlalchemy import select

    async def _run():
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Documento).where(
                    Documento.estado_render == "procesando",
                    Documento.updated_at < cutoff,
                )
            )
            stale = result.scalars().all()
            for doc in stale:
                doc.estado_render = "fallido"
                doc.error_render = "Tiempo de procesamiento agotado"
            if stale:
                await session.commit()
                for doc in stale:
                    _publish_render_status(str(doc.id), "fallido", None, doc.error_render)

    asyncio.run(_run())
