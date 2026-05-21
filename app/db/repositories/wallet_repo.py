from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.orm import Wallet


class WalletRepository(BaseRepository[Wallet]):
    model = Wallet

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_address(self, address: str) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.address == address.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_label(self, label: str) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.label == label)
        return (await self.session.execute(stmt)).scalar_one_or_none()
