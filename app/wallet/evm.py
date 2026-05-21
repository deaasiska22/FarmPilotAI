"""Thin async wrapper around web3.py.

We deliberately keep this layer small – it owns chain connectivity and
read-only RPC calls. Anything that signs goes through :class:`WalletSigner`,
which is the single place where mnemonics / private keys are unsealed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import ChainConnectionError
from app.core.logging import get_logger

logger = get_logger("wallet.evm")


@dataclass(slots=True, frozen=True)
class ChainInfo:
    name: str
    rpc_url: str
    chain_id: int | None = None
    explorer_url: str | None = None


# A small, opinionated mapping. Callers can extend via env config.
KNOWN_CHAINS: dict[str, ChainInfo] = {
    "ethereum": ChainInfo("ethereum", "https://eth.llamarpc.com", 1, "https://etherscan.io"),
    "arbitrum": ChainInfo("arbitrum", "https://arb1.arbitrum.io/rpc", 42161, "https://arbiscan.io"),
    "base": ChainInfo("base", "https://mainnet.base.org", 8453, "https://basescan.org"),
    "optimism": ChainInfo("optimism", "https://mainnet.optimism.io", 10, "https://optimistic.etherscan.io"),
    "polygon": ChainInfo("polygon", "https://polygon-rpc.com", 137, "https://polygonscan.com"),
}


class EVMClient:
    """Single chain, single endpoint, async read-only client.

    All :mod:`web3` calls are sync – we shuttle them onto a worker thread so
    they don't block the event loop.
    """

    def __init__(self, chain: ChainInfo) -> None:
        self.chain = chain
        # Imported lazily – web3 is a heavy import.
        from web3 import Web3
        from web3.providers import HTTPProvider

        self._web3 = Web3(HTTPProvider(chain.rpc_url, request_kwargs={"timeout": 15}))

    async def _run(self, fn, *args: Any, **kwargs: Any):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def is_connected(self) -> bool:
        try:
            return bool(await self._run(self._web3.is_connected))
        except Exception as exc:
            logger.warning("evm.is_connected_error", chain=self.chain.name, error=str(exc))
            return False

    async def get_chain_id(self) -> int:
        return int(await self._run(lambda: self._web3.eth.chain_id))

    async def get_balance_wei(self, address: str) -> int:
        return int(await self._run(self._web3.eth.get_balance, address))

    async def get_balance_eth(self, address: str) -> float:
        wei = await self.get_balance_wei(address)
        return wei / 1e18

    async def estimate_gas(self, tx: dict) -> int:
        return int(await self._run(self._web3.eth.estimate_gas, tx))

    async def get_gas_price_wei(self) -> int:
        return int(await self._run(lambda: self._web3.eth.gas_price))


class EVMRegistry:
    """Lookup table of chain name -> :class:`EVMClient`."""

    def __init__(self, rpc_overrides: dict[str, str] | None = None) -> None:
        self._clients: dict[str, EVMClient] = {}
        self._chains: dict[str, ChainInfo] = dict(KNOWN_CHAINS)
        for name, url in (rpc_overrides or {}).items():
            existing = self._chains.get(name)
            self._chains[name] = ChainInfo(
                name=name,
                rpc_url=url,
                chain_id=existing.chain_id if existing else None,
                explorer_url=existing.explorer_url if existing else None,
            )

    def get(self, chain: str) -> EVMClient:
        chain = chain.lower()
        if chain not in self._chains:
            raise ChainConnectionError(f"unknown chain: {chain!r}")
        if chain not in self._clients:
            self._clients[chain] = EVMClient(self._chains[chain])
        return self._clients[chain]

    def known_chains(self) -> list[str]:
        return list(self._chains.keys())
