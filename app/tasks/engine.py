"""Task execution engine.

This is the single integration point between the agents, the handlers, the
DB, and the wallet/browser layers.

Construction order is:

   Container -> TaskEngine -> ExecutorAgent + HandlerRegistry + RiskAgent

So when a service layer wants to run a strategy, it just calls
``container.task_engine.run_strategy(strategy_id)``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.executor import ExecutorAgent
from app.agents.risk import RiskAgent
from app.ai.strategy import StrategySynthesiser
from app.core.exceptions import ChainConnectionError
from app.core.logging import get_logger
from app.db.repositories.report_repo import ReportRepository
from app.db.repositories.strategy_repo import StrategyRepository
from app.db.repositories.task_repo import TaskRepository
from app.db.repositories.wallet_repo import WalletRepository
from app.models.orm import (
    Report,
    StrategyStatus,
    Task,
    TaskStatus,
)
from app.tasks.handlers import default_registry
from app.tasks.queue import TaskQueue
from app.wallet.connector import WalletConnector
from app.wallet.evm import EVMRegistry

if TYPE_CHECKING:  # pragma: no cover
    from app.container import Container


logger = get_logger("tasks.engine")


class TaskEngine:
    """Top-level orchestrator. One per process."""

    def __init__(self, container: Container) -> None:
        self.container = container

        humanizer = container.humanizer
        retry_policy = container.retry_policy

        self.registry = default_registry(container.browser_manager, humanizer)
        self.risk_agent = RiskAgent(container.settings.execution, container.ai_reasoner)
        self.executor = ExecutorAgent(
            handlers=self.registry.asdict(),
            risk_agent=self.risk_agent,
            humanizer=humanizer,
            retry_policy=retry_policy,
        )
        self.synthesiser = StrategySynthesiser(container.ai_reasoner)
        self.evm_registry = EVMRegistry(container.settings.wallet.evm_rpcs)
        self.queue = TaskQueue(max_concurrency=container.settings.execution.max_concurrency)

    # ------------------------------------------------------------------
    async def start(self) -> None:
        await self.queue.start(self._execute_single)

    async def aclose(self) -> None:
        await self.queue.stop()

    # ------------------------------------------------------------------
    async def submit_task(self, task: Task) -> None:
        await self.queue.submit(task)

    async def run_strategy(self, strategy_id: int) -> Report:
        """Drain all PENDING tasks for ``strategy_id`` and write a report row."""
        async with self.container.db.session() as session:
            strategy_repo = StrategyRepository(session)
            task_repo = TaskRepository(session)
            report_repo = ReportRepository(session)

            strategy = await strategy_repo.get(strategy_id)
            if strategy is None:
                raise ValueError(f"unknown strategy id {strategy_id}")

            tasks = await task_repo.pending_for_strategy(strategy_id)
            await strategy_repo.set_status(strategy_id, StrategyStatus.RUNNING)

        # Drive the queue in-band; one strategy at a time keeps reasoning simple.
        await self.start()
        futs = [await self.queue.submit(t) for t in tasks]
        for fut in futs:
            try:
                await fut
            except Exception as exc:
                logger.warning("engine.task_future_error", error=str(exc))

        # Reload completed tasks for accurate counts.
        async with self.container.db.session() as session:
            task_repo = TaskRepository(session)
            strategy_repo = StrategyRepository(session)
            report_repo = ReportRepository(session)
            refreshed: list[Task] = []
            for t in tasks:
                refreshed.append(await task_repo.get(t.id) or t)

            succeeded = sum(1 for t in refreshed if t.status == TaskStatus.SUCCEEDED)
            failed = sum(
                1 for t in refreshed if t.status in (TaskStatus.FAILED, TaskStatus.BLOCKED_BY_RISK)
            )

            earned = sum(float(t.result_json.get("earned_usd", 0)) for t in refreshed)
            gas = sum(float(t.result_json.get("gas_spent_usd", 0)) for t in refreshed)

            await strategy_repo.set_status(
                strategy_id,
                StrategyStatus.DONE if failed == 0 else StrategyStatus.ABORTED,
            )

            report = Report(
                strategy_id=strategy_id,
                summary=f"{succeeded}/{len(refreshed)} tasks succeeded",
                tasks_total=len(refreshed),
                tasks_succeeded=succeeded,
                tasks_failed=failed,
                earned_usd=earned,
                gas_spent_usd=gas,
                artifacts_json={"task_ids": [t.id for t in refreshed]},
            )
            await report_repo.add(report)
            return report

    # ------------------------------------------------------------------
    async def _execute_single(self, task: Task) -> None:
        """Worker callback – run one task end-to-end with its own session."""
        async with self.container.db.session() as session:
            task_repo = TaskRepository(session)
            wallet_repo = WalletRepository(session)

            task_db = await task_repo.get(task.id)
            if task_db is None:
                logger.warning("engine.task_missing", task_id=task.id)
                return
            await task_repo.mark_running(task_db)
            wallet_db = (
                await wallet_repo.get(task_db.wallet_id) if task_db.wallet_id else None
            )

            chain = (task_db.params or {}).get("chain") or "ethereum"
            try:
                connector = WalletConnector.for_chain(
                    label=wallet_db.label if wallet_db else "default",
                    address=wallet_db.address if wallet_db else "0x" + "0" * 40,
                    chain=chain,
                    registry=self.evm_registry,
                    extension_attached=False,
                )
            except ChainConnectionError as exc:
                await task_repo.mark_finished(
                    task_db, status=TaskStatus.FAILED, error=str(exc), result={}
                )
                return

            result = await self.executor.run(task=task_db, wallet=connector, chain=chain)
            status = ExecutorAgent.status_from_result(result)
            await task_repo.mark_finished(
                task_db,
                status=status,
                result=result.model_dump(mode="json"),
                error=None if result.ok else result.message,
            )
