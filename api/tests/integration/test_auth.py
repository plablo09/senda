"""
Zone 1 — Auth integration tests.

All tests run against the live Docker Compose stack (http://api:8000).
No dependency_overrides, no mocks — real DB, real JWT, real cookies.

Coverage:
  Happy path:  registro, login (token in body), /me, refresh rotation, logout
  Negative:    duplicate email, wrong password, nonexistent email, no token,
               invalid token, missing payload field, refresh without cookie
"""
from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import BASE_URL

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registro_creates_user(client: httpx.AsyncClient):
    from tests.integration.conftest import _random_email

    email = _random_email()
    resp = await client.post(
        "/auth/registro", json={"email": email, "password": "Test1234!"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert body["rol"] == "student"
    assert body["is_active"] is True
    assert "id" in body


@pytest.mark.asyncio
async def test_login_returns_token_in_body(
    client: httpx.AsyncClient, registered_user: dict
):
    resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 10
    assert body.get("token_type") == "bearer"
    # Set-Cookie headers must be present (httpOnly cookies for browsers)
    cookie_names = [c.split("=")[0] for c in resp.headers.get_list("set-cookie")]
    assert "access_token" in cookie_names
    assert "refresh_token" in cookie_names


@pytest.mark.asyncio
async def test_me_with_valid_bearer_token(
    client: httpx.AsyncClient, registered_user: dict, auth_token: str
):
    resp = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == registered_user["email"]
    assert body["rol"] == "student"


@pytest.mark.asyncio
async def test_refresh_returns_new_token(
    client: httpx.AsyncClient, login_response: httpx.Response
):
    # Extract refresh_token from Set-Cookie header
    refresh_token = None
    for cookie_header in login_response.headers.get_list("set-cookie"):
        if cookie_header.startswith("refresh_token="):
            refresh_token = cookie_header.split("=", 1)[1].split(";")[0]
            break
    assert refresh_token, "refresh_token cookie not set by login"

    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, cookies={"refresh_token": refresh_token}
    ) as cookie_client:
        resp = await cookie_client.post("/auth/refresh")
    assert resp.status_code == 200
    # New cookies must be set
    new_cookie_names = [c.split("=")[0] for c in resp.headers.get_list("set-cookie")]
    assert "access_token" in new_cookie_names


@pytest.mark.asyncio
async def test_refresh_token_rotation_revokes_original(
    client: httpx.AsyncClient, login_response: httpx.Response
):
    """Using a refresh token once must invalidate it — second use must return 401."""
    refresh_token = None
    for cookie_header in login_response.headers.get_list("set-cookie"):
        if cookie_header.startswith("refresh_token="):
            refresh_token = cookie_header.split("=", 1)[1].split(";")[0]
            break
    assert refresh_token

    # First use: should succeed
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, cookies={"refresh_token": refresh_token}
    ) as cookie_client:
        resp1 = await cookie_client.post("/auth/refresh")
    assert resp1.status_code == 200

    # Second use of the same token: must be rejected (rotation)
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, cookies={"refresh_token": refresh_token}
    ) as cookie_client:
        resp2 = await cookie_client.post("/auth/refresh")
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_session(
    client: httpx.AsyncClient, registered_user: dict, auth_token: str
):
    # Extract refresh_token by doing a fresh login
    login_resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    refresh_token = None
    for cookie_header in login_resp.headers.get_list("set-cookie"):
        if cookie_header.startswith("refresh_token="):
            refresh_token = cookie_header.split("=", 1)[1].split(";")[0]
            break
    assert refresh_token

    # Logout
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, cookies={"refresh_token": refresh_token}
    ) as cookie_client:
        logout_resp = await cookie_client.post("/auth/logout")
    assert logout_resp.status_code == 200

    # The revoked refresh token must no longer work
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=30.0, cookies={"refresh_token": refresh_token}
    ) as cookie_client:
        refresh_resp = await cookie_client.post("/auth/refresh")
    assert refresh_resp.status_code == 401


# ---------------------------------------------------------------------------
# Negative / security cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registro_duplicate_email_returns_409(
    client: httpx.AsyncClient, registered_user: dict
):
    # Reuse the already-registered user's email — avoids an extra registro call
    # that could exhaust the 5/min rate limit.
    resp = await client.post(
        "/auth/registro",
        json={"email": registered_user["email"], "password": "OtherPass1!"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    client: httpx.AsyncClient, registered_user: dict
):
    resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(client: httpx.AsyncClient):
    resp = await client.post(
        "/auth/login",
        json={"email": "noexiste@senda-test.local", "password": "Test1234!"},
    )
    # Must be 401, not 404 — do not leak whether the email exists
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: httpx.AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client: httpx.AsyncClient):
    resp = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_registro_missing_email_returns_422(client: httpx.AsyncClient):
    resp = await client.post("/auth/registro", json={"password": "Test1234!"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: httpx.AsyncClient):
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401
