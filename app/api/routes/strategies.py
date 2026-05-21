from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ExecutionServiceDep, StrategyServiceDep
from app.models.schemas import ReportRead, StrategyRead

router = APIRouter()


class DesignRequest(BaseModel):
    project_slug: str
    wallet_label: str | None = None


@router.post("/design", response_model=StrategyRead)
async def design_strategy(
    payload: DesignRequest, svc: StrategyServiceDep
) -> StrategyRead:
    try:
        return await svc.design_for(
            project_slug=payload.project_slug, wallet_label=payload.wallet_label
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{strategy_id}/run", response_model=ReportRead)
async def run_strategy(strategy_id: int, svc: ExecutionServiceDep) -> ReportRead:
    try:
        return await svc.run(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
