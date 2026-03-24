from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from api.database import DbDep
from api.models.usuario import Usuario
from api.services.auth_service import verify_access_token


async def get_current_user(request: Request, db: DbDep) -> Usuario:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    payload = await verify_access_token(token)
    user = await db.get(Usuario, uuid.UUID(payload.sub))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo"
        )
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


async def require_teacher(user: CurrentUser) -> Usuario:
    if user.rol != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol de profesor"
        )
    return user


async def require_student(user: CurrentUser) -> Usuario:
    if user.rol != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol de estudiante"
        )
    return user
