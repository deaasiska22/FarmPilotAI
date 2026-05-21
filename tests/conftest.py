"""Pytest configuration & shared fixtures."""
from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("AI_PROVIDER", "none")
os.environ.setdefault("WALLET_EXTENSION", "none")
# Use an in-memory SQLite DB so tests are fast and isolated.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["EXEC_HUMAN_DELAY_MIN_MS"] = "1"
os.environ["EXEC_HUMAN_DELAY_MAX_MS"] = "2"
os.environ["EXEC_RETRY_BACKOFF_BASE_MS"] = "1"
os.environ["EXEC_RETRY_BACKOFF_MAX_MS"] = "2"
os.environ["EXEC_RETRY_MAX_ATTEMPTS"] = "3"

# Clear any cached Settings singleton so the env above takes effect.
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def container():
    from app.container import Container, set_container

    c = Container()
    await c.db.create_all()
    set_container(c)
    try:
        yield c
    finally:
        await c.aclose()
        set_container(None)
