from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import ContainerDep
from app.db.repositories.wallet_repo import WalletRepository
from app.models.orm import Wallet
from app.models.schemas import WalletCreate, WalletRead

router = APIRouter()


@router.get("", response_model=list[WalletRead])
async def list_wallets(container: ContainerDep) -> list[WalletRead]:
    async with container.db.session() as session:
        repo = WalletRepository(session)
        rows = await repo.list(limit=200)
    return [WalletRead.model_validate(r) for r in rows]


@router.post("", response_model=WalletRead, status_code=201)
async def create_wallet(payload: WalletCreate, container: ContainerDep) -> WalletRead:
    async with container.db.session() as session:
        repo = WalletRepository(session)
        if await repo.get_by_address(payload.address):
            raise HTTPException(status_code=409, detail="address already registered")
        orm = Wallet(**payload.model_dump())
        await repo.add(orm)
    return WalletRead.model_validate(orm)
