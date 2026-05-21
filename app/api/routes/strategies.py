from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ExecutionServiceDep, StrategyServiceDep
from app.models.schemas import (
    PlanItem,
    ReportRead,
    StrategyEvaluation,
    StrategyRead,
)

router = APIRouter()


class DesignRequest(BaseModel):
    project_slug: str
    wallet_label: str | None = None


class DesignResponse(BaseModel):
    strategy: StrategyRead
    evaluation: StrategyEvaluation
    items: list[PlanItem]


@router.post("/design", response_model=DesignResponse)
async def design_strategy(
    payload: DesignRequest, svc: StrategyServiceDep
) -> DesignResponse:
    try:
        strategy, evaluation = await svc.design_for(
            project_slug=payload.project_slug, wallet_label=payload.wallet_label
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    items = [
        PlanItem.model_validate(it) for it in strategy.plan_json.get("items", [])
    ]
    return DesignResponse(strategy=strategy, evaluation=evaluation, items=items)


@router.post("/{strategy_id}/run", response_model=ReportRead)
async def run_strategy(strategy_id: int, svc: ExecutionServiceDep) -> ReportRead:
    try:
        return await svc.run(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
