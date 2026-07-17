import os

from pytodo import view


def test_terminal_width_uses_ioctl_not_columns(monkeypatch):
    """Width comes from the ioctl (real window), not COLUMNS (may be stale)."""
    monkeypatch.setenv("COLUMNS", "999")
    monkeypatch.setattr(os, "get_terminal_size", lambda fd: os.terminal_size((70, 40)))
    assert view.terminal_width() == 70


def test_terminal_width_fallback_when_not_a_tty(monkeypatch):
    def boom(fd):
        raise OSError("not a tty")

    monkeypatch.setattr(os, "get_terminal_size", boom)
    assert view.terminal_width(default=80) == 80
