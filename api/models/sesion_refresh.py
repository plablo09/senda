from __future__ import annotations

import uuid
from datetime import datetime, UTC

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class SesionRefresh(Base):
    __tablename__ = "sesiones_refresh"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    jti: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(), nullable=False, unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=sa.text("NOW()"),
        nullable=False,
    )
