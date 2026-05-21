from __future__ import annotations

from app.container import Container
from app.models.schemas import ReportRead


class ExecutionService:
    """Bridges the API layer to :class:`TaskEngine`."""

    def __init__(self, container: Container) -> None:
        self.container = container

    async def run(self, strategy_id: int) -> ReportRead:
        report = await self.container.task_engine.run_strategy(strategy_id)
        return ReportRead.model_validate(report)
