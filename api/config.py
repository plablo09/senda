from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379"
    storage_endpoint: str = "http://minio:9000"
    storage_access_key: str = "senda"
    storage_secret_key: str = "senda_dev"
    storage_bucket: str = "senda-documentos"
    llm_model: str = "ollama/llama3.2"
    llm_api_base: str | None = "http://ollama:11434"
    llm_api_key: str | None = None
    secret_key: str = "dev-secret-change-in-production"
    execution_ws_url: str = "ws://localhost:8080/ws/ejecutar"
    exec_python_image: str = "senda-exec-python"
    exec_r_image: str = "senda-exec-r"
    exec_timeout_seconds: int = 30
    container_pool_size_python: int = 2
    container_pool_size_r: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
