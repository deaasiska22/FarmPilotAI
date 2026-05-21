from __future__ import annotations

import pytest

from app.agents.opportunity import OpportunityScorer
from app.config import ExecutionSettings
from app.models.orm import ProjectRiskTier, TaskKind
from app.models.schemas import PlanItem


def _settings(**overrides) -> ExecutionSettings:
    base = {
        "EXEC_HUMAN_DELAY_MIN_MS": 1,
        "EXEC_HUMAN_DELAY_MAX_MS": 2,
        "EXEC_RISK_MAX_USD": 25.0,
        "PLANNER_OPPORTUNITY_THRESHOLD": 0.3,
        "PLANNER_RISK_THRESHOLD": 0.75,
    }
    base.update(overrides)
    return ExecutionSettings(**base)


def _proj(**overrides):
    base = {
        "slug": "proj",
        "chain": "ethereum",
        "risk_tier": ProjectRiskTier.LOW,
        "tags": [],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("kind", list(TaskKind))
def test_calibrated_risk_is_bounded(kind):
    scorer = OpportunityScorer(_settings())
    item = PlanItem(kind=kind, title="x", risk_score=0.9, gas_estimate_usd=15.0)
    annotated = scorer.annotate_items([item], project=_proj(risk_tier="medium"))
    assert 0.0 <= annotated[0].risk_score <= 1.0


def test_signing_actions_carry_extra_risk():
    scorer = OpportunityScorer(_settings())
    faucet = PlanItem(kind=TaskKind.FAUCET, title="f", risk_score=0.1)
    swap = PlanItem(kind=TaskKind.SWAP, title="s", risk_score=0.1, gas_estimate_usd=0.0)
    project = _proj(risk_tier="low")
    [f] = scorer.annotate_items([faucet], project=project)
    [s] = scorer.annotate_items([swap], project=project)
    assert s.risk_score > f.risk_score


def test_empty_plan_yields_skip():
    scorer = OpportunityScorer(_settings())
    evaluation = scorer.evaluate([], project=_proj())
    assert evaluation.verdict == "skip"
    assert evaluation.opportunity_score == 0.0


def test_high_risk_strategy_is_skipped():
    scorer = OpportunityScorer(_settings(PLANNER_RISK_THRESHOLD=0.5))
    items = [
        PlanItem(
            kind=TaskKind.CUSTOM,
            title="risky",
            risk_score=0.95,
            gas_estimate_usd=0.0,
            expected_reward_usd=10.0,
        ),
    ]
    items = scorer.annotate_items(items, project=_proj(risk_tier="high"))
    evaluation = scorer.evaluate(items, project=_proj(risk_tier="high"))
    assert evaluation.verdict == "skip"
    assert "risk" in evaluation.reason.lower()


def test_gas_above_budget_is_skipped():
    scorer = OpportunityScorer(_settings(EXEC_RISK_MAX_USD=2.0))
    items = [
        PlanItem(
            kind=TaskKind.SWAP,
            title="big swap",
            risk_score=0.1,
            gas_estimate_usd=50.0,
            expected_reward_usd=80.0,
        ),
    ]
    evaluation = scorer.evaluate(items, project=_proj())
    assert evaluation.verdict == "skip"
    assert "gas" in evaluation.reason.lower()


def test_proceed_for_profitable_low_risk_plan():
    scorer = OpportunityScorer(_settings())
    items = [
        PlanItem(
            kind=TaskKind.QUEST,
            title="quest",
            risk_score=0.05,
            gas_estimate_usd=0.0,
            # caller-supplied reward override flows via params
            params={"expected_reward_usd": 20.0},
        ),
    ]
    annotated = scorer.annotate_items(items, project=_proj(tags=["airdrop"]))
    evaluation = scorer.evaluate(annotated, project=_proj(tags=["airdrop"]))
    assert evaluation.verdict == "proceed"
    assert evaluation.opportunity_score > 0.0
    assert evaluation.expected_net_usd > 0.0


def test_unknown_chain_inflates_risk():
    scorer = OpportunityScorer(_settings())
    item = PlanItem(kind=TaskKind.QUEST, title="q", risk_score=0.1)
    main = scorer.annotate_items([item], project=_proj(chain="ethereum"))[0]
    weird = scorer.annotate_items([item], project=_proj(chain="weirdnet"))[0]
    assert weird.risk_score > main.risk_score
