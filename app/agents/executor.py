"""ExecutorAgent – runs one PlanItem end-to-end.

This is intentionally a *thin* coordinator: it does not know how to faucet,
swap, or quest. It dispatches to a registered :class:`TaskHandler`, wraps the
call in retry, applies humanizer delays, and updates the Task row.
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING

from app.agents.base import BaseAgent
from app.agents.risk import RiskAgent
from app.core.exceptions import RiskRejectedError
from app.core.humanize import Humanizer
from app.core.retry import RetryPolicy, with_retry
from app.models.orm import Task, TaskStatus
from app.models.schemas import TaskResult
from app.wallet.connector import WalletConnector

if TYPE_CHECKING:  # pragma: no cover
    from app.tasks.handlers.base import TaskHandler


class ExecutorAgent(BaseAgent):
    name = "executor"

    def __init__(
        self,
        *,
        handlers: dict[str, TaskHandler],
        risk_agent: RiskAgent,
        humanizer: Humanizer,
        retry_policy: RetryPolicy,
    ) -> None:
        super().__init__()
        self.handlers = handlers
        self.risk_agent = risk_agent
        self.humanizer = humanizer
        self.retry_policy = retry_policy

    # ------------------------------------------------------------------
    async def run(  # type: ignore[override]
        self,
        *,
        task: Task,
        wallet: WalletConnector,
        chain: str,
    ) -> TaskResult:
        handler = self.handlers.get(task.kind.value)
        if handler is None:
            return TaskResult(ok=False, message=f"no handler for kind {task.kind.value}")

        log = self.log.bind(task_id=task.id, kind=task.kind.value, title=task.title)
        log.info("executor.task_starting")

        # ---- risk gate (cheap; runs even for read-only kinds) ----
        plan_item = handler.to_plan_item(task)
        try:
            await self.risk_agent.guard(
                plan_item,
                wallet_address=wallet.address,
                chain=chain,
                notional_usd=float(task.params.get("notional_usd", 0)),
            )
        except RiskRejectedError as exc:
            log.warning("executor.task_blocked_by_risk", reason=str(exc))
            return TaskResult(ok=False, message=f"risk blocked: {exc}")

        # ---- humanise + execute via retry policy ----
        await self.humanizer.sleep()
        bound = partial(handler.execute, task=task, wallet=wallet)
        try:
            result = await with_retry(bound, policy=self.retry_policy, op_name=task.kind.value)
        except Exception as exc:
            log.error("executor.task_failed", error=str(exc))
            return TaskResult(ok=False, message=f"{type(exc).__name__}: {exc}")

        result.data.setdefault("finished_at", datetime.now(tz=UTC).isoformat())
        log.info("executor.task_completed", ok=result.ok)
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def status_from_result(result: TaskResult) -> TaskStatus:
        if result.ok:
            return TaskStatus.SUCCEEDED
        if result.message.startswith("risk blocked"):
            return TaskStatus.BLOCKED_BY_RISK
        return TaskStatus.FAILED
