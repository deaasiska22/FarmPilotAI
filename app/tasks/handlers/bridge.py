"""Bridge handler – mostly a near-clone of swap with cross-chain inputs."""
from __future__ import annotations

from app.browser.selectors import SelectorEngine
from app.core.exceptions import RetryableError, SelectorNotFoundError
from app.models.orm import Task, TaskKind
from app.models.schemas import TaskResult
from app.tasks.handlers.base import TaskHandler
from app.wallet.connector import WalletConnector


class BridgeHandler(TaskHandler):
    kind = TaskKind.BRIDGE

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        if not task.target_url:
            return TaskResult(ok=False, message="bridge target_url missing")

        amount = str(task.params.get("amount", "0.001"))
        src_chain = task.params.get("src_chain")
        dst_chain = task.params.get("dst_chain")
        dry_run = bool(task.params.get("dry_run", True))

        session = await self.browser.open_session(wallet.label)
        async with self.browser.page(wallet.label) as page:
            await page.goto(task.target_url, wait_until="domcontentloaded")
            sel = SelectorEngine(page, humanizer=self.humanizer)
            await sel.wait_idle(1_500)

            if await sel.maybe_click('button:has-text("Connect")', timeout=3_000):
                if session.extension:
                    await session.extension.ensure_connected(page)
                await self.humanizer.sleep()

            try:
                await sel.fill(
                    ('input[placeholder="0.0"]', 'input[inputmode="decimal"]'), amount
                )
            except SelectorNotFoundError as exc:
                raise RetryableError(str(exc)) from exc

            if dry_run:
                return TaskResult(
                    ok=True,
                    message="dry_run – bridge prepared but not signed",
                    data={
                        "amount": amount,
                        "src_chain": src_chain,
                        "dst_chain": dst_chain,
                    },
                )

            try:
                await sel.click(
                    (
                        'button:has-text("Bridge")',
                        'button:has-text("Transfer")',
                        'button:has-text("Send")',
                    ),
                    timeout=10_000,
                )
            except SelectorNotFoundError as exc:
                raise RetryableError(str(exc)) from exc

            if session.extension:
                await session.extension.ensure_connected(page)
            return TaskResult(
                ok=True,
                message="bridge submitted",
                data={"amount": amount, "src_chain": src_chain, "dst_chain": dst_chain},
            )
