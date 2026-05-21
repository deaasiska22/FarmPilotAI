from __future__ import annotations

import pytest

from app.db.repositories.project_repo import ProjectRepository
from app.db.repositories.wallet_repo import WalletRepository
from app.models.orm import Project, ProjectRiskTier, Wallet


@pytest.mark.asyncio
async def test_project_upsert(container):
    async with container.db.session() as session:
        repo = ProjectRepository(session)
        p1 = await repo.upsert(
            Project(
                slug="foo",
                name="Foo",
                url="https://foo.example",
                chain="ethereum",
                risk_tier=ProjectRiskTier.LOW,
                tags=["faucet"],
                metadata_json={},
            )
        )
        p2 = await repo.upsert(
            Project(
                slug="foo",
                name="Foo 2",
                url="https://foo.example",
                chain="ethereum",
                risk_tier=ProjectRiskTier.MEDIUM,
                tags=["faucet", "airdrop"],
                metadata_json={},
            )
        )
    assert p1.id == p2.id
    assert p2.name == "Foo 2"
    assert p2.risk_tier == ProjectRiskTier.MEDIUM


@pytest.mark.asyncio
async def test_wallet_lookup(container, tmp_path):
    addr = "0x" + "a" * 40
    profile_dir = str(tmp_path / "alice")
    async with container.db.session() as session:
        repo = WalletRepository(session)
        await repo.add(
            Wallet(label="alice", address=addr, profile_dir=profile_dir, is_active=True)
        )

    async with container.db.session() as session:
        repo = WalletRepository(session)
        w = await repo.get_by_label("alice")
    assert w is not None
    assert w.address == addr
