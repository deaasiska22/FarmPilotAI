from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Tiny generic CRUD helper. Repositories add domain methods on top."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, pk: int) -> ModelT | None:
        return await self.session.get(self.model, pk)

    async def list(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset).order_by(self.model.id.desc())  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
