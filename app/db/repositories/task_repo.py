from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.orm import Task, TaskStatus


class TaskRepository(BaseRepository[Task]):
    model = Task

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def pending_for_strategy(self, strategy_id: int) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.strategy_id == strategy_id, Task.status == TaskStatus.PENDING)
            .order_by(Task.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def mark_running(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(tz=UTC)
        task.attempts += 1
        await self.session.flush()
        return task

    async def mark_finished(
        self,
        task: Task,
        *,
        status: TaskStatus,
        result: dict | None = None,
        error: str | None = None,
    ) -> Task:
        task.status = status
        task.finished_at = datetime.now(tz=UTC)
        if result is not None:
            task.result_json = result
        if error is not None:
            task.last_error = error
        await self.session.flush()
        return task
