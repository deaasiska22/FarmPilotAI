"""Pre-built handler registry."""
from __future__ import annotations

from app.browser.manager import BrowserManager
from app.core.humanize import Humanizer
from app.tasks.handlers.base import HandlerRegistry, TaskHandler
from app.tasks.handlers.bridge import BridgeHandler
from app.tasks.handlers.faucet import FaucetHandler
from app.tasks.handlers.quest import CheckinHandler, QuestHandler
from app.tasks.handlers.swap import SwapHandler


def default_registry(browser: BrowserManager, humanizer: Humanizer) -> HandlerRegistry:
    reg = HandlerRegistry()
    for handler_cls in (FaucetHandler, QuestHandler, CheckinHandler, SwapHandler, BridgeHandler):
        h: TaskHandler = handler_cls(browser=browser, humanizer=humanizer)
        reg.register(h)
    return reg


__all__ = [
    "default_registry",
    "FaucetHandler",
    "QuestHandler",
    "CheckinHandler",
    "SwapHandler",
    "BridgeHandler",
]
