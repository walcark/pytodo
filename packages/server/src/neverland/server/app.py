"""FastAPI application factory.

:func:`create_app` turns a :class:`ServerConfig` into a ready app. It is the
reuse surface: another project can build its own config, call this, and mount
the result, or add its own routes on top.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import api
from .config import ServerConfig
from .poller import run_poller

# The compiled SPA (packages/server/frontend built by `pixi run build-web`).
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: ServerConfig, static_dir: Path | None = None) -> FastAPI:
    """Build the neverland FastAPI app for ``config``.

    The background git poller runs for the app's lifetime when
    ``config.poll_interval`` is positive (set it to 0 to disable, e.g. in tests).
    The web UI is served from ``static_dir`` when it has been built.

    Parameters
    ----------
    config : ServerConfig
        Resolved server configuration; stored on ``app.state.config`` for the
        route dependencies to read.
    static_dir : pathlib.Path, optional
        Directory of the compiled SPA. Defaults to the packaged one.

    Returns
    -------
    fastapi.FastAPI
        The application: API under ``/api``, the SPA under ``/``.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task = None
        if config.poll_interval > 0:
            task = asyncio.create_task(run_poller(config, stop))
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task

    app = FastAPI(title="neverland", version="0.4.0", lifespan=lifespan)
    app.state.config = config
    app.include_router(api.router)
    _mount_web(app, static_dir or DEFAULT_STATIC_DIR)
    return app


def _mount_web(app: FastAPI, static_dir: Path) -> None:
    """Serve the SPA at ``/``, or a clear hint if it has not been built.

    Mounted after the API router, so ``/api`` and ``/docs`` keep precedence over
    the catch-all static mount.
    """
    if (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
        return

    @app.get("/", include_in_schema=False)
    def _web_not_built() -> None:
        raise HTTPException(
            status_code=503,
            detail="Web UI not built. Run `pixi run build-web`.",
        )
