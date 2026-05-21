from __future__ import annotations

from collections.abc import Iterable

from app.agents.scanner import ScannerAgent
from app.container import Container
from app.db.repositories.project_repo import ProjectRepository
from app.models.orm import Project
from app.models.schemas import ProjectCreate, ProjectRead


class ProjectService:
    def __init__(self, container: Container) -> None:
        self.container = container
        self.scanner = ScannerAgent(container.ai_reasoner)

    async def scan(self, urls: Iterable[str]) -> list[ProjectRead]:
        creates = await self.scanner.run(urls)
        async with self.container.db.session() as session:
            repo = ProjectRepository(session)
            out: list[Project] = []
            for c in creates:
                orm = Project(**c.model_dump())
                out.append(await repo.upsert(orm))
        return [ProjectRead.model_validate(p) for p in out]

    async def list_projects(self) -> list[ProjectRead]:
        async with self.container.db.session() as session:
            repo = ProjectRepository(session)
            rows = await repo.list(limit=200)
        return [ProjectRead.model_validate(p) for p in rows]

    async def create(self, project: ProjectCreate) -> ProjectRead:
        async with self.container.db.session() as session:
            repo = ProjectRepository(session)
            orm = Project(**project.model_dump())
            saved = await repo.upsert(orm)
        return ProjectRead.model_validate(saved)
