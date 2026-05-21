from __future__ import annotations

from app.agents.planner import PlannerAgent
from app.ai.strategy import StrategySynthesiser
from app.container import Container
from app.db.repositories.project_repo import ProjectRepository
from app.db.repositories.strategy_repo import StrategyRepository
from app.db.repositories.task_repo import TaskRepository
from app.db.repositories.wallet_repo import WalletRepository
from app.models.orm import Strategy, Task, TaskStatus
from app.models.schemas import StrategyRead


class StrategyService:
    def __init__(self, container: Container) -> None:
        self.container = container
        self.planner = PlannerAgent(
            synthesiser=StrategySynthesiser(container.ai_reasoner),
            settings=container.settings.execution,
        )

    async def design_for(self, *, project_slug: str, wallet_label: str | None) -> StrategyRead:
        async with self.container.db.session() as session:
            projects = ProjectRepository(session)
            wallets = WalletRepository(session)
            strategies = StrategyRepository(session)
            tasks = TaskRepository(session)

            project = await projects.get_by_slug(project_slug)
            if project is None:
                raise ValueError(f"unknown project slug: {project_slug!r}")
            wallet = await wallets.get_by_label(wallet_label) if wallet_label else None
            liquidity = 0.0  # placeholder – a real impl pulls live balances per chain

            project_dict = {
                "id": project.id,
                "slug": project.slug,
                "name": project.name,
                "url": project.url,
                "chain": project.chain,
                "description": project.description,
                "tags": project.tags,
                "risk_tier": project.risk_tier.value,
                "wallet_id": wallet.id if wallet else None,
            }
            wallet_addr = wallet.address if wallet else "0x" + "0" * 40

            strategy_create, plan_items = await self.planner.run(
                project=project_dict,
                wallet_address=wallet_addr,
                wallet_liquidity=liquidity,
            )
            strategy_orm = Strategy(**strategy_create.model_dump())
            await strategies.add(strategy_orm)

            for item in plan_items:
                params = {
                    **item.params,
                    "chain": project.chain,
                    "risk_score": item.risk_score,
                }
                tasks.session.add(
                    Task(
                        strategy_id=strategy_orm.id,
                        wallet_id=wallet.id if wallet else None,
                        kind=item.kind,
                        title=item.title,
                        target_url=item.target_url,
                        params=params,
                        status=TaskStatus.PENDING,
                    )
                )
            await session.flush()
        return StrategyRead.model_validate(strategy_orm)

    async def list_for_project(self, project_id: int) -> list[StrategyRead]:
        async with self.container.db.session() as session:
            repo = StrategyRepository(session)
            rows = await repo.list_for_project(project_id)
        return [StrategyRead.model_validate(r) for r in rows]
