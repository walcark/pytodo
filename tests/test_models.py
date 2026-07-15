from datetime import date, datetime

import pytest

from pytodo.models import Todo, make_sort_key, parse_markdown

URGENCY = ["now", "soon", "someday"]
HORIZON = ["today", "week", "month"]
SORT_KEY = make_sort_key(URGENCY, HORIZON)


def test_frontmatter_roundtrip():
    todo = Todo(
        id="20260705-143201-a3f2",
        title="Renew passport",
        category="admin",
        urgency="soon",
        horizon="month",
        deadline=date(2026, 8, 15),
        created=datetime(2026, 7, 5, 14, 32, 1),
        body="details\nline 2",
    )
    text = todo.to_markdown()
    parsed = parse_markdown(text, todo_id=todo.id)
    assert parsed.title == "Renew passport"
    assert parsed.category == "admin"
    assert parsed.urgency == "soon"
    assert parsed.horizon == "month"
    assert parsed.deadline == date(2026, 8, 15)
    assert parsed.created == datetime(2026, 7, 5, 14, 32, 1)
    assert parsed.completed is None
    assert parsed.body == "details\nline 2"


def test_parse_minimal_no_body():
    text = "---\ntitle: Buy bread\ncategory: home\n---\n"
    todo = parse_markdown(text, todo_id="x")
    assert todo.title == "Buy bread"
    assert todo.body == ""
    assert todo.horizon is None
    assert todo.deadline is None


def test_parse_missing_title_raises():
    with pytest.raises(ValueError, match="title"):
        parse_markdown("---\ncategory: home\n---\n", todo_id="x")


def test_parse_missing_frontmatter_raises():
    with pytest.raises(ValueError):
        parse_markdown("no front matter", todo_id="x")


def test_sort_by_urgency_then_deadline():
    now = Todo(id="1", title="a", category="c", urgency="now")
    soon_early = Todo(
        id="2", title="b", category="c", urgency="soon", deadline=date(2026, 1, 1)
    )
    soon_late = Todo(
        id="3", title="c", category="c", urgency="soon", deadline=date(2026, 12, 1)
    )
    someday = Todo(id="4", title="d", category="c", urgency="someday")

    todos = [someday, soon_late, now, soon_early]
    ordered = sorted(todos, key=SORT_KEY)
    assert [t.id for t in ordered] == ["1", "2", "3", "4"]


def test_dated_before_undated_same_urgency():
    dated = Todo(
        id="d", title="a", category="c", urgency="soon", deadline=date(2026, 5, 1)
    )
    undated = Todo(id="u", title="b", category="c", urgency="soon")
    ordered = sorted([undated, dated], key=SORT_KEY)
    assert [t.id for t in ordered] == ["d", "u"]


def test_sort_order_follows_config():
    """Urgency rank is the position in the configured list, not a hardcoded map."""
    a = Todo(id="a", title="a", category="c", urgency="low")
    b = Todo(id="b", title="b", category="c", urgency="high")
    # "high" first in the configured order -> sorts before "low".
    key = make_sort_key(["high", "low"], HORIZON)
    ordered = sorted([a, b], key=key)
    assert [t.id for t in ordered] == ["b", "a"]


def test_overdue():
    t = Todo(id="1", title="a", category="c", deadline=date(2020, 1, 1))
    assert t.is_overdue(today=date(2026, 1, 1)) is True
    t2 = Todo(id="2", title="b", category="c", deadline=date(2030, 1, 1))
    assert t2.is_overdue(today=date(2026, 1, 1)) is False
    # a completed todo is never overdue
    t.completed = datetime(2026, 1, 1)
    assert t.is_overdue(today=date(2026, 1, 1)) is False
