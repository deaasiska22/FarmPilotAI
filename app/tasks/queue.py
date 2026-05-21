"""Async, bounded-concurrency task queue.

Each task is dequeued, executed by the :class:`ExecutorAgent`, and recorded
back to the DB.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.logging import get_logger
from app.models.orm import Task

logger = get_logger("tasks.queue")


@dataclass(slots=True)
class QueuedTask:
    task: Task
    fut: asyncio.Future


class TaskQueue:
    """Simple FIFO queue with N-worker fanout."""

    def __init__(self, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._queue: asyncio.Queue[QueuedTask | None] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._max = max_concurrency

    # ------------------------------------------------------------------
    async def start(
        self,
        executor: Callable[[Task], Awaitable[None]],
    ) -> None:
        if self._workers:
            return
        for i in range(self._max):
            self._workers.append(
                asyncio.create_task(self._worker(i, executor), name=f"taskq-worker-{i}")
            )
        logger.info("queue.started", workers=self._max)

    async def stop(self) -> None:
        for _ in self._workers:
            await self._queue.put(None)
        for w in self._workers:
            await w
        self._workers.clear()
        logger.info("queue.stopped")

    # ------------------------------------------------------------------
    async def submit(self, task: Task) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put(QueuedTask(task=task, fut=fut))
        return fut

    # ------------------------------------------------------------------
    async def _worker(self, idx: int, executor: Callable[[Task], Awaitable[None]]) -> None:
        log = logger.bind(worker=idx)
        while True:
            item = await self._queue.get()
            if item is None:
                log.debug("queue.worker_drained")
                return
            try:
                await executor(item.task)
                if not item.fut.done():
                    item.fut.set_result(None)
            except Exception as exc:  # noqa: BLE001
                log.error("queue.worker_error", error=str(exc), task_id=item.task.id)
                if not item.fut.done():
                    item.fut.set_exception(exc)
