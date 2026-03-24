from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routers import auth as auth_router
from api.database import get_db


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


_test_app = FastAPI(lifespan=_noop_lifespan)
_test_app.include_router(auth_router.router, prefix="/auth")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _test_app.dependency_overrides.clear()


def _make_db_override():
    """Return an AsyncMock suitable as a DB session dependency override."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def _make_user(
    rol: str = "teacher",
    is_active: bool = True,
    hashed_password: str | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "teacher@example.com"
    user.rol = rol
    user.is_active = is_active
    user.hashed_password = hashed_password or "$2b$12$placeholder"
    user.created_at = datetime.now(UTC)
    return user


# ---------------------------------------------------------------------------
# POST /auth/registro
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registro_success():
    db = _make_db_override()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=None)))

    # SQLAlchemy column defaults (id, is_active, created_at) are set at INSERT time,
    # not at Python object construction. Since commit/refresh are mocked we must
    # populate them in the refresh side-effect so the response serializer doesn't fail.
    def _populate_user(user):
        user.id = uuid.uuid4()
        user.is_active = True
        user.created_at = datetime.now(UTC)

    db.refresh = AsyncMock(side_effect=_populate_user)

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.hash_password", AsyncMock(return_value="hashed")):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/registro",
                json={"email": "new@example.com", "password": "secret123"},
            )

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_registro_duplicate_email_returns_409():
    existing_user = _make_user()
    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=existing_user))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/auth/registro",
            json={"email": "teacher@example.com", "password": "secret123"},
        )

    assert resp.status_code == 409
    assert "ya registrado" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_sets_cookies():
    user = _make_user()
    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=user))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.verify_password", AsyncMock(return_value=True)), \
         patch("api.routers.auth.create_access_token", return_value="access_tok"), \
         patch("api.routers.auth.create_refresh_token", AsyncMock(return_value=("refresh_tok", uuid.uuid4()))):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/login",
                json={"email": "teacher@example.com", "password": "secret123"},
            )

    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    user = _make_user()
    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=user))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.verify_password", AsyncMock(return_value=False)):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/login",
                json={"email": "teacher@example.com", "password": "wrong"},
            )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_user_not_found_returns_401():
    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": "noone@example.com", "password": "secret123"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401():
    user = _make_user(is_active=False)
    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=user))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.verify_password", AsyncMock(return_value=True)):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/auth/login",
                json={"email": "teacher@example.com", "password": "secret123"},
            )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Credenciales inválidas"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_cookies():
    db = _make_db_override()

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.revoke_refresh_token", AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            client.cookies.set("refresh_token", "some_refresh_token")
            resp = await client.post("/auth/logout")

    assert resp.status_code == 200
    assert resp.json()["mensaje"] == "Sesión cerrada"


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_no_cookie_returns_401():
    db = _make_db_override()

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.post("/auth/refresh")

    assert resp.status_code == 401
    assert "refresco" in resp.json()["detail"]


_TEST_SECRET = "test-secret-key-long-enough-for-hs256"


@pytest.mark.asyncio
async def test_refresh_revoked_token_returns_401():
    import jwt as _jwt
    from datetime import timedelta

    jti = uuid.uuid4()
    user_id = uuid.uuid4()
    token = _jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(jti),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    revoked_session = MagicMock()
    revoked_session.revoked_at = datetime.now(UTC)

    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=revoked_session))
    )

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.routers.auth.settings") as mock_cfg:
        mock_cfg.secret_key = _TEST_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            client.cookies.set("refresh_token", token)
            resp = await client.post("/auth/refresh")

    assert resp.status_code == 401
    assert "revocado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_valid_token_returns_new_access_token():
    import jwt as _jwt
    from datetime import timedelta

    jti = uuid.uuid4()
    user_id = uuid.uuid4()
    token = _jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(jti),
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    active_session = MagicMock()
    active_session.revoked_at = None

    active_user = _make_user()
    active_user.id = user_id
    active_user.is_active = True

    db = _make_db_override()
    db.execute = AsyncMock(
        return_value=AsyncMock(scalar_one_or_none=MagicMock(return_value=active_session))
    )
    db.get = AsyncMock(return_value=active_user)

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    new_jti = uuid.uuid4()
    with patch("api.routers.auth.settings") as mock_cfg, \
         patch("api.routers.auth.create_access_token", return_value="new_access_tok"), \
         patch("api.routers.auth.revoke_refresh_token", AsyncMock()), \
         patch("api.routers.auth.create_refresh_token", AsyncMock(return_value=("new_refresh_tok", new_jti))):
        mock_cfg.secret_key = _TEST_SECRET
        mock_cfg.access_token_expire_minutes = 15
        mock_cfg.refresh_token_expire_days = 7
        mock_cfg.cookie_secure = False
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            client.cookies.set("refresh_token", token)
            resp = await client.post("/auth/refresh")

    assert resp.status_code == 200
    assert resp.json()["mensaje"] == "Token renovado"
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_with_valid_cookie_returns_user():
    user = _make_user(rol="teacher")
    db = _make_db_override()
    db.get = AsyncMock(return_value=user)

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    with patch("api.dependencies.auth.verify_access_token", AsyncMock(return_value=MagicMock(sub=str(user.id), rol=user.rol))):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", "valid_token")
            resp = await client.get("/auth/me")

    assert resp.status_code == 200
    assert resp.json()["email"] == "teacher@example.com"
    assert resp.json()["rol"] == "teacher"


@pytest.mark.asyncio
async def test_me_without_cookie_returns_401():
    db = _make_db_override()

    async def _get_db_override():
        yield db

    _test_app.dependency_overrides[get_db] = _get_db_override

    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/auth/me")

    assert resp.status_code == 401
