from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.orm import Project


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_slug(self, slug: str) -> Project | None:
        stmt = select(Project).where(Project.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, project: Project) -> Project:
        existing = await self.get_by_slug(project.slug)
        if existing is None:
            return await self.add(project)
        existing.name = project.name
        existing.url = project.url
        existing.chain = project.chain
        existing.description = project.description
        existing.risk_tier = project.risk_tier
        existing.tags = project.tags
        existing.metadata_json = project.metadata_json
        await self.session.flush()
        return existing
