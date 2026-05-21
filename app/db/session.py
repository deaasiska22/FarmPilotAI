"""Async SQLAlchemy engine + session management."""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import DatabaseSettings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger("db")


class Database:
    """Owns the engine and session factory for the lifetime of the process."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._ensure_sqlite_dir(settings.url)
        self._engine: AsyncEngine = create_async_engine(
            settings.url,
            echo=settings.echo,
            future=True,
            pool_pre_ping=True,
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @staticmethod
    def _ensure_sqlite_dir(url: str) -> None:
        if not url.startswith("sqlite"):
            return
        # crude DSN parse: sqlite+aiosqlite:///./data/db.sqlite
        try:
            path_part = url.split("///", 1)[1]
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
        except IndexError:  # in-memory or atypical DSN – nothing to do
            return

    # ------------------------------------------------------------------
    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session that commits on clean exit and rolls back on error."""
        session = self._sessionmaker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # ------------------------------------------------------------------
    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("db.schema_created", url=self._settings.url)

    async def drop_all(self) -> None:  # mostly for tests
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def aclose(self) -> None:
        await self._engine.dispose()
        logger.info("db.engine_disposed")
