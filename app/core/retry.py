"""Retry / recovery primitives.

We intentionally don't wire tenacity directly into business code – we expose
``with_retry`` / ``RetryPolicy`` so callers can choose backoff parameters per
operation, and so we can attach domain hooks (logging, metrics, kill-switch).
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.core.exceptions import FatalTaskError, RetryableError
from app.core.logging import get_logger

T = TypeVar("T")

logger = get_logger("retry")


@dataclass(slots=True)
class RetryPolicy:
    """Exponential backoff with jitter.

    Attributes
    ----------
    max_attempts:
        Total attempts (including the first try). Must be >= 1.
    base_ms / max_ms:
        Backoff lower / upper bound in milliseconds.
    jitter:
        Fractional jitter applied on top of computed delay (0..1).
    retry_on:
        Tuple of exception classes considered retryable. By default we retry
        only on :class:`RetryableError` so callers must opt-in by raising it.
    """

    max_attempts: int = 4
    base_ms: int = 500
    max_ms: int = 15_000
    jitter: float = 0.35
    retry_on: tuple[type[BaseException], ...] = (RetryableError,)

    def _delay_for(self, attempt: int) -> float:
        # attempt is 1-indexed; first retry uses base, then 2x, 4x, ...
        raw_ms = min(self.base_ms * (2 ** (attempt - 1)), self.max_ms)
        if self.jitter > 0:
            raw_ms *= 1 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, raw_ms / 1000.0)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    op_name: str = "operation",
) -> T:
    """Execute ``fn`` honouring ``policy``.

    ``fn`` must be a no-arg async callable; wrap with ``functools.partial`` /
    ``lambda`` to bind state from the caller. We never sleep before the first
    attempt and never sleep after the final failed attempt.
    """
    policy = policy or RetryPolicy()
    if policy.max_attempts < 1:
        raise ValueError("RetryPolicy.max_attempts must be >= 1")

    last_exc: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except FatalTaskError:
            # explicit fatal – never retry
            raise
        except policy.retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= policy.max_attempts:
                logger.error(
                    "retry.exhausted",
                    op=op_name,
                    attempt=attempt,
                    max_attempts=policy.max_attempts,
                    error=str(exc),
                )
                raise
            delay = policy._delay_for(attempt)
            logger.warning(
                "retry.attempt_failed",
                op=op_name,
                attempt=attempt,
                next_delay_s=round(delay, 3),
                error=str(exc),
            )
            await asyncio.sleep(delay)
        except Exception:
            # not on the retry list – escalate immediately
            raise

    # unreachable, but mypy doesn't know that
    assert last_exc is not None
    raise last_exc
