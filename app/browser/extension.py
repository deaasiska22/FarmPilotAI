"""Wallet extension support (MetaMask / Rabby).

We do **not** ship an extension binary. The user must download the unpacked
extension once (or point at an existing install) and reference its path via
``WALLET_EXTENSION_PATH``. The runtime then:

1. Launches Chromium with ``--load-extension=...`` against a persistent
   profile.
2. Discovers the extension's background service worker.
3. Performs the one-time onboarding (import mnemonic + set password) if the
   extension's keystore is empty.
4. Exposes :meth:`ensure_connected` for downstream handlers, which clicks
   "Connect" / "Approve" popups from the dApp side.

The flow is best-effort and self-healing: every selector goes through
:class:`SelectorEngine` with multiple fallbacks.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import WalletSettings
from app.core.exceptions import WalletExtensionError
from app.core.humanize import Humanizer
from app.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import BrowserContext, Page


logger = get_logger("browser.extension")


# ---------------------------------------------------------------------------
# Extension catalog
# ---------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class ExtensionSpec:
    """Static metadata for a supported wallet extension."""

    name: str
    onboarding_url_re: str            # regex matched against page.url
    onboarding_terms_selectors: tuple[str, ...]
    import_button_selectors: tuple[str, ...]
    mnemonic_input_selectors: tuple[str, ...]
    password_input_selectors: tuple[str, ...]
    password_confirm_selectors: tuple[str, ...]
    submit_button_selectors: tuple[str, ...]
    connect_button_selectors: tuple[str, ...]
    approve_button_selectors: tuple[str, ...]


METAMASK = ExtensionSpec(
    name="metamask",
    onboarding_url_re=r".*chrome-extension://[a-z]+/home\.html.*",
    onboarding_terms_selectors=(
        '[data-testid="onboarding-terms-checkbox"]',
        'input[type="checkbox"]:has(~ * >> text=/agree/i)',
        'text="I agree"',
    ),
    import_button_selectors=(
        '[data-testid="onboarding-import-wallet"]',
        'button:has-text("Import an existing wallet")',
        'button:has-text("Import wallet")',
    ),
    mnemonic_input_selectors=(
        '[data-testid="import-srp__srp-word-0"]',
        'input[placeholder*="Secret"]',
        'textarea[autocomplete="off"]',
    ),
    password_input_selectors=(
        '[data-testid="create-password-new"]',
        'input[autocomplete="new-password"]',
        'input[type="password"]',
    ),
    password_confirm_selectors=(
        '[data-testid="create-password-confirm"]',
        'input[autocomplete="new-password"]:nth-of-type(2)',
    ),
    submit_button_selectors=(
        '[data-testid="create-password-import"]',
        '[data-testid="onboarding-complete-done"]',
        'button:has-text("Import")',
        'button:has-text("Done")',
        'button[type="submit"]',
    ),
    connect_button_selectors=(
        '[data-testid="page-container-footer-next"]',
        'button:has-text("Next")',
        'button:has-text("Connect")',
    ),
    approve_button_selectors=(
        '[data-testid="page-container-footer-next"]',
        'button:has-text("Approve")',
        'button:has-text("Confirm")',
    ),
)


RABBY = ExtensionSpec(
    name="rabby",
    onboarding_url_re=r".*chrome-extension://[a-z]+/index\.html.*",
    onboarding_terms_selectors=('text="I agree"',),
    import_button_selectors=(
        'button:has-text("Import via Mnemonic")',
        'button:has-text("Import")',
    ),
    mnemonic_input_selectors=('textarea',),
    password_input_selectors=('input[type="password"]',),
    password_confirm_selectors=('input[type="password"]:nth-of-type(2)',),
    submit_button_selectors=('button:has-text("Confirm")',),
    connect_button_selectors=('button:has-text("Connect")',),
    approve_button_selectors=('button:has-text("Sign")', 'button:has-text("Approve")'),
)


_EXTENSIONS = {"metamask": METAMASK, "rabby": RABBY}


def get_extension_spec(name: str) -> ExtensionSpec | None:
    return _EXTENSIONS.get(name.lower())


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class WalletExtension:
    """Drives a wallet extension via Playwright.

    A single instance is bound to a single ``BrowserContext`` (and therefore a
    single Chromium profile / wallet identity).
    """

    def __init__(
        self,
        context: BrowserContext,
        spec: ExtensionSpec,
        settings: WalletSettings,
        humanizer: Humanizer,
    ) -> None:
        self.context = context
        self.spec = spec
        self.settings = settings
        self.humanizer = humanizer
        self._home_url: str | None = None
        self._log = logger.bind(extension=spec.name)

    # ------------------------------------------------------------------
    @classmethod
    def validate_extension_path(cls, settings: WalletSettings) -> Path | None:
        if settings.extension == "none":
            return None
        if not settings.extension_path:
            raise WalletExtensionError(
                "WALLET_EXTENSION_PATH is not set – cannot load wallet extension. "
                "Either set WALLET_EXTENSION=none or point at an unpacked extension dir."
            )
        p = Path(settings.extension_path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            raise WalletExtensionError(f"Extension path does not exist: {p}")
        manifest = p / "manifest.json"
        if not manifest.exists():
            raise WalletExtensionError(f"manifest.json missing in {p}")
        return p

    # ------------------------------------------------------------------
    async def discover_home_url(self, timeout_s: float = 20.0) -> str:
        """Find the extension's onboarding/home page from background workers."""
        if self._home_url:
            return self._home_url

        deadline = asyncio.get_running_loop().time() + timeout_s
        while asyncio.get_running_loop().time() < deadline:
            # background_pages = MV2, service_workers = MV3
            workers = list(self.context.background_pages) + list(self.context.service_workers)
            for w in workers:
                url = getattr(w, "url", "")
                if url.startswith("chrome-extension://"):
                    base = url.rsplit("/", 1)[0]
                    self._home_url = f"{base}/home.html"
                    self._log.info("extension.home_discovered", url=self._home_url)
                    return self._home_url
            await asyncio.sleep(0.5)

        raise WalletExtensionError("Could not discover wallet extension after launch")

    # ------------------------------------------------------------------
    async def onboard(self) -> None:
        """One-time setup: import mnemonic + set password.

        Idempotent: if the keystore already exists this is a no-op.
        """
        if not self.settings.default_mnemonic or not self.settings.default_password:
            self._log.warning("extension.onboard.skipped", reason="missing mnemonic/password")
            return

        from app.browser.selectors import SelectorEngine

        home = await self.discover_home_url()
        page = await self.context.new_page()
        sel = SelectorEngine(page, humanizer=self.humanizer)

        await page.goto(home, wait_until="domcontentloaded")
        await self.humanizer.sleep()

        # Already onboarded? bail out
        if await sel.exists('[data-testid="account-menu-icon"]', timeout=2_000):
            self._log.info("extension.already_onboarded")
            await page.close()
            return

        await sel.maybe_click(self.spec.onboarding_terms_selectors)
        await sel.click(self.spec.import_button_selectors)
        await self.humanizer.sleep()

        # MetaMask renders 12 individual word boxes; we type into the first
        # and rely on its paste-handling to spread them. Falls back to a
        # single textarea for Rabby.
        await sel.fill(self.spec.mnemonic_input_selectors, self.settings.default_mnemonic)
        await self.humanizer.sleep()

        await sel.fill(self.spec.password_input_selectors, self.settings.default_password)
        await sel.maybe_fill(self.spec.password_confirm_selectors, self.settings.default_password)
        await sel.click(self.spec.submit_button_selectors)

        # Step through any "Done" screens.
        for _ in range(5):
            if not await sel.maybe_click(self.spec.submit_button_selectors, timeout=2_500):
                break
            await self.humanizer.sleep(scale=0.5)

        self._log.info("extension.onboarded")
        await page.close()

    # ------------------------------------------------------------------
    async def approve_pending_popup(self, timeout_s: float = 15.0) -> bool:
        """Click "Connect" / "Approve" on whichever extension popup is open.

        Returns True if a popup was found and approved.
        """
        from app.browser.selectors import SelectorEngine

        deadline = asyncio.get_running_loop().time() + timeout_s
        while asyncio.get_running_loop().time() < deadline:
            for page in self.context.pages:
                if "notification.html" in page.url or "popup.html" in page.url:
                    sel = SelectorEngine(page, humanizer=self.humanizer)
                    # Many flows require two clicks: Next then Confirm.
                    clicked_once = await sel.maybe_click(
                        self.spec.connect_button_selectors, timeout=4_000
                    )
                    clicked_twice = await sel.maybe_click(
                        self.spec.approve_button_selectors, timeout=4_000
                    )
                    if clicked_once or clicked_twice:
                        self._log.info("extension.popup_approved", url=page.url)
                        return True
            await asyncio.sleep(0.5)
        self._log.debug("extension.no_popup")
        return False

    async def ensure_connected(self, dapp_page: Page) -> None:
        """Convenience: trigger any pending popups after a dApp "Connect" click."""
        await asyncio.sleep(1.0)   # let the popup spawn
        await self.approve_pending_popup()
