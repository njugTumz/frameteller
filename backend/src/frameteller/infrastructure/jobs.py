"""InProcessJobQueue: asyncio tasks with idempotency keys and status callbacks.

Fine for one container. Jobs are lost on restart, which is acceptable because every job is idempotent and
the client can re-request it; a durable queue can replace this behind JobQueuePort.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from frameteller.application.errors import ApplicationError
from frameteller.application.ports import Job

log = logging.getLogger("frameteller.jobs")

Handler = Callable[[Job], Awaitable[None]]


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


StatusCallback = Callable[[Job, JobStatus, str | None], Awaitable[None]]


class InProcessJobQueue:
    def __init__(
        self, handlers: dict[str, Handler], *, concurrency: int = 3, on_status: StatusCallback | None = None
    ) -> None:
        self._handlers = handlers
        self._slots = asyncio.Semaphore(concurrency)
        self._on_status = on_status
        self._status: dict[str, JobStatus] = {}
        self._messages: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job: Job) -> bool:
        if job.kind not in self._handlers:
            raise ValueError(f"no handler for job kind {job.kind!r}")
        if self._status.get(job.idempotency_key) not in (None, JobStatus.FAILED):
            return False  # queued, running or done: never run twice
        await self._set(job, JobStatus.QUEUED)
        task = asyncio.create_task(self._run(job), name=job.idempotency_key)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def status(self, idempotency_key: str) -> JobStatus | None:
        return self._status.get(idempotency_key)

    def message(self, idempotency_key: str) -> str | None:
        """The user-facing message of a failed job."""
        return self._messages.get(idempotency_key)

    async def join(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def _run(self, job: Job) -> None:
        async with self._slots:
            await self._set(job, JobStatus.RUNNING)
            try:
                await self._handlers[job.kind](job)
            except Exception as exc:
                message = exc.user_message if isinstance(exc, ApplicationError) else "Something went wrong."
                log.exception("job failed", extra={"job_kind": job.kind, "job_key": job.idempotency_key})
                await self._set(job, JobStatus.FAILED, message)
                return
            await self._set(job, JobStatus.SUCCEEDED)

    async def _set(self, job: Job, status: JobStatus, message: str | None = None) -> None:
        self._status[job.idempotency_key] = status
        if message is not None:
            self._messages[job.idempotency_key] = message
        if self._on_status:
            try:
                await self._on_status(job, status, message)
            except Exception:
                log.exception("job status callback failed", extra={"job_key": job.idempotency_key})
