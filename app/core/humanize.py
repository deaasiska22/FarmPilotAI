"""Human-like timing & interaction helpers.

Anti-sybil heuristics expect:

* Variable inter-action delays (not constant).
* Realistic typing cadence with occasional pauses.
* Mouse movement before clicks (handled in the browser layer).

This module exposes pure helpers and a small ``Humanizer`` class so callers
can inject mocked clocks in tests.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from app.config import ExecutionSettings


@dataclass(slots=True)
class Humanizer:
    """Generates and (optionally) sleeps for human-like durations."""

    min_ms: int
    max_ms: int
    rng: random.Random = random.Random()

    @classmethod
    def from_settings(cls, settings: ExecutionSettings) -> Humanizer:
        return cls(min_ms=settings.human_delay_min_ms, max_ms=settings.human_delay_max_ms)

    # -- core -------------------------------------------------------------
    def next_delay_ms(self, scale: float = 1.0) -> int:
        """Return a randomised delay in milliseconds.

        ``scale`` lets callers temporarily widen or narrow the window
        (e.g. ``scale=0.3`` for keystroke gaps, ``scale=3`` for "thinking").
        """
        lo = max(1, int(self.min_ms * scale))
        hi = max(lo + 1, int(self.max_ms * scale))
        return self.rng.randint(lo, hi)

    async def sleep(self, scale: float = 1.0) -> None:
        await asyncio.sleep(self.next_delay_ms(scale) / 1000.0)

    # -- typing cadence ---------------------------------------------------
    def keystroke_delay_ms(self) -> int:
        """Per-keystroke delay used by the browser layer when typing text."""
        # 60-220ms with occasional 600ms "think" pauses
        if self.rng.random() < 0.04:
            return self.rng.randint(450, 900)
        return self.rng.randint(60, 220)

    def thinking_pause_ms(self) -> int:
        return self.rng.randint(self.max_ms, self.max_ms * 3)
