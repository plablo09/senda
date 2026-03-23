from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.models.sesion_refresh import SesionRefresh
from api.models.usuario import Usuario
from api.schemas.auth import LoginRequest, UsuarioCreate, UsuarioResponse
from api.services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    revoke_refresh_token,
    verify_password,
)

router = APIRouter(tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_COOKIE_KWARGS = dict(httponly=True, samesite="lax")


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.access_token_expire_minutes * 60,
        secure=settings.cookie_secure,
        **_COOKIE_KWARGS,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        secure=settings.cookie_secure,
        **_COOKIE_KWARGS,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")


@router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def registro(payload: UsuarioCreate, db: DbDep) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email ya registrado"
        )
    hashed_pw = await hash_password(payload.password)
    user = Usuario(email=payload.email, hashed_password=hashed_pw, rol=payload.rol)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login")
async def login(payload: LoginRequest, response: Response, db: DbDep) -> dict:
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )
    if not await verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Cuenta inactiva"
        )
    access_token = create_access_token(user.id, user.rol)
    refresh_token, _ = await create_refresh_token(user.id, db)
    _set_auth_cookies(response, access_token, refresh_token)
    return {"mensaje": "Sesión iniciada"}


@router.post("/logout")
async def logout(request: Request, response: Response, db: DbDep) -> dict:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = jwt.decode(
                refresh_token, settings.secret_key, algorithms=["HS256"]
            )
            await revoke_refresh_token(uuid.UUID(payload["jti"]), db)
        except Exception:
            pass  # token already invalid — proceed with clearing cookies
    _clear_auth_cookies(response)
    return {"mensaje": "Sesión cerrada"}


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: DbDep) -> dict:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sin token de refresco"
        )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de refresco expirado"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de refresco inválido"
        )

    jti = uuid.UUID(payload["jti"])
    result = await db.execute(select(SesionRefresh).where(SesionRefresh.jti == jti))
    session = result.scalar_one_or_none()
    if not session or session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de refresco revocado"
        )

    user = await db.get(Usuario, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado",
        )

    new_access_token = create_access_token(user.id, user.rol)
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        max_age=settings.access_token_expire_minutes * 60,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"mensaje": "Token renovado"}
