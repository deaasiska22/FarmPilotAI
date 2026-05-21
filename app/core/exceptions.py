"""Typed exception hierarchy.

The hierarchy is intentionally shallow – everything inherits from
:class:`FarmPilotError` so that the executor / retry layer can distinguish
"our" failures from unexpected ones.
"""
from __future__ import annotations


class FarmPilotError(Exception):
    """Base class for all FarmPilotAI errors."""


# --- configuration ---
class ConfigurationError(FarmPilotError):
    """Bad or missing configuration."""


# --- browser ---
class BrowserError(FarmPilotError):
    """Anything browser/Playwright related."""


class SelectorNotFoundError(BrowserError):
    """A self-healing selector exhausted every fallback."""


class WalletExtensionError(BrowserError):
    """MetaMask / Rabby extension failed to initialise or sign."""


# --- wallet / chain ---
class WalletError(FarmPilotError):
    """Generic wallet error."""


class RiskRejectedError(WalletError):
    """A transaction was rejected by the risk analyser."""


class ChainConnectionError(WalletError):
    """RPC unreachable / mismatched chainId."""


# --- task engine ---
class TaskError(FarmPilotError):
    """Generic task failure."""


class RetryableError(TaskError):
    """Marker class: the retry layer will reattempt these."""


class FatalTaskError(TaskError):
    """Marker class: the retry layer must NOT reattempt these."""


class TaskTimeoutError(RetryableError):
    """The task exceeded its allotted time budget."""


# --- planning ---
class PlanningError(FarmPilotError):
    """Planner could not build a viable plan."""


class StrategyError(FarmPilotError):
    """Strategy generation failed."""
