"""Repository pattern – one module per aggregate root.

Repositories take an :class:`AsyncSession` from the caller; they never open
or close sessions themselves. This keeps transaction boundaries explicit in
the service layer.
"""
from app.db.repositories.project_repo import ProjectRepository
from app.db.repositories.report_repo import ReportRepository
from app.db.repositories.strategy_repo import StrategyRepository
from app.db.repositories.task_repo import TaskRepository
from app.db.repositories.wallet_repo import WalletRepository

__all__ = [
    "ProjectRepository",
    "ReportRepository",
    "StrategyRepository",
    "TaskRepository",
    "WalletRepository",
]
