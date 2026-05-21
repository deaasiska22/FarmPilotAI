from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.orm import Strategy, StrategyStatus


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_for_project(self, project_id: int) -> list[Strategy]:
        stmt = (
            select(Strategy)
            .where(Strategy.project_id == project_id)
            .order_by(Strategy.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_status(self, strategy_id: int, status: StrategyStatus) -> Strategy | None:
        s = await self.get(strategy_id)
        if s is None:
            return None
        s.status = status
        await self.session.flush()
        return s
