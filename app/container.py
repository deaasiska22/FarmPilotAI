"""Application-wide dependency container.

Centralises construction and lifecycle of the heavy singletons:

* :class:`Settings`
* SQLAlchemy engine / session factory
* Browser manager (Playwright)
* AI reasoner client
* Task engine

FastAPI's :mod:`fastapi.Depends` and the agents both pull objects from the
same container, so wiring stays single-sourced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.core.humanize import Humanizer
from app.core.logging import configure_logging, get_logger
from app.core.retry import RetryPolicy


@dataclass
class Container:
    """Lazy-initialising service container.

    All heavy resources are constructed on first access. Tests can build a
    :class:`Container` with stub attributes and pass it where the real one
    would normally go.
    """

    settings: Settings = field(default_factory=get_settings)

    # late-bound singletons
    _humanizer: Humanizer | None = field(default=None, init=False, repr=False)
    _retry_policy: RetryPolicy | None = field(default=None, init=False, repr=False)
    _db: object | None = field(default=None, init=False, repr=False)
    _browser_manager: object | None = field(default=None, init=False, repr=False)
    _ai_reasoner: object | None = field(default=None, init=False, repr=False)
    _task_engine: object | None = field(default=None, init=False, repr=False)
    _log: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        configure_logging(self.settings.log)
        self._log = get_logger("container")

    # ------------------------------------------------------------------
    # Pure value singletons
    # ------------------------------------------------------------------
    @property
    def humanizer(self) -> Humanizer:
        if self._humanizer is None:
            self._humanizer = Humanizer.from_settings(self.settings.execution)
        return self._humanizer

    @property
    def retry_policy(self) -> RetryPolicy:
        if self._retry_policy is None:
            ex = self.settings.execution
            self._retry_policy = RetryPolicy(
                max_attempts=ex.retry_max_attempts,
                base_ms=ex.retry_backoff_base_ms,
                max_ms=ex.retry_backoff_max_ms,
            )
        return self._retry_policy

    # ------------------------------------------------------------------
    # Heavy resources (imported lazily to avoid cycles)
    # ------------------------------------------------------------------
    @property
    def db(self):
        if self._db is None:
            from app.db.session import Database

            self._db = Database(self.settings.db)
        return self._db

    @property
    def browser_manager(self):
        if self._browser_manager is None:
            from app.browser.manager import BrowserManager

            self._browser_manager = BrowserManager(
                settings=self.settings.browser,
                wallet_settings=self.settings.wallet,
                humanizer=self.humanizer,
            )
        return self._browser_manager

    @property
    def ai_reasoner(self):
        if self._ai_reasoner is None:
            from app.ai.reasoner import build_reasoner

            self._ai_reasoner = build_reasoner(self.settings.ai)
        return self._ai_reasoner

    @property
    def task_engine(self):
        if self._task_engine is None:
            from app.tasks.engine import TaskEngine

            self._task_engine = TaskEngine(container=self)
        return self._task_engine

    # ------------------------------------------------------------------
    async def aclose(self) -> None:
        """Tear down everything that was actually constructed."""
        self._log.info("container.shutdown.start")
        if self._task_engine is not None:
            await self._task_engine.aclose()  # type: ignore[attr-defined]
        if self._browser_manager is not None:
            await self._browser_manager.aclose()  # type: ignore[attr-defined]
        if self._db is not None:
            await self._db.aclose()  # type: ignore[attr-defined]
        self._log.info("container.shutdown.done")


_container: Container | None = None


def get_container() -> Container:
    """Process-wide singleton accessor.

    Tests can call :func:`set_container` to swap in a custom container.
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container | None) -> None:
    global _container
    _container = container
