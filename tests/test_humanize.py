from __future__ import annotations

import pytest

from app.core.humanize import Humanizer


def test_next_delay_in_range():
    h = Humanizer(min_ms=10, max_ms=30)
    samples = [h.next_delay_ms() for _ in range(200)]
    assert all(10 <= s <= 30 for s in samples)


def test_keystroke_delay_within_bounds():
    h = Humanizer(min_ms=10, max_ms=30)
    samples = [h.keystroke_delay_ms() for _ in range(500)]
    assert all(50 < s < 1000 for s in samples)


@pytest.mark.asyncio
async def test_sleep_returns_quickly():
    h = Humanizer(min_ms=1, max_ms=2)
    await h.sleep()
