from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from api.config import settings
from api.database import DbDep, get_db
from api.models.sesion_refresh import SesionRefresh
from api.models.usuario import Usuario
from api.dependencies.auth import CurrentUser
from api.schemas.auth import LoginRequest, UsuarioCreate, UsuarioResponse
from api.limiter import limiter
from api.services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    revoke_refresh_token,
    verify_password,
    verify_refresh_token,
)

router = APIRouter(tags=["auth"])

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
    response.delete_cookie("access_token", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie("refresh_token", secure=settings.cookie_secure, httponly=True, samesite="lax")


@router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def registro(request: Request, payload: UsuarioCreate, db: DbDep) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email ya registrado"
        )
    hashed_pw = await hash_password(payload.password)
    user = Usuario(email=payload.email, hashed_password=hashed_pw, rol="student")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, response: Response, db: DbDep) -> dict:
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )
    if not await verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )
    access_token = create_access_token(user.id, user.rol)
    refresh_token, _ = await create_refresh_token(user.id, db)
    _set_auth_cookies(response, access_token, refresh_token)
    return {"mensaje": "Sesión iniciada", "access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
@limiter.limit("20/minute")
async def logout(request: Request, response: Response, db: DbDep) -> dict:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = await verify_refresh_token(refresh_token)
            await revoke_refresh_token(uuid.UUID(payload.jti), db)
        except HTTPException:
            pass  # token already invalid or malformed — proceed with clearing cookies
    _clear_auth_cookies(response)
    return {"mensaje": "Sesión cerrada"}


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(request: Request, response: Response, db: DbDep) -> dict:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sin token de refresco"
        )
    payload = await verify_refresh_token(token)

    jti = uuid.UUID(payload.jti)
    result = await db.execute(select(SesionRefresh).where(SesionRefresh.jti == jti))
    session = result.scalar_one_or_none()
    if not session or session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de refresco revocado"
        )

    user = await db.get(Usuario, uuid.UUID(payload.sub))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado",
        )

    await revoke_refresh_token(jti, db)
    new_access_token = create_access_token(user.id, user.rol)
    new_refresh_token, _ = await create_refresh_token(user.id, db)
    _set_auth_cookies(response, new_access_token, new_refresh_token)
    return {"mensaje": "Token renovado"}


@router.get("/me", response_model=UsuarioResponse)
async def me(user: CurrentUser) -> Usuario:
    return user
