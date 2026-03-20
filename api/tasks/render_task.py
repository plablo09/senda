from __future__ import annotations
import asyncio
from celery_app import celery_app

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def render_documento(self, documento_id: str):
    """
    Celery task: fetch documento → serialize to .qmd → quarto render → upload to MinIO → update DB.
    """
    import asyncio
    from database import AsyncSessionLocal
    from models.documento import Documento
    from services.qmd_serializer import serialize_document
    from services.renderer import render_qmd, RenderError
    from services.storage import upload_html, ensure_bucket_exists
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
            except RenderError as exc:
                doc.estado_render = "fallido"
                doc.error_render = str(exc)
            except Exception as exc:
                doc.estado_render = "fallido"
                doc.error_render = f"Error inesperado: {exc}"
                raise self.retry(exc=exc)
            finally:
                await session.commit()

    asyncio.run(_run())


@celery_app.task
def cleanup_stale_containers():
    """Celery beat task: kill execution containers whose Redis session has expired."""
    import docker
    import redis as redis_lib
    from config import settings

    r = redis_lib.from_url(settings.redis_url)
    client = docker.from_env()

    for container in client.containers.list(filters={"label": "senda.exec=true"}):
        container_id = container.id[:12]
        # Check if any session still references this container
        matching_keys = r.keys(f"session:*:container_id")
        active_ids = {r.get(k).decode() for k in matching_keys if r.get(k)}
        if container_id not in active_ids:
            try:
                container.kill()
                container.remove()
            except Exception:
                pass
