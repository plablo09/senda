from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator
import docker
from api.config import settings

logger = logging.getLogger(__name__)

@dataclass
class OutputChunk:
    tipo: str  # "stdout" | "stderr" | "imagen" | "error" | "fin"
    contenido: str

@dataclass
class ContainerPool:
    language: str
    image: str
    size: int
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    async def initialize(self, docker_client: docker.DockerClient):
        """Reuse existing running containers with matching labels, then start new ones to fill the pool."""
        existing = await asyncio.to_thread(
            docker_client.containers.list,
            filters={"label": [f"senda.exec=true", f"senda.language={self.language}"], "status": "running"},
        )
        for container in existing:
            await self._queue.put(container.id)
            logger.info("Reusing existing container %s for %s", container.id[:12], self.language)

        needed = self.size - self._queue.qsize()
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
            await self._queue.put(container.id)
            logger.info("Pre-warmed container %s for %s", container.id[:12], self.language)

    async def acquire(self) -> str:
        """Get an available container ID. Wakes immediately on release; waits up to 60s if pool exhausted."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            raise TimeoutError("No hay contenedores de ejecución disponibles. Intenta de nuevo.")

    async def release(self, container_id: str) -> None:
        """Return a container to the pool; waiters are notified immediately."""
        await self._queue.put(container_id)


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
            await self._cleanup_container(container_id)
            await pool.release(container_id)

    async def _cleanup_container(self, container_id: str) -> None:
        """Wipe /tmp and /workspace before returning the container to the pool."""
        try:
            container = await asyncio.to_thread(self._docker.containers.get, container_id)
            await asyncio.to_thread(
                container.exec_run,
                ["sh", "-c", "rm -rf /tmp/* /workspace/*"],
                user="root",
            )
        except Exception:
            logger.warning("Cleanup failed for container %s; it will be retired", container_id[:12])

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
            _, stream = await asyncio.to_thread(
                container.exec_run,
                exec_cmd,
                stream=True,
                demux=True,
                environment={"MPLBACKEND": "Agg"},  # non-interactive matplotlib backend
            )

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[OutputChunk | None] = asyncio.Queue()

            def _read():
                try:
                    for stdout_chunk, stderr_chunk in stream:
                        if stdout_chunk:
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                OutputChunk(
                                    tipo="stdout",
                                    contenido=stdout_chunk.decode("utf-8", errors="replace"),
                                ),
                            )
                        if stderr_chunk:
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                OutputChunk(
                                    tipo="stderr",
                                    contenido=stderr_chunk.decode("utf-8", errors="replace"),
                                ),
                            )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            read_task = asyncio.create_task(asyncio.to_thread(_read))
            try:
                while True:
                    chunk = await asyncio.wait_for(
                        queue.get(), timeout=settings.exec_timeout_seconds
                    )
                    if chunk is None:
                        break
                    yield chunk
            except asyncio.TimeoutError:
                yield OutputChunk(tipo="error", contenido="Tiempo de ejecución excedido.")
                return
            finally:
                read_task.cancel()

            yield OutputChunk(tipo="fin", contenido="")

        except Exception as exc:
            yield OutputChunk(tipo="error", contenido=str(exc))


# Singleton — initialized at app startup
execution_pool = ExecutionPool()
