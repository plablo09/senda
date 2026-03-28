"""
Shared fixtures for integration tests.

Tests run inside the `api` Docker container against the live stack:
    make test-int
    # docker compose run --rm -e PYTHONPATH=/app api pytest api/tests/integration/ -v

All HTTP calls go to http://api:8000 (the internal Docker service name).
Never use localhost here — these tests run inside Docker.

NOTE: The documentos, datasets, and retroalimentacion routers have no auth
today (Phase 2 auth only covers /ejecutar and /auth/me). Tests reflect that.
When auth is added to those routers this conftest will need auth_headers passed
to document fixtures.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

# ---------------------------------------------------------------------------
# Base URL — internal Docker service, not localhost
# ---------------------------------------------------------------------------

BASE_URL = "http://api:8000"


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _random_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@senda-test.local"


@pytest.fixture
async def registered_user(client: httpx.AsyncClient) -> dict:
    """Registers a student account. Returns {email, password, id}."""
    email = _random_email()
    password = "Test1234!"
    resp = await client.post("/auth/registro", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return {"email": email, "password": password, "id": resp.json()["id"]}


@pytest.fixture
async def auth_token(client: httpx.AsyncClient, registered_user: dict) -> str:
    """Logs in and returns the access_token string from the JSON body."""
    resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("access_token")
    assert token, "access_token missing from login response body"
    return token


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Authorization header dict for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
async def login_response(client: httpx.AsyncClient, registered_user: dict) -> httpx.Response:
    """Full login response — exposes cookies (refresh_token) for refresh/logout tests."""
    resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    return resp


# ---------------------------------------------------------------------------
# AST fixtures
# ---------------------------------------------------------------------------

MINIMAL_AST = {
    "schemaVersion": 1,
    "blocks": [
        {"type": "text", "text": "# Título de prueba"},
        {"type": "text", "text": "Párrafo de contenido."},
    ],
}

FULL_AST = {
    "schemaVersion": 1,
    "blocks": [
        {"type": "text", "text": "# Documento completo"},
        {"type": "text", "text": "Párrafo introductorio."},
        {
            "type": "ejercicio",
            "attrs": {
                "exerciseId": "ej-001",
                "language": "python",
                "caption": "Ejercicio de prueba",
                "starterCode": "# escribe tu código aquí",
                "solutionCode": "print('hola')",
                "hints": ["Piensa en print()", "Usa comillas"],
            },
        },
        {"type": "nota", "attrs": {"content": "Esta es una nota importante."}},
        {"type": "ecuacion", "attrs": {"latex": "E = mc^2", "display": True}},
    ],
}


# ---------------------------------------------------------------------------
# Document fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def created_document(client: httpx.AsyncClient) -> AsyncGenerator[dict, None]:
    """Creates a document without AST (no render triggered). Deletes on teardown."""
    resp = await client.post("/documentos", json={"titulo": "Doc de prueba de integración"})
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    yield doc
    await client.delete(f"/documentos/{doc['id']}")


async def _wait_for_render(
    client: httpx.AsyncClient, doc_id: str, timeout: int = 90
) -> dict:
    """
    Polls GET /documentos/{id} until estado_render is a terminal state.

    Falls back to polling instead of WebSocket to avoid the pub/sub race
    condition (task completing before WS subscription is established).
    Returns the final document dict.
    """
    for _ in range(timeout):
        resp = await client.get(f"/documentos/{doc_id}")
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        if doc["estado_render"] in ("listo", "fallido"):
            return doc
        await asyncio.sleep(1.0)
    # Return whatever state we have on timeout
    resp = await client.get(f"/documentos/{doc_id}")
    return resp.json()


@pytest.fixture
async def rendered_document(client: httpx.AsyncClient) -> AsyncGenerator[dict, None]:
    """
    Creates a document with MINIMAL_AST, waits for the render pipeline to
    reach a terminal state (listo or fallido). Deletes on teardown.
    """
    resp = await client.post(
        "/documentos",
        json={"titulo": "Doc render de integración", "ast": MINIMAL_AST},
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]

    doc = await _wait_for_render(client, doc_id, timeout=90)
    yield doc
    await client.delete(f"/documentos/{doc_id}")
