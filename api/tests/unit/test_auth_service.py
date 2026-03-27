from __future__ import annotations

import uuid
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from api.services.auth_service import (
    _ALGORITHM,
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)

_SECRET = "test-secret"


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hash_and_verify_password_success():
    hashed = await hash_password("secret123")
    assert await verify_password("secret123", hashed) is True


@pytest.mark.asyncio
async def test_verify_wrong_password_returns_false():
    hashed = await hash_password("secret123")
    assert await verify_password("wrong", hashed) is False


@pytest.mark.asyncio
async def test_hash_is_not_plaintext():
    plain = "secret123"
    hashed = await hash_password(plain)
    assert hashed != plain


# ---------------------------------------------------------------------------
# create_access_token / verify_access_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_verify_access_token():
    user_id = uuid.uuid4()
    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        mock_cfg.access_token_expire_minutes = 15
        token = create_access_token(user_id, "teacher")
        payload = await verify_access_token(token)

    assert payload.sub == str(user_id)
    assert payload.rol == "teacher"


@pytest.mark.asyncio
async def test_verify_access_token_expired_raises_401():
    from fastapi import HTTPException

    user_id = uuid.uuid4()
    expired_payload = {
        "sub": str(user_id),
        "rol": "student",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) - timedelta(seconds=1),
    }
    token = jwt.encode(expired_payload, _SECRET, algorithm=_ALGORITHM)
    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_access_token(token)

    assert exc_info.value.status_code == 401
    assert "expirado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_access_token_invalid_raises_401():
    from fastapi import HTTPException

    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_access_token("not.a.token")

    assert exc_info.value.status_code == 401
    assert "inválido" in exc_info.value.detail


# ---------------------------------------------------------------------------
# verify_refresh_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_refresh_token_valid():
    jti = uuid.uuid4()
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": str(jti),
        "exp": datetime.now(UTC) + timedelta(days=7),
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        result = await verify_refresh_token(token)

    assert result.sub == payload["sub"]
    assert result.jti == payload["jti"]


@pytest.mark.asyncio
async def test_verify_refresh_token_expired_raises_401():
    from fastapi import HTTPException

    payload = {
        "sub": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(UTC) - timedelta(seconds=1),
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_refresh_token(token)

    assert exc_info.value.status_code == 401
    assert "expirado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_refresh_token_invalid_raises_401():
    from fastapi import HTTPException

    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_refresh_token("not.a.token")

    assert exc_info.value.status_code == 401
    assert "inválido" in exc_info.value.detail


# ---------------------------------------------------------------------------
# create_refresh_token / revoke_refresh_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_refresh_token_persists_to_db():
    from api.services.auth_service import create_refresh_token

    user_id = uuid.uuid4()
    db = AsyncMock()

    with patch("api.services.auth_service.settings") as mock_cfg:
        mock_cfg.secret_key = _SECRET
        mock_cfg.refresh_token_expire_days = 7
        token, jti = await create_refresh_token(user_id, db)

    assert isinstance(token, str)
    assert isinstance(jti, uuid.UUID)
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_refresh_token_sets_revoked_at():
    from api.services.auth_service import revoke_refresh_token
    from api.models.sesion_refresh import SesionRefresh

    jti = uuid.uuid4()
    mock_session = MagicMock(spec=SesionRefresh)
    mock_session.revoked_at = None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=mock_session)))

    await revoke_refresh_token(jti, db)

    assert mock_session.revoked_at is not None
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_refresh_token_missing_session_is_noop():
    from api.services.auth_service import revoke_refresh_token

    jti = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=None)))

    await revoke_refresh_token(jti, db)

    db.commit.assert_not_called()
