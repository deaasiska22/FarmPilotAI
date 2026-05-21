"""Gas estimation for planned actions.

The estimator marries two signals:

* **Static gas budget per task kind.** Most farming actions fall into a tight
  range (faucets are off-chain, simple swaps are ~150k gas units, bridges
  ~250k, etc.). We keep a table so the planner can quote numbers even when
  no RPC is reachable.
* **Live ``gas_price`` from the chain.** When an :class:`EVMRegistry` is
  available we ask the chain for its current gas price; otherwise we fall
  back to ``ExecutionSettings.default_gas_gwei``.

USD conversion uses ``ExecutionSettings.eth_price_usd`` — production deploys
should plug in a price oracle and override that at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import ExecutionSettings
from app.core.logging import get_logger
from app.models.orm import TaskKind
from app.models.schemas import PlanItem
from app.wallet.evm import EVMRegistry

logger = get_logger("agent.gas")


# ---------------------------------------------------------------------------
# Static per-kind gas budget (in gas units, not gwei).
# Values cover the 95th-percentile of mainnet observations.
# ---------------------------------------------------------------------------
DEFAULT_GAS_UNITS: dict[TaskKind, int] = {
    TaskKind.FAUCET: 0,        # off-chain
    TaskKind.QUEST: 0,         # off-chain (social)
    TaskKind.CHECKIN: 0,       # usually off-chain; on-chain checkins set via params
    TaskKind.SWAP: 165_000,
    TaskKind.BRIDGE: 260_000,
    TaskKind.CUSTOM: 120_000,
}


@dataclass(slots=True)
class GasQuote:
    gas_units: int
    gas_price_gwei: float
    gas_eth: float
    gas_usd: float


class GasEstimator:
    """Estimates gas for individual :class:`PlanItem`s.

    The estimator is intentionally lightweight; production deploys can drop
    in a richer implementation (e.g. simulating txs against a forked node)
    while keeping the same interface.
    """

    def __init__(
        self,
        settings: ExecutionSettings,
        evm_registry: EVMRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.evm_registry = evm_registry
        # Memoise live gas prices per chain so we don't hammer the RPC.
        self._gas_price_cache_gwei: dict[str, float] = {}

    # ------------------------------------------------------------------
    async def gas_price_gwei(self, chain: str) -> float:
        """Return current gwei for ``chain`` or fall back to the default."""
        if chain in self._gas_price_cache_gwei:
            return self._gas_price_cache_gwei[chain]

        gwei = self.settings.default_gas_gwei
        if self.evm_registry is not None:
            try:
                client = self.evm_registry.get(chain)
                wei = await client.get_gas_price_wei()
                gwei = wei / 1e9
            except Exception as exc:
                logger.warning(
                    "gas.live_price_failed",
                    chain=chain,
                    error=str(exc),
                    fallback_gwei=gwei,
                )
        self._gas_price_cache_gwei[chain] = gwei
        return gwei

    # ------------------------------------------------------------------
    async def estimate(self, item: PlanItem, chain: str) -> GasQuote:
        """Estimate gas for one :class:`PlanItem`.

        ``item.params['gas_units']`` overrides the default table when set.
        """
        params = item.params or {}
        explicit_units = params.get("gas_units")
        units = (
            int(explicit_units)
            if isinstance(explicit_units, int | float) and explicit_units >= 0
            else DEFAULT_GAS_UNITS.get(item.kind, 100_000)
        )

        if units == 0:
            return GasQuote(gas_units=0, gas_price_gwei=0.0, gas_eth=0.0, gas_usd=0.0)

        gwei = await self.gas_price_gwei(chain)
        gas_eth = (units * gwei) / 1e9
        gas_usd = gas_eth * self.settings.eth_price_usd
        return GasQuote(gas_units=units, gas_price_gwei=gwei, gas_eth=gas_eth, gas_usd=gas_usd)

    async def annotate(self, items: list[PlanItem], chain: str) -> list[PlanItem]:
        """Return a list of items with the gas fields populated."""
        out: list[PlanItem] = []
        for item in items:
            quote = await self.estimate(item, chain)
            out.append(
                item.model_copy(
                    update={
                        "gas_units": quote.gas_units,
                        "gas_estimate_usd": round(quote.gas_usd, 6),
                    }
                )
            )
        return out
