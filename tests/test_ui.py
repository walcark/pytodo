import builtins

import pytest

from pytodo import ui


def test_text_input_fallback_without_gum(monkeypatch):
    """gum absent -> fall back to input()."""
    monkeypatch.setattr(ui, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "my todo")
    assert ui.text_input("placeholder") == "my todo"


def test_confirm_fallback_yes(monkeypatch):
    monkeypatch.setattr(ui, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    assert ui.confirm("delete?") is True


def test_confirm_fallback_no(monkeypatch):
    monkeypatch.setattr(ui, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert ui.confirm("delete?") is False


def test_confirm_fallback_cancel(monkeypatch):
    monkeypatch.setattr(ui, "_has", lambda tool: False)

    def _raise(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", _raise)
    with pytest.raises(ui.Cancelled):
        ui.confirm("delete?")


def test_ensure_fzf_raises_when_absent(monkeypatch):
    monkeypatch.setattr(ui, "_has", lambda tool: False)
    with pytest.raises(ui.MissingTool, match="fzf"):
        ui.ensure_fzf()


def test_format_line_with_overdue():
    from datetime import date

    from pytodo.models import Todo

    t = Todo(
        id="1", title="Pay", category="admin", urgency="now", deadline=date(2020, 1, 1)
    )
    line = ui.format_line(t)
    assert line.startswith("[admin] [now] Pay")
    assert "⚠" in line
