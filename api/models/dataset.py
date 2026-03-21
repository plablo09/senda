from __future__ import annotations
import uuid
from datetime import datetime, UTC
from sqlalchemy import DateTime, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from api.database import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    mimetype: Mapped[str] = mapped_column(String(100), nullable=False)
    es_publico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
