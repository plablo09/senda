from __future__ import annotations

import uuid
from datetime import datetime, UTC

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    ast: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    qmd_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_render: Mapped[str] = mapped_column(String(50), default="pendiente", nullable=False)
    url_artefacto: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_render: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
