from __future__ import annotations

import pytest

from app.agents.executor import ExecutorAgent
from app.agents.risk import RiskAgent
from app.ai.reasoner import HeuristicReasoner
from app.config import ExecutionSettings
from app.core.humanize import Humanizer
from app.core.retry import RetryPolicy
from app.models.orm import Task, TaskKind, TaskStatus
from app.models.schemas import PlanItem, TaskResult
from app.tasks.handlers.base import TaskHandler


class _OkHandler(TaskHandler):
    kind = TaskKind.FAUCET

    def __init__(self) -> None:
        # bypass the parent ctor – we don't need a browser
        pass

    async def execute(self, *, task: Task, wallet) -> TaskResult:  # noqa: D401
        return TaskResult(ok=True, message="ok")


class _FailHandler(TaskHandler):
    kind = TaskKind.QUEST

    def __init__(self) -> None:
        pass

    async def execute(self, *, task: Task, wallet) -> TaskResult:
        from app.core.exceptions import RetryableError

        raise RetryableError("always fails")


def _make_task(kind: TaskKind) -> Task:
    t = Task(
        id=1,
        strategy_id=1,
        wallet_id=None,
        kind=kind,
        status=TaskStatus.PENDING,
        title="t",
        target_url=None,
        params={},
        attempts=0,
    )
    return t


@pytest.mark.asyncio
async def test_executor_runs_success():
    risk = RiskAgent(ExecutionSettings(EXEC_RISK_MAX_USD=10), HeuristicReasoner())
    exec_agent = ExecutorAgent(
        handlers={TaskKind.FAUCET.value: _OkHandler()},
        risk_agent=risk,
        humanizer=Humanizer(min_ms=1, max_ms=2),
        retry_policy=RetryPolicy(max_attempts=2, base_ms=1, max_ms=2),
    )

    class _W:
        label = "x"
        address = "0x" + "0" * 40

    result = await exec_agent.run(task=_make_task(TaskKind.FAUCET), wallet=_W(), chain="ethereum")
    assert result.ok
    assert ExecutorAgent.status_from_result(result) == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_executor_returns_failed_on_handler_exception():
    risk = RiskAgent(ExecutionSettings(), HeuristicReasoner())
    exec_agent = ExecutorAgent(
        handlers={TaskKind.QUEST.value: _FailHandler()},
        risk_agent=risk,
        humanizer=Humanizer(min_ms=1, max_ms=2),
        retry_policy=RetryPolicy(max_attempts=2, base_ms=1, max_ms=2),
    )

    class _W:
        label = "x"
        address = "0x" + "0" * 40

    result = await exec_agent.run(task=_make_task(TaskKind.QUEST), wallet=_W(), chain="ethereum")
    assert not result.ok
    assert ExecutorAgent.status_from_result(result) == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_risk_blocks_high_notional():
    risk = RiskAgent(ExecutionSettings(EXEC_RISK_MAX_USD=5), HeuristicReasoner())
    item = PlanItem(kind=TaskKind.SWAP, title="big swap", risk_score=0.1)
    decision = await risk.run(
        item,
        wallet_address="0x" + "0" * 40,
        chain="ethereum",
        notional_usd=999,
    )
    assert not decision.approved
    assert "exceeds" in decision.reason.lower()
