"""Strategy synthesis – glues the reasoner output into typed PlanItems."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.ai.prompts import PLANNER_USER_TEMPLATE, SYSTEM_PLANNER
from app.ai.reasoner import BaseReasoner
from app.core.exceptions import StrategyError
from app.core.logging import get_logger
from app.models.schemas import PlanItem

logger = get_logger("ai.strategy")


class StrategySynthesiser:
    def __init__(self, reasoner: BaseReasoner) -> None:
        self.reasoner = reasoner

    async def design(
        self,
        *,
        project: dict[str, Any],
        wallet_address: str,
        wallet_liquidity: float,
        max_usd: float,
        dry_run: bool,
    ) -> tuple[str, list[PlanItem]]:
        user = PLANNER_USER_TEMPLATE.format(
            name=project.get("name", "?"),
            slug=project.get("slug", "?"),
            url=project.get("url", "?"),
            chain=project.get("chain", "?"),
            risk_tier=project.get("risk_tier", "unknown"),
            tags=", ".join(project.get("tags") or []) or "-",
            description=(project.get("description") or "-")[:600],
            wallet_address=wallet_address,
            wallet_liquidity=f"{wallet_liquidity:.4f}",
            max_usd=f"{max_usd:.2f}",
            dry_run=dry_run,
        )
        raw = await self.reasoner.generate_json(system=SYSTEM_PLANNER, user=user)
        items_raw = raw.get("items", [])
        items: list[PlanItem] = []
        for entry in items_raw:
            try:
                items.append(PlanItem.model_validate(entry))
            except ValidationError as exc:
                logger.warning("strategy.invalid_item", error=str(exc), entry=entry)
        if not items:
            raise StrategyError("reasoner returned no valid plan items")
        return raw.get("rationale", ""), items
