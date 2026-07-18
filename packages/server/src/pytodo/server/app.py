"""FastAPI application factory.

:func:`create_app` turns a :class:`ServerConfig` into a ready app. It is the
reuse surface: another project can build its own config, call this, and mount
the result, or add its own routes on top.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import api
from .config import ServerConfig
from .poller import run_poller


def create_app(config: ServerConfig) -> FastAPI:
    """Build the pytodo FastAPI app for ``config``.

    The background git poller runs for the app's lifetime when
    ``config.poll_interval`` is positive (set it to 0 to disable, e.g. in tests).

    Parameters
    ----------
    config : ServerConfig
        Resolved server configuration; stored on ``app.state.config`` for the
        route dependencies to read.

    Returns
    -------
    fastapi.FastAPI
        The application, with the API mounted under ``/api``.
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

    app = FastAPI(title="pytodo", version="0.3.0", lifespan=lifespan)
    app.state.config = config
    app.include_router(api.router)
    return app
