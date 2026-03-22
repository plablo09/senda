from __future__ import annotations

import uuid
from datetime import datetime, UTC

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class EjecucionError(Base):
    __tablename__ = "ejecucion_errores"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    documento_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ejercicio_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    error_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    error_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
