from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal
import docker
from api.config import settings

logger = logging.getLogger(__name__)

@dataclass
class OutputChunk:
    tipo: Literal["stdout", "stderr", "imagen", "error", "fin"]
    contenido: str

@dataclass
class ContainerPool:
    language: str
    image: str
    size: int
    _available: list = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def initialize(self, docker_client: docker.DockerClient):
        """Reuse existing running containers with matching labels, then start new ones to fill the pool."""
        async with self._lock:
            # Check for already-running containers (e.g. started by docker-compose)
            existing = await asyncio.to_thread(
                docker_client.containers.list,
                filters={"label": [f"senda.exec=true", f"senda.language={self.language}"], "status": "running"},
            )
            for container in existing:
                self._available.append(container.id)
                logger.info(
                    "Reusing existing container %s for %s", container.id[:12], self.language
                )

            # Start additional containers if we have fewer than `size`
            needed = self.size - len(self._available)
            for _ in range(needed):
                container = await asyncio.to_thread(
                    docker_client.containers.run,
                    self.image,
                    command="sleep infinity",
                    detach=True,
                    labels={"senda.exec": "true", "senda.language": self.language},
                    mem_limit="512m",
                    cpu_quota=50000,  # 50% of one CPU
                    network_mode="none",  # no network access for execution containers
                    read_only=False,  # need /tmp write access
                    tmpfs={"/tmp": "size=100m"},
                )
                self._available.append(container.id)
                logger.info("Pre-warmed container %s for %s", container.id[:12], self.language)

    async def acquire(self) -> str:
        """Get an available container ID. Waits up to 60s if pool is exhausted."""
        for _ in range(60):
            async with self._lock:
                if self._available:
                    return self._available.pop(0)
            await asyncio.sleep(1)
        raise TimeoutError("No hay contenedores de ejecución disponibles. Intenta de nuevo.")

    async def release(self, container_id: str) -> None:
        """Return a container to the pool (it will be reused as-is)."""
        async with self._lock:
            self._available.append(container_id)


class ExecutionPool:
    """Manages Python and R container pools and routes execution requests."""

    def __init__(self):
        self._docker = docker.from_env()
        self._pools: dict[str, ContainerPool] = {}

    async def startup(self):
        self._pools["python"] = ContainerPool(
            language="python",
            image=settings.exec_python_image,
            size=settings.container_pool_size_python,
        )
        self._pools["r"] = ContainerPool(
            language="r",
            image=settings.exec_r_image,
            size=settings.container_pool_size_r,
        )
        for pool in self._pools.values():
            await pool.initialize(self._docker)
        logger.info("Execution pool ready")

    async def shutdown(self):
        pass

    async def execute(
        self, language: str, code: str
    ) -> AsyncIterator[OutputChunk]:
        """
        Acquire a container, run the code, stream output chunks.
        Always releases the container back to the pool when done.
        """
        pool = self._pools.get(language)
        if not pool:
            yield OutputChunk(tipo="error", contenido=f"Lenguaje no soportado: {language}")
            return

        container_id = await pool.acquire()
        try:
            async for chunk in self._run_in_container(container_id, language, code):
                yield chunk
        finally:
            await pool.release(container_id)

    async def _run_in_container(
        self, container_id: str, language: str, code: str
    ) -> AsyncIterator[OutputChunk]:
        """Run code inside container via docker exec, stream output."""
        container = await asyncio.to_thread(
            self._docker.containers.get, container_id
        )

        # Write code to a temp file inside the container, then execute
        if language == "python":
            exec_cmd = ["python3", "-c", code]
        else:
            exec_cmd = ["Rscript", "-e", code]

        try:
            exec_id = await asyncio.to_thread(
                container.exec_run,
                exec_cmd,
                stream=True,
                demux=True,
                environment={"MPLBACKEND": "Agg"},  # non-interactive matplotlib backend
            )
            # exec_run with stream=True returns (exit_code, generator)
            _, stream = exec_id

            async def read_stream():
                for stdout_chunk, stderr_chunk in await asyncio.to_thread(list, stream):
                    if stdout_chunk:
                        yield OutputChunk(tipo="stdout", contenido=stdout_chunk.decode("utf-8", errors="replace"))
                    if stderr_chunk:
                        yield OutputChunk(tipo="stderr", contenido=stderr_chunk.decode("utf-8", errors="replace"))

            async for chunk in read_stream():
                yield chunk

            yield OutputChunk(tipo="fin", contenido="")

        except Exception as exc:
            yield OutputChunk(tipo="error", contenido=str(exc))


# Singleton — initialized at app startup
execution_pool = ExecutionPool()
