"""High-level wallet connector.

Bundles an :class:`EVMClient`, a :class:`BaseSigner`, and a reference to the
browser-side wallet extension. Task handlers receive a :class:`WalletConnector`
and pick the path they need (RPC read, dApp click-through, raw signing).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.wallet.evm import EVMClient, EVMRegistry
from app.wallet.signer import BaseSigner

logger = get_logger("wallet.connector")


@dataclass(slots=True)
class WalletConnector:
    """Composite the executor passes around per (wallet, project) pair."""

    label: str
    address: str
    chain: str
    evm: EVMClient
    signer: BaseSigner | None = None       # None when in dry-run / observer mode
    extension_attached: bool = False       # True if a BrowserSession with extension exists

    @classmethod
    def for_chain(
        cls,
        label: str,
        address: str,
        chain: str,
        registry: EVMRegistry,
        signer: BaseSigner | None = None,
        extension_attached: bool = False,
    ) -> WalletConnector:
        return cls(
            label=label,
            address=address,
            chain=chain,
            evm=registry.get(chain),
            signer=signer,
            extension_attached=extension_attached,
        )

    async def liquidity_summary(self) -> dict[str, float]:
        """Cheap snapshot used by the planner / risk layer."""
        balance = await self.evm.get_balance_eth(self.address)
        return {self.chain: balance}
