import asyncio

from pytodo.server import poller
from pytodo.server.config import ServerConfig


def _drive(config, ready_after=0.06):
    """Run the poller briefly, then stop it, from a sync test."""

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(poller.run_poller(config, stop))
        await asyncio.sleep(ready_after)
        stop.set()
        await task

    asyncio.run(scenario())


def test_poller_syncs_on_each_tick(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(poller.vcs, "background_flush", calls.append)
    _drive(ServerConfig(data_dir=tmp_path, poll_interval=0.01))
    assert calls and all(p == tmp_path for p in calls)


def test_poller_survives_sync_errors(monkeypatch, tmp_path):
    def boom(_data_dir):
        raise RuntimeError("git down")

    monkeypatch.setattr(poller.vcs, "background_flush", boom)
    # Must not raise: a failing sync is logged and retried, never fatal.
    _drive(ServerConfig(data_dir=tmp_path, poll_interval=0.01))


def test_poller_stops_promptly(monkeypatch, tmp_path):
    monkeypatch.setattr(poller.vcs, "background_flush", lambda _d: None)
    # A long interval must not delay shutdown: stop.wait() short-circuits it.
    _drive(ServerConfig(data_dir=tmp_path, poll_interval=3600), ready_after=0.03)
