from __future__ import annotations

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Synchronous DB URL for Alembic (psycopg2 instead of asyncpg)."""
        if "+asyncpg" not in self.database_url:
            raise ValueError(
                f"DATABASE_URL must use the +asyncpg scheme; got: {self.database_url!r}"
            )
        return self.database_url.replace("+asyncpg", "+psycopg2")
    redis_url: str = "redis://redis:6379"
    storage_endpoint: str = "http://minio:9000"
    storage_public_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "senda"
    storage_secret_key: str = "senda_dev"
    storage_bucket: str = "senda-documentos"
    llm_model: str = "gemini/gemini-2.0-flash"
    llm_api_base: str | None = None
    llm_api_key: str | None = None
    feedback_silence_window: int = 2
    feedback_max_responses: int = 3
    secret_key: str = "dev-secret-change-in-production"
    execution_ws_url: str = "ws://localhost:8080/ws/ejecutar"
    exec_python_image: str = "senda-exec-python"
    exec_r_image: str = "senda-exec-r"
    exec_timeout_seconds: int = 30
    container_pool_size_python: int = 2
    container_pool_size_r: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

DATASET_ACCEPTED_MIMETYPES: set[str] = {
    "text/csv",
    "application/geo+json",
    "application/zip",
    "application/geopackage+sqlite3",
}
DATASET_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
