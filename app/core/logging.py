"""Structured logging.

We use :mod:`structlog` so that every log record carries the same context
fields (task_id, wallet, project, …) regardless of whether the underlying
sink is plain-text (dev) or JSON (prod).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import Processor

from app.config import LoggingSettings

_CONFIGURED = False


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def configure_logging(settings: LoggingSettings) -> None:
    """Idempotent global logging configuration.

    Safe to call from FastAPI lifespan, CLI scripts, tests, etc.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.file:
        _ensure_dir(settings.file)
        handlers.append(logging.FileHandler(settings.file, encoding="utf-8"))

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.json_output:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a logger bound with ``initial_context`` baked in."""
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
