"""Faucet task handler."""
from __future__ import annotations

from app.browser.selectors import SelectorEngine
from app.core.exceptions import RetryableError, SelectorNotFoundError
from app.models.orm import Task, TaskKind
from app.models.schemas import TaskResult
from app.tasks.handlers.base import TaskHandler
from app.wallet.connector import WalletConnector

_CLAIM_SELECTORS = (
    'button:has-text("Claim")',
    'button:has-text("Request")',
    'button:has-text("Drip")',
    '[data-testid="faucet-claim"]',
)
_ADDRESS_INPUT_SELECTORS = (
    'input[placeholder*="0x"]',
    'input[placeholder*="wallet"]',
    'input[name*="address"]',
    'input[type="text"]',
)


class FaucetHandler(TaskHandler):
    kind = TaskKind.FAUCET

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        if not task.target_url:
            return TaskResult(ok=False, message="faucet target_url missing")

        async with self.browser.page(wallet.label) as page:
            await page.goto(task.target_url, wait_until="domcontentloaded")
            sel = SelectorEngine(page, humanizer=self.humanizer)
            await sel.wait_idle(800)

            # Fill the address if the faucet has an input box.
            await sel.maybe_fill(_ADDRESS_INPUT_SELECTORS, wallet.address, timeout=3_000)
            await self.humanizer.sleep(scale=0.5)

            try:
                await sel.click(_CLAIM_SELECTORS, timeout=15_000)
            except SelectorNotFoundError as exc:
                raise RetryableError(str(exc)) from exc

            await sel.wait_idle(1_500)

            success_text = await sel.get_text(
                ("text=/success/i", "text=/sent/i", "text=/funded/i"), timeout=8_000
            )
            return TaskResult(
                ok=success_text is not None,
                message=success_text or "claim submitted; no confirmation text detected",
                data={"url": task.target_url},
            )
