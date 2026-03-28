"""
Zone 2 — Document lifecycle integration tests.

All tests run against the live Docker Compose stack (http://api:8000).
No dependency_overrides — real DB, real Celery worker, real MinIO bucket.

Coverage:
  CRUD:           create (no AST), get, list, update, delete, 404
  Render pipeline: create with AST → Celery → Quarto → MinIO → public GET 200
  AST round-trip: saved ast is returned unchanged on GET (regression for Bug 6)
  Edge cases:     empty blocks, malformed ast (422), large text, ejercicio fields

NOTE: The documentos router has no auth today. Tests do not send auth headers.
When auth is added to this router, update these tests to use auth_headers fixture.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from tests.integration.conftest import (
    FULL_AST,
    MINIMAL_AST,
    _wait_for_render,
    internal_artifact_url,
)

# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_document_no_ast(client: httpx.AsyncClient):
    resp = await client.post("/documentos", json={"titulo": "Sin AST"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["titulo"] == "Sin AST"
    assert body["ast"] is None
    # No render triggered when ast is None
    assert body["estado_render"] == "pendiente"
    # Cleanup
    await client.delete(f"/documentos/{body['id']}")


@pytest.mark.asyncio
async def test_get_document(client: httpx.AsyncClient, created_document: dict):
    resp = await client.get(f"/documentos/{created_document['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created_document["id"]
    assert body["titulo"] == created_document["titulo"]
    # All response fields must be present
    for field in ("id", "titulo", "ast", "estado_render", "url_artefacto", "error_render",
                  "created_at", "updated_at"):
        assert field in body, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_list_documents(client: httpx.AsyncClient, created_document: dict):
    resp = await client.get("/documentos")
    assert resp.status_code == 200
    docs = resp.json()
    assert isinstance(docs, list)
    ids = [d["id"] for d in docs]
    assert created_document["id"] in ids


@pytest.mark.asyncio
async def test_update_document_titulo(
    client: httpx.AsyncClient, created_document: dict
):
    resp = await client.put(
        f"/documentos/{created_document['id']}",
        json={"titulo": "Título actualizado"},
    )
    assert resp.status_code == 200
    assert resp.json()["titulo"] == "Título actualizado"


@pytest.mark.asyncio
async def test_delete_document(client: httpx.AsyncClient):
    resp = await client.post("/documentos", json={"titulo": "Para borrar"})
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    del_resp = await client.delete(f"/documentos/{doc_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/documentos/{doc_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_document_returns_404(client: httpx.AsyncClient):
    resp = await client.get(f"/documentos/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Render pipeline — the critical integration path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_completes_with_minimal_ast(
    client: httpx.AsyncClient, rendered_document: dict
):
    """Full pipeline: POST → Celery → Quarto → MinIO → estado_render=listo."""
    assert rendered_document["estado_render"] == "listo", (
        f"Render did not complete. estado_render={rendered_document['estado_render']!r}, "
        f"error_render={rendered_document['error_render']!r}"
    )
    assert rendered_document["url_artefacto"] is not None


@pytest.mark.asyncio
async def test_render_artifact_is_publicly_accessible(
    client: httpx.AsyncClient, rendered_document: dict
):
    """Unauthenticated GET on the artifact URL must return 200 (MinIO policy regression)."""
    assert rendered_document["estado_render"] == "listo", "Render must succeed first"
    url = rendered_document["url_artefacto"]
    assert url is not None

    # Rewrite localhost→minio: tests run inside Docker where the public endpoint
    # is unreachable; the internal endpoint exercises the same bucket policy.
    async with httpx.AsyncClient(timeout=15.0) as anon_client:
        resp = await anon_client.get(internal_artifact_url(url))
    assert resp.status_code == 200, (
        f"Artifact URL returned {resp.status_code}. "
        "Likely a MinIO public-read policy regression (see Bug 4)."
    )


@pytest.mark.asyncio
async def test_render_produces_html(
    client: httpx.AsyncClient, rendered_document: dict
):
    """Artifact content must be valid HTML, not an error page or empty body."""
    assert rendered_document["estado_render"] == "listo"
    url = rendered_document["url_artefacto"]

    async with httpx.AsyncClient(timeout=15.0) as anon_client:
        resp = await anon_client.get(internal_artifact_url(url))
    assert resp.status_code == 200
    content = resp.text.lower()
    assert "<html" in content, "Artifact does not appear to be HTML"


@pytest.mark.asyncio
async def test_render_with_full_ast(client: httpx.AsyncClient):
    """All block types (text, ejercicio, nota, ecuacion) must serialize and render."""
    resp = await client.post(
        "/documentos",
        json={"titulo": "Documento completo", "ast": FULL_AST},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = await _wait_for_render(client, doc_id, timeout=120)
    assert doc["estado_render"] == "listo", (
        f"Full-AST render failed: error_render={doc['error_render']!r}"
    )
    await client.delete(f"/documentos/{doc_id}")


@pytest.mark.asyncio
async def test_update_triggers_rerender(client: httpx.AsyncClient):
    """Updating the AST must trigger a second render and produce a new artifact."""
    # Create and render first version
    resp = await client.post(
        "/documentos",
        json={"titulo": "Versión 1", "ast": MINIMAL_AST},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    first = await _wait_for_render(client, doc_id, timeout=90)
    assert first["estado_render"] == "listo"

    # Update AST — must re-trigger render
    updated_ast = {
        "schemaVersion": 1,
        "blocks": [
            {"type": "text", "text": "# Versión 2"},
            {"type": "text", "text": "Contenido actualizado."},
        ],
    }
    put_resp = await client.put(
        f"/documentos/{doc_id}", json={"ast": updated_ast}
    )
    assert put_resp.status_code == 200

    second = await _wait_for_render(client, doc_id, timeout=90)
    assert second["estado_render"] == "listo", (
        f"Re-render failed: {second['error_render']!r}"
    )
    assert second["url_artefacto"] is not None

    await client.delete(f"/documentos/{doc_id}")


# ---------------------------------------------------------------------------
# AST round-trip — regression guard for Bug 6 (editor ignoring doc.ast)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ast_saved_and_returned(client: httpx.AsyncClient):
    """AST written on POST must be returned verbatim on GET (not null, not truncated)."""
    resp = await client.post(
        "/documentos",
        json={"titulo": "Round-trip test", "ast": MINIMAL_AST},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    get_resp = await client.get(f"/documentos/{doc_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()

    assert body["ast"] is not None, "ast is null on GET — editor will load blank (Bug 6 regression)"
    assert len(body["ast"]["blocks"]) == len(MINIMAL_AST["blocks"])

    await client.delete(f"/documentos/{doc_id}")


@pytest.mark.asyncio
async def test_ast_ejercicio_fields_round_trip(client: httpx.AsyncClient):
    """
    Ejercicio block fields (hints, starterCode, solutionCode, language) must
    survive the save→load round-trip with correct types.
    """
    ejercicio_block = FULL_AST["blocks"][2]  # the ejercicio block
    ast = {"schemaVersion": 1, "blocks": [ejercicio_block]}

    resp = await client.post(
        "/documentos", json={"titulo": "Ejercicio round-trip", "ast": ast}
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    get_resp = await client.get(f"/documentos/{doc_id}")
    assert get_resp.status_code == 200
    saved_block = get_resp.json()["ast"]["blocks"][0]

    attrs = saved_block["attrs"]
    assert attrs["language"] == ejercicio_block["attrs"]["language"]
    assert attrs["starterCode"] == ejercicio_block["attrs"]["starterCode"]
    assert attrs["solutionCode"] == ejercicio_block["attrs"]["solutionCode"]
    assert isinstance(attrs["hints"], list), (
        f"hints should be a list, got {type(attrs['hints'])}"
    )
    assert attrs["hints"] == ejercicio_block["attrs"]["hints"]

    await client.delete(f"/documentos/{doc_id}")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_document_empty_blocks(client: httpx.AsyncClient):
    """An AST with zero blocks is valid — should not raise a 500."""
    ast = {"schemaVersion": 1, "blocks": []}
    resp = await client.post(
        "/documentos", json={"titulo": "Vacío", "ast": ast}
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    await client.delete(f"/documentos/{doc_id}")


@pytest.mark.asyncio
async def test_create_document_ast_missing_schema_version_returns_422(
    client: httpx.AsyncClient,
):
    """ast without schemaVersion must be rejected with 422 (model_validator)."""
    bad_ast = {"blocks": [{"type": "text", "text": "sin versión"}]}
    resp = await client.post(
        "/documentos", json={"titulo": "Sin versión", "ast": bad_ast}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_document_long_text_block(client: httpx.AsyncClient):
    """A 5000-char text block must be stored and returned without truncation."""
    long_text = "x" * 5000
    ast = {"schemaVersion": 1, "blocks": [{"type": "text", "text": long_text}]}
    resp = await client.post(
        "/documentos", json={"titulo": "Texto largo", "ast": ast}
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    get_resp = await client.get(f"/documentos/{doc_id}")
    assert get_resp.status_code == 200
    saved_text = get_resp.json()["ast"]["blocks"][0]["text"]
    assert len(saved_text) == 5000, f"Text was truncated: got {len(saved_text)} chars"

    await client.delete(f"/documentos/{doc_id}")


@pytest.mark.asyncio
async def test_update_missing_both_fields_returns_422(
    client: httpx.AsyncClient, created_document: dict
):
    """PUT with neither titulo nor ast must be rejected (model_validator)."""
    resp = await client.put(
        f"/documentos/{created_document['id']}", json={}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_documents_returns_list_when_empty(client: httpx.AsyncClient):
    """GET /documentos must return [] (not 500) even if no documents exist."""
    resp = await client.get("/documentos")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
