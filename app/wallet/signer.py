"""Signer abstraction.

The default :class:`LocalSigner` derives an account from the configured
mnemonic. Callers that integrate KMS / Vault / Fireblocks plug in their own
implementation by subclassing :class:`BaseSigner`.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from app.core.exceptions import WalletError
from app.core.logging import get_logger

logger = get_logger("wallet.signer")


@dataclass(slots=True, frozen=True)
class SignedTx:
    raw: bytes
    hash_hex: str


class BaseSigner(abc.ABC):
    """Pluggable signer interface."""

    address: str

    @abc.abstractmethod
    async def sign_transaction(self, tx: dict) -> SignedTx: ...

    @abc.abstractmethod
    async def sign_message(self, message: str) -> str: ...


class LocalSigner(BaseSigner):
    """In-process mnemonic-derived signer. Never log the secret."""

    def __init__(self, mnemonic: str, hd_path: str = "m/44'/60'/0'/0/0") -> None:
        if not mnemonic or len(mnemonic.split()) < 12:
            raise WalletError("mnemonic looks invalid")
        # Imported lazily – heavy and only needed when actually signing.
        from eth_account import Account

        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(mnemonic, account_path=hd_path)
        self._account = acct
        self.address = acct.address

    async def sign_transaction(self, tx: dict) -> SignedTx:
        import asyncio

        def _do() -> SignedTx:
            signed = self._account.sign_transaction(tx)
            return SignedTx(raw=bytes(signed.raw_transaction), hash_hex=signed.hash.hex())

        return await asyncio.to_thread(_do)

    async def sign_message(self, message: str) -> str:
        import asyncio

        from eth_account.messages import encode_defunct

        def _do() -> str:
            msg = encode_defunct(text=message)
            sig = self._account.sign_message(msg)
            return sig.signature.hex()

        return await asyncio.to_thread(_do)
