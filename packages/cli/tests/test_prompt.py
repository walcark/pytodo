import builtins

import pytest

from pytodo.cli import prompt


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


def test_format_line_leads_with_state_and_context():
    from pytodo.core.todo import Todo, TodoState

    t = Todo(id="1", title="Pay", state=TodoState.NEXT, context="@phone", area="admin")
    assert prompt.format_line(t) == "[next] [@phone] Pay (admin)"


def test_format_line_omits_unset_fields():
    from pytodo.core.todo import Todo

    assert prompt.format_line(Todo(id="1", title="Bare")) == "[inbox] Bare"
