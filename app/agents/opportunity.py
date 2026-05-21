"""Opportunity / risk scorer.

Once the planner has a draft list of :class:`PlanItem`s with gas estimates,
this scorer:

1. Estimates **expected reward** per item (heuristics keyed by ``TaskKind``
   plus tag-based modifiers).
2. Computes an **aggregate opportunity score** in ``[0, 1]`` reflecting both
   net dollar expectation and the project's risk tier.
3. Calibrates each item's **risk score** with the planner's own signals
   (gas burn vs budget, chain trust, project risk tier).
4. Emits a :class:`StrategyEvaluation` with a typed ``verdict`` so the
   service layer can decide whether to execute, defer, or skip.

Heuristics are intentionally explicit and tunable; an LLM-only scorer
hallucinates rewards on novel protocols. We use the LLM only to bias the
final score, never to replace these numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import ExecutionSettings
from app.core.logging import get_logger
from app.models.orm import ProjectRiskTier, TaskKind
from app.models.schemas import PlanItem, StrategyEvaluation, StrategyVerdict

logger = get_logger("agent.opportunity")


# ---------------------------------------------------------------------------
# Static reward heuristics (USD). These are intentionally conservative.
# ---------------------------------------------------------------------------
_BASE_REWARD_USD: dict[TaskKind, float] = {
    TaskKind.FAUCET: 0.50,     # testnet drips have ~negligible $ value
    TaskKind.QUEST: 1.25,      # social / Galxe-style reputation farm
    TaskKind.CHECKIN: 0.20,    # daily check-in points
    TaskKind.SWAP: 0.00,       # no direct reward; airdrop expectation only
    TaskKind.BRIDGE: 0.00,
    TaskKind.CUSTOM: 0.50,
}

_TAG_REWARD_MULTIPLIER: dict[str, float] = {
    "airdrop": 3.0,
    "points": 1.5,
    "incentivised": 2.0,
    "season": 1.5,
}

_RISK_TIER_WEIGHT: dict[ProjectRiskTier, float] = {
    ProjectRiskTier.LOW: 0.10,
    ProjectRiskTier.MEDIUM: 0.30,
    ProjectRiskTier.HIGH: 0.65,
    ProjectRiskTier.UNKNOWN: 0.45,
}


@dataclass(slots=True)
class _Project:
    """Minimal projection of project metadata needed by the scorer."""

    slug: str
    chain: str
    risk_tier: ProjectRiskTier
    tags: list[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> _Project:
        tier_raw = raw.get("risk_tier", "unknown")
        if isinstance(tier_raw, ProjectRiskTier):
            tier = tier_raw
        else:
            try:
                tier = ProjectRiskTier(str(tier_raw))
            except ValueError:
                tier = ProjectRiskTier.UNKNOWN
        return cls(
            slug=str(raw.get("slug", "?")),
            chain=str(raw.get("chain", "ethereum")).lower(),
            risk_tier=tier,
            tags=[str(t).lower() for t in (raw.get("tags") or [])],
        )


class OpportunityScorer:
    """Evaluates whether a draft plan is worth executing."""

    def __init__(self, settings: ExecutionSettings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Reward
    # ------------------------------------------------------------------
    def _expected_reward(self, item: PlanItem, project: _Project) -> float:
        # explicit override wins
        explicit = item.params.get("expected_reward_usd") if item.params else None
        if isinstance(explicit, int | float) and explicit >= 0:
            return float(explicit)

        base = _BASE_REWARD_USD.get(item.kind, 0.5)
        multiplier = 1.0
        for tag in project.tags:
            multiplier *= _TAG_REWARD_MULTIPLIER.get(tag, 1.0)
        # Quests / faucets earn proportionally less on already-saturated chains.
        if project.chain in ("ethereum", "arbitrum") and item.kind in (
            TaskKind.FAUCET,
            TaskKind.QUEST,
        ):
            multiplier *= 0.5
        return round(base * multiplier, 4)

    # ------------------------------------------------------------------
    # Risk calibration
    # ------------------------------------------------------------------
    def _calibrated_risk(
        self, item: PlanItem, project: _Project, gas_usd: float, budget_usd: float
    ) -> float:
        # Start from whatever the reasoner emitted.
        score = float(item.risk_score or 0.0)
        # Add project-tier weight.
        score = min(1.0, score + _RISK_TIER_WEIGHT[project.risk_tier])
        # Signing actions are inherently riskier than off-chain ones.
        if item.kind in (TaskKind.SWAP, TaskKind.BRIDGE, TaskKind.CUSTOM):
            score = min(1.0, score + 0.15)
        # Gas burn close to the budget => high risk.
        if budget_usd > 0 and gas_usd / budget_usd > 0.5:
            score = min(1.0, score + 0.15)
        # Unknown / no-RPC chains are higher risk.
        if project.chain not in (
            "ethereum",
            "arbitrum",
            "base",
            "optimism",
            "polygon",
        ):
            score = min(1.0, score + 0.10)
        return round(score, 4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def annotate_items(
        self,
        items: list[PlanItem],
        project: dict[str, Any] | _Project,
    ) -> list[PlanItem]:
        proj = project if isinstance(project, _Project) else _Project.from_dict(project)
        budget = self.settings.risk_max_usd
        out: list[PlanItem] = []
        for item in items:
            reward = self._expected_reward(item, proj)
            risk = self._calibrated_risk(item, proj, item.gas_estimate_usd, budget)
            out.append(
                item.model_copy(
                    update={"expected_reward_usd": reward, "risk_score": risk}
                )
            )
        return out

    def evaluate(
        self,
        items: list[PlanItem],
        project: dict[str, Any] | _Project,
    ) -> StrategyEvaluation:
        """Roll annotated items into a strategy-level verdict."""
        proj = project if isinstance(project, _Project) else _Project.from_dict(project)
        if not items:
            return StrategyEvaluation(
                opportunity_score=0.0,
                risk_score=0.0,
                estimated_gas_usd=0.0,
                expected_reward_usd=0.0,
                expected_net_usd=0.0,
                verdict="skip",
                reason="planner returned no actionable items",
            )

        total_gas = round(sum(i.gas_estimate_usd for i in items), 4)
        total_reward = round(sum(i.expected_reward_usd for i in items), 4)
        net = round(total_reward - total_gas, 4)
        max_item_risk = max(i.risk_score for i in items)
        avg_item_risk = sum(i.risk_score for i in items) / len(items)
        # Worst-case dominates, but the average pulls it back when most steps
        # are safe – avoids one risky checkin tanking the whole plan.
        strategy_risk = round(0.7 * max_item_risk + 0.3 * avg_item_risk, 4)

        # Opportunity score: net dollars normalised to the budget, plus a
        # risk-tier penalty so unknown projects can't outrank trusted ones.
        budget = max(self.settings.risk_max_usd, 1.0)
        normalised_net = max(0.0, min(net / budget, 1.0))
        tier_penalty = _RISK_TIER_WEIGHT[proj.risk_tier]
        opportunity = round(max(0.0, normalised_net * (1.0 - tier_penalty)), 4)

        # Verdict
        verdict: StrategyVerdict
        reason: str
        if total_gas > budget:
            verdict, reason = "skip", (
                f"estimated gas ${total_gas:.4f} exceeds budget ${budget:.2f}"
            )
        elif strategy_risk >= self.settings.risk_threshold:
            verdict, reason = "skip", (
                f"strategy risk {strategy_risk:.2f} >= threshold {self.settings.risk_threshold:.2f}"
            )
        elif net <= 0 and total_gas > 0:
            verdict, reason = "skip", (
                f"expected net ${net:.4f} <= 0 with non-zero gas cost"
            )
        elif opportunity < self.settings.opportunity_threshold:
            verdict, reason = "needs_review", (
                f"opportunity {opportunity:.2f} below threshold "
                f"{self.settings.opportunity_threshold:.2f}"
            )
        else:
            verdict, reason = "proceed", "plan is within budget and risk envelope"

        logger.info(
            "opportunity.evaluated",
            project=proj.slug,
            items=len(items),
            net_usd=net,
            opportunity=opportunity,
            risk=strategy_risk,
            verdict=verdict,
        )

        return StrategyEvaluation(
            opportunity_score=opportunity,
            risk_score=strategy_risk,
            estimated_gas_usd=total_gas,
            expected_reward_usd=total_reward,
            expected_net_usd=net,
            verdict=verdict,
            reason=reason,
        )
