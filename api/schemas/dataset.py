from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class DatasetResponse(BaseModel):
    id: uuid.UUID
    filename: str
    url: str
    mimetype: str
    es_publico: bool
    created_at: datetime

    model_config = {"from_attributes": True}
