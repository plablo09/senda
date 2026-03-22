from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, documentos, ejecutar, datasets, retroalimentacion
from api.services.execution_pool import execution_pool
from api.ws import render_status as render_status_ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup: create DB tables
    from api.database import create_tables
    import api.models.ejecucion_error  # noqa: F401 — registers EjecucionError with Base.metadata

    await create_tables()
    await execution_pool.startup()
    yield
    await execution_pool.shutdown()


app = FastAPI(title="Senda API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documentos.router, prefix="/documentos")
app.include_router(ejecutar.router)
app.include_router(datasets.router, prefix="/datasets")
app.include_router(render_status_ws.router)
app.include_router(retroalimentacion.router, prefix="/retroalimentacion")
