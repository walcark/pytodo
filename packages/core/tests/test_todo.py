from datetime import datetime

import pytest

from neverland.core.todo import Todo, TodoState, parse_markdown, sort_key


def test_roundtrip_markdown():
    t = Todo(
        id="20260705-143201-a3f2",
        title="Renew passport",
        state=TodoState.NEXT,
        context="@phone",
        area="admin",
        project="20260705-000000-0001",
        created=datetime(2026, 7, 5, 14, 32, 1),
        body="Some notes.",
    )
    parsed = parse_markdown(t.to_markdown(), todo_id=t.id)

    assert parsed.title == "Renew passport"
    assert parsed.state is TodoState.NEXT
    assert parsed.context == "@phone"
    assert parsed.area == "admin"
    assert parsed.project == "20260705-000000-0001"
    assert parsed.created == datetime(2026, 7, 5, 14, 32, 1)
    assert parsed.body == "Some notes."


def test_waiting_roundtrip():
    t = Todo(id="1", title="Quote", state=TodoState.WAITING, waiting_on="Marc")
    parsed = parse_markdown(t.to_markdown(), todo_id="1")
    assert parsed.state is TodoState.WAITING
    assert parsed.waiting_on == "Marc"


def test_defaults_to_inbox_with_bare_frontmatter():
    todo = parse_markdown('---\ntitle: "Bare"\n---\n', todo_id="x")
    assert todo.state is TodoState.INBOX
    assert todo.context is None
    assert todo.area is None
    assert todo.project is None
    assert todo.body == ""


def test_unknown_state_falls_back_to_inbox():
    # A todo must never be lost to an unreadable state: inbox puts it back in
    # front of you at the next clarify rather than hiding it.
    todo = parse_markdown('---\ntitle: "Odd"\nstate: bogus\n---\n', todo_id="x")
    assert todo.state is TodoState.INBOX


@pytest.mark.parametrize(
    "text",
    [
        "no front matter at all",
        "---\ntitle: x\n",  # unterminated
        "---\narea: admin\n---\n",  # no title
    ],
)
def test_parse_errors(text):
    with pytest.raises(ValueError):
        parse_markdown(text, todo_id="x")


def test_sort_key_is_oldest_first():
    old = Todo(id="1", title="b", created=datetime(2026, 1, 1))
    recent = Todo(id="2", title="a", created=datetime(2026, 7, 1))
    assert sorted([recent, old], key=sort_key) == [old, recent]


def test_sort_key_puts_undated_last():
    dated = Todo(id="1", title="a", created=datetime(2026, 7, 1))
    undated = Todo(id="2", title="a")
    assert sorted([undated, dated], key=sort_key) == [dated, undated]


def test_sort_key_breaks_ties_on_title():
    stamp = datetime(2026, 7, 1)
    b = Todo(id="1", title="Beta", created=stamp)
    a = Todo(id="2", title="alpha", created=stamp)
    assert sorted([b, a], key=sort_key) == [a, b]
