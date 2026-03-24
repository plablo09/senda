from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import auth, datasets, documentos, ejecutar, health, retroalimentacion
from api.services.execution_pool import execution_pool
from api.ws import render_status as render_status_ws


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # DB schema is managed by Alembic migrations (run via the migrator service at startup)
    await execution_pool.startup()
    yield
    await execution_pool.shutdown()


app = FastAPI(title="Senda API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(documentos.router, prefix="/documentos")
app.include_router(ejecutar.router)
app.include_router(datasets.router, prefix="/datasets")
app.include_router(render_status_ws.router)
app.include_router(retroalimentacion.router, prefix="/retroalimentacion")
