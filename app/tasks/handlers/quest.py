"""Quest / check-in handlers."""
from __future__ import annotations

from app.browser.selectors import SelectorEngine
from app.core.exceptions import RetryableError, SelectorNotFoundError
from app.models.orm import Task, TaskKind
from app.models.schemas import TaskResult
from app.tasks.handlers.base import TaskHandler
from app.wallet.connector import WalletConnector

_QUEST_BUTTON_SELECTORS = (
    'button:has-text("Connect Wallet")',
    'button:has-text("Connect")',
    'button:has-text("Verify")',
    'button:has-text("Claim")',
    'button:has-text("Complete")',
)


class QuestHandler(TaskHandler):
    """Generic "press the obvious buttons in order" quest runner."""

    kind = TaskKind.QUEST

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        if not task.target_url:
            return TaskResult(ok=False, message="quest target_url missing")

        session = await self.browser.open_session(wallet.label)
        async with self.browser.page(wallet.label) as page:
            await page.goto(task.target_url, wait_until="domcontentloaded")
            sel = SelectorEngine(page, humanizer=self.humanizer)
            await sel.wait_idle(1_500)

            attempts: list[str] = []
            for label in ("Connect Wallet", "Connect", "Verify", "Claim", "Complete"):
                if await sel.maybe_click(f'button:has-text("{label}")', timeout=3_000):
                    attempts.append(label)
                    # Connection flows spawn an extension popup — drive it.
                    if label.startswith("Connect") and session.extension:
                        await session.extension.ensure_connected(page)
                    await self.humanizer.sleep()

            if not attempts:
                raise RetryableError("no quest buttons found")

            await sel.wait_idle(1_500)
            confirmation = await sel.get_text(
                (
                    "text=/quest.*complete/i",
                    "text=/verified/i",
                    "text=/success/i",
                ),
                timeout=5_000,
            )
            return TaskResult(
                ok=confirmation is not None or "Claim" in attempts,
                message=confirmation or f"quest steps executed: {attempts}",
                data={"steps": attempts, "url": task.target_url},
            )


class CheckinHandler(TaskHandler):
    """Daily check-in handler — single click, idempotent."""

    kind = TaskKind.CHECKIN

    async def execute(self, *, task: Task, wallet: WalletConnector) -> TaskResult:
        if not task.target_url:
            return TaskResult(ok=False, message="checkin target_url missing")

        async with self.browser.page(wallet.label) as page:
            await page.goto(task.target_url, wait_until="domcontentloaded")
            sel = SelectorEngine(page, humanizer=self.humanizer)
            await sel.wait_idle(800)
            try:
                await sel.click(
                    (
                        'button:has-text("Check-in")',
                        'button:has-text("Check in")',
                        'button:has-text("Daily")',
                    ),
                    timeout=10_000,
                )
            except SelectorNotFoundError as exc:
                # already checked in today is a soft success
                if await sel.exists("text=/already.*checked/i", timeout=2_000):
                    return TaskResult(ok=True, message="already checked in today")
                raise RetryableError(str(exc)) from exc

            return TaskResult(ok=True, message="check-in submitted")
