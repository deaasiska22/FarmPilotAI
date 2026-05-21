from __future__ import annotations

import pytest

from app.agents.gas import GasEstimator
from app.agents.opportunity import OpportunityScorer
from app.agents.planner import PlannerAgent
from app.ai.reasoner import HeuristicReasoner
from app.ai.strategy import StrategySynthesiser
from app.config import ExecutionSettings


def _settings(**overrides) -> ExecutionSettings:
    base = {
        "EXEC_HUMAN_DELAY_MIN_MS": 1,
        "EXEC_HUMAN_DELAY_MAX_MS": 2,
        "EXEC_RISK_MAX_USD": 25.0,
        "PLANNER_OPPORTUNITY_THRESHOLD": 0.0,
        "PLANNER_RISK_THRESHOLD": 0.95,
    }
    base.update(overrides)
    return ExecutionSettings(**base)


def _planner(settings: ExecutionSettings | None = None) -> PlannerAgent:
    settings = settings or _settings()
    return PlannerAgent(
        synthesiser=StrategySynthesiser(HeuristicReasoner()),
        gas_estimator=GasEstimator(settings, evm_registry=None),
        opportunity_scorer=OpportunityScorer(settings),
        settings=settings,
    )


_PROJECT = {
    "id": 1,
    "slug": "sample",
    "name": "Sample",
    "url": "https://sample.example",
    "chain": "ethereum",
    "risk_tier": "low",
    "tags": ["faucet", "airdrop"],
    "description": "Demo",
}


@pytest.mark.asyncio
async def test_planner_outputs_strategy_with_evaluation_columns():
    strategy, items, evaluation = await _planner().run(
        project=_PROJECT, wallet_address="0x" + "1" * 40, wallet_liquidity=0.0
    )
    assert items, "planner should return at least one task"
    assert strategy.opportunity_score == evaluation.opportunity_score
    assert strategy.risk_score == evaluation.risk_score
    assert strategy.estimated_gas_usd == evaluation.estimated_gas_usd
    assert strategy.expected_reward_usd == evaluation.expected_reward_usd
    assert strategy.verdict == evaluation.verdict


@pytest.mark.asyncio
async def test_planner_attaches_gas_estimate_per_item():
    _, items, _ = await _planner().run(
        project=_PROJECT, wallet_address="0x" + "1" * 40, wallet_liquidity=0.0
    )
    # All heuristic items are off-chain → zero gas; risk_score should be bounded.
    for it in items:
        assert it.gas_estimate_usd >= 0.0
        assert 0.0 <= it.risk_score <= 1.0
        assert it.expected_reward_usd >= 0.0


@pytest.mark.asyncio
async def test_planner_proceeds_for_low_risk_project():
    _, _, evaluation = await _planner().run(
        project=_PROJECT, wallet_address="0x" + "1" * 40, wallet_liquidity=0.0
    )
    # Heuristic plan: zero-gas faucet/quest/checkin on a low-risk project
    # tagged 'airdrop' should comfortably clear the proceed threshold.
    assert evaluation.verdict == "proceed"
    assert evaluation.expected_net_usd > 0.0
    assert evaluation.estimated_gas_usd == 0.0


@pytest.mark.asyncio
async def test_planner_skips_when_gas_dwarfs_budget():
    # Tiny budget vs. an explicit gas-heavy item gets rejected.
    settings = _settings(EXEC_RISK_MAX_USD=0.5, PLANNER_DEFAULT_GAS_GWEI=100.0)
    planner = _planner(settings)

    class _OnlySwap:
        async def design(self, **kwargs):
            from app.models.orm import TaskKind
            from app.models.schemas import PlanItem
            return "swap-only", [
                PlanItem(
                    kind=TaskKind.SWAP, title="swap", risk_score=0.05,
                    expected_reward_usd=1.0,
                )
            ]

    planner.synthesiser = _OnlySwap()
    _, _, evaluation = await planner.run(
        project=_PROJECT, wallet_address="0x" + "1" * 40, wallet_liquidity=0.0
    )
    assert evaluation.verdict == "skip"
    assert evaluation.estimated_gas_usd > 0.0


@pytest.mark.asyncio
async def test_planner_rejects_incomplete_project_metadata():
    from app.core.exceptions import PlanningError

    with pytest.raises(PlanningError):
        await _planner().run(
            project={"slug": "missing-id"},
            wallet_address="0x" + "1" * 40,
            wallet_liquidity=0.0,
        )
