"""PlannerAgent – the strategy designer.

End-to-end pipeline:

1. Validate & normalise project metadata.
2. Ask the :class:`StrategySynthesiser` for a draft list of :class:`PlanItem`s.
3. Annotate every item with a gas estimate via :class:`GasEstimator`.
4. Annotate every item with an expected reward and a calibrated risk score
   via :class:`OpportunityScorer`, and roll the items into a
   :class:`StrategyEvaluation` with a typed ``verdict``.
5. Assemble a :class:`StrategyCreate` payload that captures rationale, plan
   items, and the evaluation in dedicated columns.

The agent is intentionally a *thin coordinator* – every step lives in a
collaborator that can be unit-tested in isolation.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.gas import GasEstimator
from app.agents.opportunity import OpportunityScorer, _Project
from app.ai.strategy import StrategySynthesiser
from app.config import ExecutionSettings
from app.core.exceptions import PlanningError
from app.models.orm import ProjectRiskTier, StrategyStatus
from app.models.orm import StrategyVerdict as StrategyVerdictORM
from app.models.schemas import PlanItem, StrategyCreate, StrategyEvaluation

_VERDICT_ORM = {
    "proceed": StrategyVerdictORM.PROCEED,
    "skip": StrategyVerdictORM.SKIP,
    "needs_review": StrategyVerdictORM.NEEDS_REVIEW,
}


class PlannerAgent(BaseAgent):
    """High-level coordinator – does NOT call out to LLMs or chains itself."""

    name = "planner"

    def __init__(
        self,
        *,
        synthesiser: StrategySynthesiser,
        gas_estimator: GasEstimator,
        opportunity_scorer: OpportunityScorer,
        settings: ExecutionSettings,
    ) -> None:
        super().__init__()
        self.synthesiser = synthesiser
        self.gas = gas_estimator
        self.scorer = opportunity_scorer
        self.settings = settings

    # ------------------------------------------------------------------
    async def run(  # type: ignore[override]
        self,
        *,
        project: dict[str, Any],
        wallet_address: str,
        wallet_liquidity: float,
    ) -> tuple[StrategyCreate, list[PlanItem], StrategyEvaluation]:
        self._validate_project(project)

        rationale, draft_items = await self.synthesiser.design(
            project=project,
            wallet_address=wallet_address,
            wallet_liquidity=wallet_liquidity,
            max_usd=self.settings.risk_max_usd,
            dry_run=self.settings.dry_run,
        )

        chain = str(project.get("chain", "ethereum"))
        gas_annotated = await self.gas.annotate(draft_items, chain=chain)

        scored = self.scorer.annotate_items(gas_annotated, project=_Project.from_dict(project))
        evaluation = self.scorer.evaluate(scored, project=_Project.from_dict(project))

        strategy = StrategyCreate(
            name=f"{project.get('slug', 'project')}-auto",
            project_id=int(project["id"]),
            wallet_id=project.get("wallet_id"),
            status=self._status_for(evaluation),
            rationale=self._compose_rationale(rationale, evaluation),
            plan_json={
                "items": [it.model_dump(mode="json") for it in scored],
                "evaluation": evaluation.model_dump(mode="json"),
            },
            opportunity_score=evaluation.opportunity_score,
            risk_score=evaluation.risk_score,
            estimated_gas_usd=evaluation.estimated_gas_usd,
            expected_reward_usd=evaluation.expected_reward_usd,
            verdict=evaluation.verdict,
        )

        self.log.info(
            "planner.strategy_drafted",
            project=project.get("slug"),
            items=len(scored),
            opportunity=evaluation.opportunity_score,
            risk=evaluation.risk_score,
            gas_usd=evaluation.estimated_gas_usd,
            net_usd=evaluation.expected_net_usd,
            verdict=evaluation.verdict,
        )
        return strategy, scored, evaluation

    # ------------------------------------------------------------------
    @staticmethod
    def _validate_project(project: dict[str, Any]) -> None:
        missing = [k for k in ("id", "slug", "chain") if k not in project]
        if missing:
            raise PlanningError(f"project metadata missing required fields: {missing}")

    @staticmethod
    def _status_for(evaluation: StrategyEvaluation) -> StrategyStatus:
        if evaluation.verdict == "skip":
            return StrategyStatus.ABORTED
        if evaluation.verdict == "needs_review":
            return StrategyStatus.DRAFT
        return StrategyStatus.READY

    @staticmethod
    def _compose_rationale(synth_text: str, evaluation: StrategyEvaluation) -> str:
        parts: list[str] = []
        if synth_text:
            parts.append(synth_text.strip())
        parts.append(
            f"verdict={evaluation.verdict} ({evaluation.reason}); "
            f"opportunity={evaluation.opportunity_score:.2f} "
            f"risk={evaluation.risk_score:.2f} "
            f"net=${evaluation.expected_net_usd:.4f}"
        )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    @staticmethod
    def verdict_orm(value: str) -> StrategyVerdictORM:
        """Translate the schema-level literal into the ORM enum."""
        if value not in _VERDICT_ORM:
            raise PlanningError(f"unknown verdict: {value!r}")
        return _VERDICT_ORM[value]

    # Re-export so callers don't need to import ProjectRiskTier separately
    RiskTier = ProjectRiskTier
