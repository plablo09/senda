from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from api.database import get_db
from api.models.dataset import Dataset
from api.schemas.dataset import DatasetResponse
from api.services.storage import upload_dataset, delete_object
from api.config import DATASET_ACCEPTED_MIMETYPES, DATASET_MAX_SIZE_BYTES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["datasets"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def subir_dataset(file: UploadFile, db: DbDep) -> Dataset:
    # Read content first to check size
    content = await file.read()

    if len(content) > DATASET_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera el límite de 50 MB.",
        )

    mimetype = file.content_type or ""
    if mimetype not in DATASET_ACCEPTED_MIMETYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo de archivo no permitido: {mimetype}. Tipos aceptados: {', '.join(sorted(DATASET_ACCEPTED_MIMETYPES))}",
        )

    dataset_id = str(uuid.uuid4())
    url = await asyncio.to_thread(upload_dataset, dataset_id, file.filename or "archivo", content, mimetype)

    dataset = Dataset(
        id=uuid.UUID(dataset_id),
        filename=file.filename or "archivo",
        url=url,
        mimetype=mimetype,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetResponse])
async def listar_datasets(db: DbDep) -> list[Dataset]:
    result = await db.execute(select(Dataset).order_by(Dataset.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_dataset(dataset_id: uuid.UUID, db: DbDep) -> None:
    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset no encontrado")

    # Extract key from URL: everything after the bucket name
    # URL format: {public_endpoint}/{bucket}/{key}
    from api.config import settings
    prefix = f"{settings.storage_public_endpoint}/{settings.storage_bucket}/"
    if dataset.url.startswith(prefix):
        key = dataset.url[len(prefix):]
        try:
            await asyncio.to_thread(delete_object, key)
        except Exception:
            logger.warning("Failed to delete dataset object from storage (dataset_id=%s, key=%s)", dataset_id, key, exc_info=True)
    else:
        logger.warning("Dataset URL does not match expected prefix; skipping storage delete (dataset_id=%s, url=%s)", dataset_id, dataset.url)

    await db.delete(dataset)
    await db.commit()
