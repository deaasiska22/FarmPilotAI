"""Self-healing selector engine.

The Web3 ecosystem is famously fast-moving – data-testid attributes appear,
disappear, and rename across releases. Each user-facing action takes a tuple
of selectors and falls through them in order; if none match we surface a
:class:`SelectorNotFoundError` with the full attempt log.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.core.exceptions import SelectorNotFoundError
from app.core.humanize import Humanizer
from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Locator, Page


logger = get_logger("browser.selectors")


class SelectorEngine:
    """Wraps a Playwright :class:`Page` with multi-selector fallbacks."""

    def __init__(self, page: Page, humanizer: Humanizer | None = None) -> None:
        self.page = page
        self.humanizer = humanizer

    # ------------------------------------------------------------------
    def _normalize(self, selectors: str | Iterable[str]) -> tuple[str, ...]:
        if isinstance(selectors, str):
            return (selectors,)
        return tuple(selectors)

    async def _first_visible(
        self, selectors: tuple[str, ...], timeout: int
    ) -> Locator | None:
        per_attempt = max(250, timeout // max(1, len(selectors)))
        for sel in selectors:
            loc = self.page.locator(sel).first
            try:
                await loc.wait_for(state="visible", timeout=per_attempt)
                return loc
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    async def exists(self, selectors: str | Iterable[str], timeout: int = 5_000) -> bool:
        sels = self._normalize(selectors)
        return await self._first_visible(sels, timeout) is not None

    async def click(
        self,
        selectors: str | Iterable[str],
        timeout: int = 15_000,
        *,
        humanize: bool = True,
    ) -> None:
        sels = self._normalize(selectors)
        loc = await self._first_visible(sels, timeout)
        if loc is None:
            raise SelectorNotFoundError(f"click: none of {sels} matched within {timeout}ms")
        # Tiny mouse-move sets off most bot detectors a lot less than a raw click.
        try:
            box = await loc.bounding_box()
            if box:
                await self.page.mouse.move(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=8,
                )
        except Exception:
            pass
        await loc.click()
        if humanize and self.humanizer is not None:
            await self.humanizer.sleep(scale=0.4)

    async def maybe_click(
        self,
        selectors: str | Iterable[str],
        timeout: int = 4_000,
        *,
        humanize: bool = True,
    ) -> bool:
        """Click if found, return False otherwise. Never raises."""
        sels = self._normalize(selectors)
        loc = await self._first_visible(sels, timeout)
        if loc is None:
            return False
        try:
            await loc.click()
        except Exception as exc:
            logger.warning("selector.maybe_click_failed", selectors=sels, error=str(exc))
            return False
        if humanize and self.humanizer is not None:
            await self.humanizer.sleep(scale=0.4)
        return True

    async def fill(
        self,
        selectors: str | Iterable[str],
        value: str,
        timeout: int = 15_000,
        *,
        human_typing: bool = True,
    ) -> None:
        sels = self._normalize(selectors)
        loc = await self._first_visible(sels, timeout)
        if loc is None:
            raise SelectorNotFoundError(f"fill: none of {sels} matched within {timeout}ms")
        await loc.click()
        if human_typing and self.humanizer is not None:
            # type character by character with realistic cadence
            await loc.fill("")
            for ch in value:
                await loc.type(ch, delay=self.humanizer.keystroke_delay_ms())
            return
        await loc.fill(value)

    async def maybe_fill(
        self,
        selectors: str | Iterable[str],
        value: str,
        timeout: int = 4_000,
    ) -> bool:
        try:
            await self.fill(selectors, value, timeout=timeout)
            return True
        except SelectorNotFoundError:
            return False

    # ------------------------------------------------------------------
    async def get_text(self, selectors: str | Iterable[str], timeout: int = 5_000) -> str | None:
        sels = self._normalize(selectors)
        loc = await self._first_visible(sels, timeout)
        if loc is None:
            return None
        try:
            return (await loc.inner_text()).strip()
        except Exception:
            return None

    async def wait_idle(self, ms: int = 500) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=ms * 4)
        except Exception:
            await asyncio.sleep(ms / 1000)
