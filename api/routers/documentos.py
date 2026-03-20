from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.documento import Documento
from api.schemas.documento import DocumentoCreate, DocumentoResponse, DocumentoUpdate

try:
    from api.tasks.render_task import render_task
except ImportError:
    render_task = None  # type: ignore[assignment]

router = APIRouter(tags=["documentos"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=DocumentoResponse, status_code=status.HTTP_201_CREATED)
async def crear_documento(payload: DocumentoCreate, db: DbDep) -> Documento:
    doc = Documento(titulo=payload.titulo, ast=payload.ast)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    if payload.ast is not None and render_task is not None:
        render_task.delay(str(doc.id))

    return doc


@router.get("", response_model=list[DocumentoResponse])
async def listar_documentos(db: DbDep) -> list[Documento]:
    result = await db.execute(select(Documento).order_by(Documento.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{documento_id}", response_model=DocumentoResponse)
async def obtener_documento(documento_id: uuid.UUID, db: DbDep) -> Documento:
    doc = await db.get(Documento, documento_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado",
        )
    return doc


@router.put("/{documento_id}", response_model=DocumentoResponse)
async def actualizar_documento(
    documento_id: uuid.UUID,
    payload: DocumentoUpdate,
    db: DbDep,
) -> Documento:
    doc = await db.get(Documento, documento_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado",
        )

    ast_changed = False

    if payload.titulo is not None:
        doc.titulo = payload.titulo
    if payload.ast is not None:
        doc.ast = payload.ast
        ast_changed = True

    await db.commit()
    await db.refresh(doc)

    if ast_changed and render_task is not None:
        render_task.delay(str(doc.id))

    return doc


@router.delete("/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_documento(documento_id: uuid.UUID, db: DbDep) -> None:
    doc = await db.get(Documento, documento_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado",
        )
    await db.delete(doc)
    await db.commit()
