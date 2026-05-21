"""Top-level Playwright orchestrator.

Owns the singleton :class:`playwright.async_api.Playwright` instance and a
pool of named, persistent browser contexts keyed by wallet label.

External callers should only touch :class:`BrowserManager` – it hides the
extension loading, stealth injection, and lifecycle quirks.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.browser.extension import (
    WalletExtension,
    get_extension_spec,
)
from app.browser.profile import BrowserProfile
from app.browser.stealth import apply_stealth
from app.config import BrowserSettings, WalletSettings
from app.core.exceptions import BrowserError
from app.core.humanize import Humanizer
from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import BrowserContext, Page, Playwright


logger = get_logger("browser.manager")


@dataclass(slots=True)
class BrowserSession:
    """A single live (profile, context, wallet) triple."""

    profile: BrowserProfile
    context: BrowserContext
    extension: WalletExtension | None

    async def new_page(self) -> Page:
        page = await self.context.new_page()
        return page


class BrowserManager:
    """Lazy Playwright bootstrap + pooled persistent contexts."""

    def __init__(
        self,
        settings: BrowserSettings,
        wallet_settings: WalletSettings,
        humanizer: Humanizer,
    ) -> None:
        self.settings = settings
        self.wallet_settings = wallet_settings
        self.humanizer = humanizer

        self._playwright: Playwright | None = None
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

        # Lazily resolved on first session open so a missing extension path
        # doesn't crash startup when the user has WALLET_EXTENSION=none.
        self._extension_path: Path | None = None
        self._extension_validated = False

    def _resolve_extension_path(self) -> Path | None:
        if self._extension_validated:
            return self._extension_path
        if self.wallet_settings.extension == "none":
            self._extension_path = None
        else:
            self._extension_path = WalletExtension.validate_extension_path(
                self.wallet_settings
            )
        self._extension_validated = True
        return self._extension_path

    # ------------------------------------------------------------------
    async def _ensure_playwright(self) -> Playwright:
        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            logger.info("playwright.started")
        return self._playwright

    def _launch_args(self) -> list[str]:
        args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self._extension_path is not None:
            ext = str(self._extension_path)
            args += [
                f"--disable-extensions-except={ext}",
                f"--load-extension={ext}",
            ]
        return args

    # ------------------------------------------------------------------
    async def open_session(self, wallet_label: str) -> BrowserSession:
        """Return an existing or freshly-launched session for ``wallet_label``."""
        async with self._lock:
            if wallet_label in self._sessions:
                return self._sessions[wallet_label]

            pw = await self._ensure_playwright()
            extension_path = self._resolve_extension_path()
            profile = BrowserProfile.for_label(wallet_label, self.settings.profiles_dir)

            # Extensions cannot load in headless=True on stock Chromium; we
            # warn and fall back to headed when an extension is requested.
            headless = self.settings.headless and extension_path is None
            if self.settings.headless and extension_path is not None:
                logger.warning(
                    "browser.headless_disabled_for_extension",
                    reason="chromium does not support extensions in headless mode",
                )

            browser_type = pw.chromium
            context = await browser_type.launch_persistent_context(
                user_data_dir=profile.user_data_dir,
                headless=headless,
                channel=self.settings.channel if self.settings.channel != "chromium" else None,
                args=self._launch_args(),
                user_agent=self.settings.user_agent,
                viewport={"width": 1366, "height": 850},
                ignore_default_args=["--enable-automation"],
            )
            context.set_default_timeout(self.settings.default_timeout_ms)
            await apply_stealth(context)

            extension: WalletExtension | None = None
            spec = get_extension_spec(self.wallet_settings.extension)
            if spec is not None and extension_path is not None:
                extension = WalletExtension(
                    context=context,
                    spec=spec,
                    settings=self.wallet_settings,
                    humanizer=self.humanizer,
                )
                try:
                    await extension.onboard()
                except Exception as exc:
                    # Don't kill the session on onboarding failure – many flows
                    # only need a logged-in dApp profile.
                    logger.error("browser.onboard_failed", error=str(exc))

            session = BrowserSession(profile=profile, context=context, extension=extension)
            self._sessions[wallet_label] = session
            logger.info("browser.session_opened", wallet=wallet_label, headless=headless)
            return session

    # ------------------------------------------------------------------
    @asynccontextmanager
    async def page(self, wallet_label: str) -> AsyncIterator[Page]:
        """Yield a fresh page bound to ``wallet_label``'s session.

        The page is closed on exit; the context survives across calls.
        """
        session = await self.open_session(wallet_label)
        page = await session.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception as exc:
                logger.warning("browser.page_close_failed", error=str(exc))

    # ------------------------------------------------------------------
    async def screenshot(self, page: Page, filename: str) -> str:
        """Persist a screenshot under the configured ``screenshots`` dir."""
        path = self.settings.profiles_dir.parent / "screenshots" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception as exc:
            raise BrowserError(f"screenshot failed: {exc}") from exc
        return str(path)

    async def aclose(self) -> None:
        for label, session in list(self._sessions.items()):
            try:
                await session.context.close()
            except Exception as exc:
                logger.warning("browser.session_close_failed", wallet=label, error=str(exc))
        self._sessions.clear()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
            logger.info("playwright.stopped")
