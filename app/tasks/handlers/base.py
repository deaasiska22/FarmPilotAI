"""TaskHandler interface + registry.

Each handler implements one ``TaskKind`` and is responsible for translating a
high-level intent (PlanItem / Task row) into concrete browser + wallet
operations.
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from app.models.orm import Task, TaskKind
from app.models.schemas import PlanItem, TaskResult

if TYPE_CHECKING:  # pragma: no cover
    from app.browser.manager import BrowserManager
    from app.core.humanize import Humanizer
    from app.wallet.connector import WalletConnector


class TaskHandler(abc.ABC):
    """Abstract base for all concrete task handlers."""

    kind: TaskKind

    def __init__(self, browser: BrowserManager, humanizer: Humanizer) -> None:
        self.browser = browser
        self.humanizer = humanizer

    @abc.abstractmethod
    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult: ...

    def to_plan_item(self, task: Task) -> PlanItem:
        return PlanItem(
            kind=task.kind,
            title=task.title,
            target_url=task.target_url,
            params=task.params or {},
            rationale=None,
            risk_score=float((task.params or {}).get("risk_score", 0.0)),
        )


class HandlerRegistry:
    def __init__(self) -> None:
        self._by_kind: dict[str, TaskHandler] = {}

    def register(self, handler: TaskHandler) -> None:
        self._by_kind[handler.kind.value] = handler

    def asdict(self) -> dict[str, TaskHandler]:
        return dict(self._by_kind)

    def get(self, kind: TaskKind | str) -> TaskHandler | None:
        key = kind.value if isinstance(kind, TaskKind) else kind
        return self._by_kind.get(key)
