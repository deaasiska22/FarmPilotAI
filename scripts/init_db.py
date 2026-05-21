"""Idempotent DB bootstrap. Safe to run multiple times.

Usage:

    $ python -m scripts.init_db
"""
from __future__ import annotations

import asyncio

from app.container import get_container
from app.core.logging import configure_logging, get_logger


async def main() -> None:
    container = get_container()
    configure_logging(container.settings.log)
    log = get_logger("init_db")
    await container.db.create_all()
    log.info("db.ready", url=container.settings.db.url)
    await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
