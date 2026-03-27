from __future__ import annotations

from importlib.metadata import version, PackageNotFoundError
from fastapi import APIRouter

router = APIRouter(tags=["health"])


def _get_version() -> str:
    try:
        return version("senda-api")
    except PackageNotFoundError:
        return "unknown"


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"estado": "ok", "version": _get_version()}
