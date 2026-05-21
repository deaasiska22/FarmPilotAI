from __future__ import annotations

import pytest

from app.core.exceptions import FatalTaskError, RetryableError
from app.core.retry import RetryPolicy, with_retry


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        return 42

    out = await with_retry(op, policy=RetryPolicy(max_attempts=3, base_ms=1, max_ms=2))
    assert out == 42
    assert calls == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RetryableError("transient")
        return "ok"

    out = await with_retry(op, policy=RetryPolicy(max_attempts=5, base_ms=1, max_ms=2))
    assert out == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_exhausts_retries():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise RetryableError("nope")

    with pytest.raises(RetryableError):
        await with_retry(op, policy=RetryPolicy(max_attempts=3, base_ms=1, max_ms=2))
    assert calls == 3


@pytest.mark.asyncio
async def test_fatal_never_retried():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise FatalTaskError("burn")

    with pytest.raises(FatalTaskError):
        await with_retry(op, policy=RetryPolicy(max_attempts=4, base_ms=1, max_ms=2))
    assert calls == 1


@pytest.mark.asyncio
async def test_unrelated_exception_propagates_without_retry():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await with_retry(op, policy=RetryPolicy(max_attempts=4, base_ms=1, max_ms=2))
    assert calls == 1
