"""End-to-end farming workflow.

Demonstrates the full pipeline without requiring any external network or a
real wallet extension:

  1. Seed a wallet + a project in the DB.
  2. Ask the PlannerAgent to draft a strategy (via the heuristic reasoner).
  3. Run the strategy through the TaskEngine.
  4. Render a markdown report.

Run with:

    $ python -m scripts.run_workflow

Requires only ``pip install -r requirements.txt`` – no Playwright browsers,
no RPC connectivity (we override the handlers with mocks below so the
example is hermetic).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.container import Container, get_container
from app.core.logging import configure_logging, get_logger
from app.db.repositories.project_repo import ProjectRepository
from app.db.repositories.wallet_repo import WalletRepository
from app.models.orm import Project, ProjectRiskTier, Task, TaskKind, Wallet
from app.models.schemas import TaskResult
from app.reports.generator import ReportGenerator
from app.services.execution_service import ExecutionService
from app.services.strategy_service import StrategyService
from app.tasks.handlers.base import TaskHandler
from app.wallet.connector import WalletConnector


class _NoopHandler(TaskHandler):
    """Mock handler used by the example so we don't need a real browser."""

    def __init__(self, kind: TaskKind, browser, humanizer) -> None:
        super().__init__(browser, humanizer)
        self.kind = kind

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        await asyncio.sleep(0.05)
        return TaskResult(ok=True, message=f"[noop] {task.kind.value}: {task.title}")


async def _seed(container: Container) -> tuple[Project, Wallet]:
    async with container.db.session() as session:
        projects = ProjectRepository(session)
        wallets = WalletRepository(session)

        project = await projects.upsert(
            Project(
                slug="demo-testnet",
                name="Demo Testnet Faucet",
                url="https://example.org/faucet",
                chain="ethereum",
                description="Demo project used by run_workflow.py",
                risk_tier=ProjectRiskTier.LOW,
                tags=["faucet", "testnet"],
            )
        )

        # Reuse if a wallet with this label already exists (re-runs)
        wallet = await wallets.get_by_label("demo-wallet")
        if wallet is None:
            wallet = Wallet(
                label="demo-wallet",
                address="0x000000000000000000000000000000000000dEaD",
                profile_dir=str(container.settings.browser.profiles_dir / "demo"),
                is_active=True,
                notes="Burner used by run_workflow.py",
            )
            await wallets.add(wallet)
    return project, wallet


async def main() -> None:
    container = get_container()
    configure_logging(container.settings.log)
    log = get_logger("example")

    # 1. DB
    await container.db.create_all()
    project, wallet = await _seed(container)
    log.info("seed.done", project=project.slug, wallet=wallet.label)

    # 2. Swap real handlers for hermetic no-ops (no browser, no chain calls).
    engine = container.task_engine
    for kind in TaskKind:
        handler = _NoopHandler(
            kind=kind,
            browser=container.browser_manager,
            humanizer=container.humanizer,
        )
        engine.registry.register(handler)
    engine.executor.handlers = engine.registry.asdict()

    # 3. Plan
    strategies = StrategyService(container)
    strategy = await strategies.design_for(
        project_slug=project.slug, wallet_label=wallet.label
    )
    log.info("plan.ready", strategy_id=strategy.id, name=strategy.name)

    # 4. Execute
    execution = ExecutionService(container)
    report = await execution.run(strategy.id)
    log.info(
        "execution.done",
        strategy_id=strategy.id,
        succeeded=report.tasks_succeeded,
        failed=report.tasks_failed,
    )

    # 5. Render report
    generator = ReportGenerator(container)
    md_path: Path = await generator.save_markdown(strategy.id)
    log.info("report.written", path=str(md_path))

    print("\n===== FarmPilot example summary =====")
    print(f"strategy : {strategy.name} (id={strategy.id})")
    print(f"tasks    : {report.tasks_succeeded}/{report.tasks_total} ok")
    print(f"report   : {md_path}")

    await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
