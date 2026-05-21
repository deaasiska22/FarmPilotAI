from __future__ import annotations

import pytest

from app.agents.gas import DEFAULT_GAS_UNITS, GasEstimator
from app.config import ExecutionSettings
from app.models.orm import TaskKind
from app.models.schemas import PlanItem


def _settings(**overrides) -> ExecutionSettings:
    base = {
        "EXEC_HUMAN_DELAY_MIN_MS": 1,
        "EXEC_HUMAN_DELAY_MAX_MS": 2,
        "PLANNER_ETH_PRICE_USD": 3_000.0,
        "PLANNER_DEFAULT_GAS_GWEI": 50.0,
    }
    base.update(overrides)
    return ExecutionSettings(**base)


@pytest.mark.asyncio
async def test_off_chain_kinds_have_zero_gas():
    est = GasEstimator(_settings(), evm_registry=None)
    for kind in (TaskKind.FAUCET, TaskKind.QUEST, TaskKind.CHECKIN):
        item = PlanItem(kind=kind, title="x")
        quote = await est.estimate(item, chain="ethereum")
        assert quote.gas_units == 0
        assert quote.gas_usd == 0.0


@pytest.mark.asyncio
async def test_swap_uses_default_table_and_fallback_gwei():
    est = GasEstimator(_settings(), evm_registry=None)
    item = PlanItem(kind=TaskKind.SWAP, title="swap usdc")
    quote = await est.estimate(item, chain="ethereum")
    assert quote.gas_units == DEFAULT_GAS_UNITS[TaskKind.SWAP]
    assert quote.gas_price_gwei == 50.0
    # 165_000 units * 50 gwei = 0.00825 ETH; * $3000 = $24.75
    assert pytest.approx(quote.gas_eth, rel=1e-6) == 165_000 * 50 / 1e9
    assert pytest.approx(quote.gas_usd, rel=1e-6) == 165_000 * 50 / 1e9 * 3_000


@pytest.mark.asyncio
async def test_explicit_gas_units_override_defaults():
    est = GasEstimator(_settings(), evm_registry=None)
    item = PlanItem(
        kind=TaskKind.BRIDGE,
        title="bridge eth",
        params={"gas_units": 50_000},
    )
    quote = await est.estimate(item, chain="arbitrum")
    assert quote.gas_units == 50_000


@pytest.mark.asyncio
async def test_annotate_writes_back_to_plan_items():
    est = GasEstimator(_settings(), evm_registry=None)
    items = [
        PlanItem(kind=TaskKind.FAUCET, title="faucet"),
        PlanItem(kind=TaskKind.SWAP, title="swap"),
    ]
    annotated = await est.annotate(items, chain="ethereum")
    # input list left untouched (immutability matters for retries)
    assert items[1].gas_units == 0
    assert annotated[0].gas_units == 0
    assert annotated[1].gas_units > 0
    assert annotated[1].gas_estimate_usd > 0


@pytest.mark.asyncio
async def test_live_gas_price_used_when_registry_available():
    class _Client:
        async def get_gas_price_wei(self):
            return 12_345_000_000  # 12.345 gwei

    class _Registry:
        def get(self, chain):
            return _Client()

    est = GasEstimator(_settings(), evm_registry=_Registry())
    assert pytest.approx(await est.gas_price_gwei("base")) == 12.345


@pytest.mark.asyncio
async def test_live_gas_price_falls_back_on_rpc_failure():
    class _BrokenClient:
        async def get_gas_price_wei(self):
            raise RuntimeError("rpc down")

    class _Registry:
        def get(self, chain):
            return _BrokenClient()

    est = GasEstimator(_settings(PLANNER_DEFAULT_GAS_GWEI=42.0), evm_registry=_Registry())
    assert await est.gas_price_gwei("base") == 42.0
