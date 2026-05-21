"""FastAPI entrypoint."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.container import get_container
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = get_container()
    configure_logging(container.settings.log)
    log = get_logger("api")
    await container.db.create_all()
    log.info("api.startup", env=container.settings.app_env, version=__version__)
    try:
        yield
    finally:
        await container.aclose()
        log.info("api.shutdown")


def create_app() -> FastAPI:
    container = get_container()
    app = FastAPI(
        title=container.settings.app_name,
        version=__version__,
        description="Autonomous Web3 farming agent.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(api_router)
    return app


app = create_app()
