from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.deps import ContainerDep
from app.db.repositories.report_repo import ReportRepository
from app.models.schemas import ReportRead
from app.reports.generator import ReportGenerator

router = APIRouter()


@router.get("/strategy/{strategy_id}", response_model=ReportRead)
async def get_report(strategy_id: int, container: ContainerDep) -> ReportRead:
    async with container.db.session() as session:
        repo = ReportRepository(session)
        row = await repo.latest_for_strategy(strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no report for strategy")
    return ReportRead.model_validate(row)


@router.get("/strategy/{strategy_id}/markdown", response_class=PlainTextResponse)
async def get_report_markdown(strategy_id: int, container: ContainerDep) -> str:
    gen = ReportGenerator(container)
    try:
        return await gen.render_markdown(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
