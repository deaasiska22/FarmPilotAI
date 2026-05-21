"""Anti-detection patches applied to every browser context.

We don't claim full stealth – the goal is to remove the most obvious tells
(``navigator.webdriver``, missing chrome runtime, etc.) so the agent looks
no worse than a vanilla Chrome install.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import BrowserContext


_STEALTH_JS = """
// 1. Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Spoof languages + plugins to look like a fresh Chrome install
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5].map(() => ({ name: 'pdf', length: 1 })),
});

// 3. Chrome runtime presence
window.chrome = window.chrome || { runtime: {} };

// 4. Permissions.query returning sane defaults
const origQuery = navigator.permissions && navigator.permissions.query;
if (origQuery) {
    navigator.permissions.query = (p) =>
        p && p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : origQuery(p);
}

// 5. Fingerprint mitigation: deterministic but plausible canvas noise
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function (...args) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const w = this.width, h = this.height;
        if (w > 0 && h > 0) {
            const img = ctx.getImageData(0, 0, w, h);
            for (let i = 0; i < img.data.length; i += 50) {
                img.data[i] = img.data[i] ^ 1;
            }
            ctx.putImageData(img, 0, 0);
        }
    }
    return toDataURL.apply(this, args);
};
"""


async def apply_stealth(context: BrowserContext) -> None:
    """Install JS overrides on every new page in this context."""
    await context.add_init_script(_STEALTH_JS)
