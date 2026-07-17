import builtins

import pytest

from pytodo import prompt


def test_text_input_fallback_without_gum(monkeypatch):
    """gum absent -> fall back to input()."""
    monkeypatch.setattr(prompt, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "my todo")
    assert prompt.text_input("placeholder") == "my todo"


def test_confirm_fallback_yes(monkeypatch):
    monkeypatch.setattr(prompt, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    assert prompt.confirm("delete?") is True


def test_confirm_fallback_no(monkeypatch):
    monkeypatch.setattr(prompt, "_has", lambda tool: False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert prompt.confirm("delete?") is False


def test_confirm_fallback_cancel(monkeypatch):
    monkeypatch.setattr(prompt, "_has", lambda tool: False)

    def _raise(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", _raise)
    with pytest.raises(prompt.Cancelled):
        prompt.confirm("delete?")


def test_ensure_fzf_raises_when_absent(monkeypatch):
    monkeypatch.setattr(prompt, "_has", lambda tool: False)
    with pytest.raises(prompt.MissingTool, match="fzf"):
        prompt.ensure_fzf()


def test_format_line_shows_horizon():
    from pytodo.todo import Todo

    t = Todo(id="1", title="Pay", category="admin", urgency="now", horizon="week")
    line = prompt.format_line(t)
    assert line.startswith("[admin] [now] Pay")
    assert "(week)" in line
