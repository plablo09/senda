from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, UTC

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models.sesion_refresh import SesionRefresh
from api.schemas.auth import TokenPayload

_ALGORITHM = "HS256"


async def hash_password(plain: str) -> str:
    hashed: bytes = await asyncio.to_thread(bcrypt.hashpw, plain.encode(), bcrypt.gensalt())
    return hashed.decode()


async def verify_password(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(bcrypt.checkpw, plain.encode(), hashed.encode())


def create_access_token(user_id: uuid.UUID, rol: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "rol": rol,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


async def create_refresh_token(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[str, uuid.UUID]:
    jti = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    token = jwt.encode(
        {"sub": str(user_id), "jti": str(jti), "exp": expires_at},
        settings.secret_key,
        algorithm=_ALGORITHM,
    )
    db.add(SesionRefresh(jti=jti, user_id=user_id, expires_at=expires_at))
    await db.commit()
    return token, jti


def verify_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return TokenPayload(sub=payload["sub"], rol=payload["rol"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


async def revoke_refresh_token(jti: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(SesionRefresh).where(SesionRefresh.jti == jti))
    session = result.scalar_one_or_none()
    if session:
        session.revoked_at = datetime.now(UTC)
        await db.commit()
