"""Background git poller: keeps the working copy fresh while the server runs.

The server is one more git writer, coordinated with the CLI and other devices
through the remote. A long-running process must therefore *pull* on a timer to
reflect changes made elsewhere (and push its own). This reuses
:func:`neverland.core.vcs.background_flush`, which already pulls, pushes, drains and
takes the shared lock, so the poller is only the "every N seconds" wrapper.

The blocking git call runs in a threadpool so it never stalls the event loop,
and every failure is swallowed: a dead poller is worse than a missed tick.
"""

from __future__ import annotations

import asyncio
import logging

from neverland.core import service, vcs
from neverland.core.vocabulary import load_repo_config

from .config import ServerConfig

log = logging.getLogger("neverland.server.poller")


def _tick(config: ServerConfig) -> None:
    """One poller cycle: materialize due routines, then pull/push.

    Materializing here is what makes recurring todos appear on their day for a
    long-running server without any cron: it is idempotent, so running it every
    interval only acts when a routine actually comes due.
    """
    repo = load_repo_config(config.data_dir)
    repo.sync_auto = False  # the flush below owns the network sync
    service.materialize_routines(config.data_dir, repo)
    vcs.background_flush(config.data_dir)


async def run_poller(config: ServerConfig, stop: asyncio.Event) -> None:
    """Sync the data repo every ``config.poll_interval`` seconds until ``stop``.

    Parameters
    ----------
    config : ServerConfig
        Active configuration (``data_dir`` and ``poll_interval``).
    stop : asyncio.Event
        Set by the app's shutdown to end the loop promptly.
    """
    while not stop.is_set():
        try:
            await asyncio.to_thread(_tick, config)
        except Exception:
            log.exception("poller tick failed; will retry next tick")
        try:
            await asyncio.wait_for(stop.wait(), timeout=config.poll_interval)
        except TimeoutError:
            pass  # interval elapsed: sync again
