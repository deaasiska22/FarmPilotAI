from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import ContainerDep
from app.db.repositories.task_repo import TaskRepository
from app.models.schemas import TaskRead

router = APIRouter()


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, container: ContainerDep) -> TaskRead:
    async with container.db.session() as session:
        repo = TaskRepository(session)
        row = await repo.get(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskRead.model_validate(row)
