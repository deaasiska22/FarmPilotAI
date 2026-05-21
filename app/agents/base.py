"""Base agent contract.

Agents are *single-purpose* classes; they expose a single async ``run``
method and never own DB sessions. The orchestrator (service layer or task
engine) opens the session and passes it down.
"""
from __future__ import annotations

import abc
from typing import Any

from app.core.logging import get_logger


class BaseAgent(abc.ABC):
    """Common scaffolding for every agent in the system."""

    #: short, kebab-case identifier used in logs/metrics.
    name: str = "agent"

    def __init__(self) -> None:
        self.log = get_logger(f"agent.{self.name}")

    @abc.abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any: ...

    def bind(self, **ctx: Any) -> BaseAgent:
        """Return self with the logger temporarily bound to ``ctx``."""
        self.log = self.log.bind(**ctx)
        return self
