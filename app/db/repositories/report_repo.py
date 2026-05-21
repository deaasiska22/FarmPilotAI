from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.orm import Report


class ReportRepository(BaseRepository[Report]):
    model = Report

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def latest_for_strategy(self, strategy_id: int) -> Report | None:
        stmt = (
            select(Report)
            .where(Report.strategy_id == strategy_id)
            .order_by(Report.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
