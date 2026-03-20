from __future__ import annotations
import asyncio
from api.celery_app import celery_app

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
            except RenderError as exc:
                # Permanent failure — commit terminal state immediately
                doc.estado_render = "fallido"
                doc.error_render = str(exc)
                await session.commit()
            except Exception as exc:
                if self.request.retries >= self.max_retries:
                    # All retries exhausted — commit terminal state
                    doc.estado_render = "fallido"
                    doc.error_render = f"Error inesperado: {exc}"
                    await session.commit()
                else:
                    # Transient failure — reset so retry starts clean
                    doc.estado_render = "pendiente"
                    doc.error_render = None
                    await session.commit()
                    raise self.retry(exc=exc)

    asyncio.run(_run())
