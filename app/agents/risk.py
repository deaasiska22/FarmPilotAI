"""Pre-transaction risk gate.

The risk agent enforces hard, dumb rules first (budget, dry-run), then
optionally consults the LLM for a softer signal. Hard rules always win.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base import BaseAgent
from app.ai.prompts import SYSTEM_RISK
from app.ai.reasoner import BaseReasoner
from app.config import ExecutionSettings
from app.core.exceptions import RiskRejectedError
from app.models.schemas import PlanItem


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    risk_score: float
    reason: str


class RiskAgent(BaseAgent):
    name = "risk"

    def __init__(self, settings: ExecutionSettings, reasoner: BaseReasoner) -> None:
        super().__init__()
        self.settings = settings
        self.reasoner = reasoner

    async def run(
        self,
        plan_item: PlanItem,
        *,
        wallet_address: str,
        chain: str,
        notional_usd: float = 0.0,
        context: dict[str, Any] | None = None,
    ) -> RiskDecision:  # type: ignore[override]
        # ---- Hard rules ---------------------------------------------------
        if notional_usd > self.settings.risk_max_usd:
            return RiskDecision(
                approved=False,
                risk_score=1.0,
                reason=(
                    f"notional {notional_usd:.2f} exceeds "
                    f"budget {self.settings.risk_max_usd:.2f}"
                ),
            )
        if plan_item.risk_score >= 0.85:
            return RiskDecision(
                approved=False, risk_score=plan_item.risk_score, reason="planner flagged high risk"
            )

        # ---- Soft, LLM-assisted check ------------------------------------
        prompt = (
            f"Action: {plan_item.kind} – {plan_item.title}\n"
            f"Chain: {chain}\nWallet: {wallet_address}\n"
            f"Notional (USD): {notional_usd}\nDry run: {self.settings.dry_run}\n"
            f"Params: {plan_item.params}\nRationale: {plan_item.rationale or '-'}"
        )
        try:
            verdict = await self.reasoner.generate_json(system=SYSTEM_RISK, user=prompt)
        except Exception as exc:
            # Fail-closed for unknown errors so we never bypass on outages.
            self.log.warning("risk.reasoner_failure", error=str(exc))
            return RiskDecision(
                approved=False,
                risk_score=1.0,
                reason="risk reasoner unavailable – failing closed",
            )

        return RiskDecision(
            approved=bool(verdict.get("approved", False)),
            risk_score=float(verdict.get("risk_score", plan_item.risk_score or 0.5)),
            reason=str(verdict.get("reason", "ok")),
        )

    async def guard(self, *args: Any, **kwargs: Any) -> RiskDecision:
        """Like :meth:`run` but raises :class:`RiskRejectedError` if denied."""
        d = await self.run(*args, **kwargs)
        if not d.approved:
            raise RiskRejectedError(d.reason)
        return d
