"""PlannerAgent – generates a strategy for a (project, wallet) pair."""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.ai.strategy import StrategySynthesiser
from app.config import ExecutionSettings
from app.models.orm import StrategyStatus
from app.models.schemas import PlanItem, StrategyCreate


class PlannerAgent(BaseAgent):
    name = "planner"

    def __init__(
        self, synthesiser: StrategySynthesiser, settings: ExecutionSettings
    ) -> None:
        super().__init__()
        self.synthesiser = synthesiser
        self.settings = settings

    async def run(  # type: ignore[override]
        self,
        *,
        project: dict[str, Any],
        wallet_address: str,
        wallet_liquidity: float,
    ) -> tuple[StrategyCreate, list[PlanItem]]:
        rationale, items = await self.synthesiser.design(
            project=project,
            wallet_address=wallet_address,
            wallet_liquidity=wallet_liquidity,
            max_usd=self.settings.risk_max_usd,
            dry_run=self.settings.dry_run,
        )
        strategy = StrategyCreate(
            name=f"{project.get('slug', 'project')}-auto",
            project_id=project["id"],
            wallet_id=project.get("wallet_id"),
            status=StrategyStatus.READY,
            rationale=rationale,
            plan_json={"items": [i.model_dump(mode="json") for i in items]},
        )
        self.log.info(
            "planner.strategy_drafted",
            project=project.get("slug"),
            items=len(items),
        )
        return strategy, items
