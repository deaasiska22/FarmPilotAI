"""Swap handler.

This is intentionally conservative – it only *prepares* the swap UI and then
triggers the extension popup. The actual signing is gated by the executor's
risk agent and the global ``EXEC_DRY_RUN`` switch.
"""
from __future__ import annotations

from app.browser.selectors import SelectorEngine
from app.core.exceptions import RetryableError, SelectorNotFoundError
from app.models.orm import Task, TaskKind
from app.models.schemas import TaskResult
from app.tasks.handlers.base import TaskHandler
from app.wallet.connector import WalletConnector

_AMOUNT_INPUT_SELECTORS = (
    'input[placeholder="0.0"]',
    'input[inputmode="decimal"]',
    'input[type="number"]',
)
_SWAP_BUTTON_SELECTORS = (
    'button:has-text("Swap")',
    'button:has-text("Confirm Swap")',
    'button:has-text("Review")',
)


class SwapHandler(TaskHandler):
    kind = TaskKind.SWAP

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        if not task.target_url:
            return TaskResult(ok=False, message="swap target_url missing")

        amount = str(task.params.get("amount", "0.001"))
        from_token = task.params.get("from_token")
        to_token = task.params.get("to_token")
        dry_run = bool(task.params.get("dry_run", True))

        session = await self.browser.open_session(wallet.label)
        async with self.browser.page(wallet.label) as page:
            await page.goto(task.target_url, wait_until="domcontentloaded")
            sel = SelectorEngine(page, humanizer=self.humanizer)
            await sel.wait_idle(1_500)

            # Connect wallet if needed
            if await sel.maybe_click('button:has-text("Connect")', timeout=3_000):
                if session.extension:
                    await session.extension.ensure_connected(page)
                await self.humanizer.sleep()

            # Fill amount
            try:
                await sel.fill(_AMOUNT_INPUT_SELECTORS, amount)
            except SelectorNotFoundError as exc:
                raise RetryableError(str(exc)) from exc

            await self.humanizer.sleep()

            if dry_run:
                return TaskResult(
                    ok=True,
                    message="dry_run – swap prepared but not signed",
                    data={
                        "amount": amount,
                        "from_token": from_token,
                        "to_token": to_token,
                    },
                )

            # Confirm via dApp + extension popup
            try:
                await sel.click(_SWAP_BUTTON_SELECTORS, timeout=10_000)
            except SelectorNotFoundError as exc:
                raise RetryableError(str(exc)) from exc

            if session.extension:
                await session.extension.ensure_connected(page)

            return TaskResult(
                ok=True,
                message="swap submitted",
                data={"amount": amount, "from_token": from_token, "to_token": to_token},
            )
