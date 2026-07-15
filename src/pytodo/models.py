"""Todo model and markdown front matter (de)serialization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml


@dataclass
class Todo:
    """A single todo, stored as one markdown file with a YAML front matter.

    The identifier (``id``) is the file name without extension. It is set once
    at creation time and never changes; moving the file to ``done/`` keeps the
    same name.

    Attributes
    ----------
    id : str
        Unique identifier, also the file stem (``YYYYMMDD-HHMMSS-<hex>``).
    title : str
        One-line title, mandatory.
    category : str
        Category name, constrained by the repo config.
    urgency : str
        One of ``now``, ``soon`` or ``someday``.
    horizon : str or None
        Optional soft horizon (``today``, ``week`` or ``month``).
    deadline : datetime.date or None
        Optional hard deadline.
    created : datetime.datetime or None
        Creation timestamp.
    completed : datetime.datetime or None
        Completion timestamp, filled when the file moves to ``done/``.
    body : str
        Optional markdown body.
    path : pathlib.Path or None
        On-disk location of the file, when known.
    """

    id: str
    title: str
    category: str
    urgency: str = "soon"
    horizon: str | None = None
    deadline: date | None = None
    created: datetime | None = None
    completed: datetime | None = None
    body: str = ""
    path: Path | None = None

    # -- Serialization ----------------------------------------------------

    def to_frontmatter(self) -> dict:
        """Return the front matter as an ordered mapping."""
        return {
            "title": self.title,
            "category": self.category,
            "urgency": self.urgency,
            "horizon": self.horizon,
            "deadline": self.deadline,
            "created": self.created,
            "completed": self.completed,
        }

    def to_markdown(self) -> str:
        """Render the todo as a markdown document.

        Returns
        -------
        str
            A ``---`` delimited YAML front matter followed by the optional
            markdown body.
        """
        fm = yaml.safe_dump(
            self.to_frontmatter(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).rstrip("\n")
        body = self.body.strip("\n")
        text = f"---\n{fm}\n---\n"
        if body:
            text += f"\n{body}\n"
        return text

    # -- Sort keys --------------------------------------------------------

    def is_overdue(self, today: date | None = None) -> bool:
        """Return whether the todo has a passed, still-open deadline.

        Parameters
        ----------
        today : datetime.date, optional
            Reference date, defaults to :func:`datetime.date.today`.

        Returns
        -------
        bool
            ``True`` if the deadline is strictly before ``today`` and the todo
            is not completed yet.
        """
        today = today or date.today()
        return (
            self.deadline is not None
            and self.deadline < today
            and self.completed is None
        )


def make_sort_key(urgency: list[str], horizon: list[str]) -> Callable[[Todo], tuple]:
    """Build an in-category sort key bound to the repo's value orderings.

    Both ``urgency`` and ``horizon`` are ordered lists coming from the repo
    config: the rank of a value is its index (position 0 is the most urgent /
    nearest). Todos are ordered by urgency first, then dated-before-undated,
    then by ascending deadline and horizon. Unknown values sort last.

    Parameters
    ----------
    urgency : list of str
        Allowed urgency values, most urgent first.
    horizon : list of str
        Allowed horizon values, nearest first.

    Returns
    -------
    callable
        A function suitable for ``sorted(todos, key=...)``.
    """

    def rank(value: str | None, order: list[str]) -> int:
        if value is None or value not in order:
            return len(order)  # unknown / unset values sort last
        return order.index(value)

    def key(todo: Todo) -> tuple:
        deadline = todo.deadline or date.max
        has_no_date = todo.deadline is None and todo.horizon is None
        return (
            rank(todo.urgency, urgency),
            has_no_date,
            deadline,
            rank(todo.horizon, horizon),
            todo.title.lower(),
        )

    return key


def _coerce_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _coerce_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def parse_markdown(text: str, *, todo_id: str, path: Path | None = None) -> Todo:
    """Parse a todo file (front matter plus body) into a :class:`Todo`.

    Parameters
    ----------
    text : str
        Full file content.
    todo_id : str
        Identifier to assign (typically the file stem).
    path : pathlib.Path, optional
        On-disk location, stored on the returned object.

    Returns
    -------
    Todo
        The parsed todo.

    Raises
    ------
    ValueError
        If the front matter is missing, malformed, or lacks a ``title``.
    """
    if not text.startswith("---"):
        raise ValueError("missing front matter (file must start with '---')")

    # Split on the second standalone '---' line.
    parts = text.split("\n")
    if parts[0].strip() != "---":
        raise ValueError("malformed front matter")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("unterminated front matter (missing closing '---')")

    fm_text = "\n".join(parts[1:end])
    body = "\n".join(parts[end + 1 :]).strip("\n")
    fm = yaml.safe_load(fm_text) or {}

    title = fm.get("title")
    if not title:
        raise ValueError("mandatory 'title' field is missing")

    return Todo(
        id=todo_id,
        title=str(title),
        category=str(fm.get("category", "")),
        urgency=str(fm.get("urgency", "soon")),
        horizon=(fm.get("horizon") or None),
        deadline=_coerce_date(fm.get("deadline")),
        created=_coerce_datetime(fm.get("created")),
        completed=_coerce_datetime(fm.get("completed")),
        body=body,
        path=path,
    )


def load_todo(path: Path) -> Todo:
    """Read and parse a todo file from disk.

    Parameters
    ----------
    path : pathlib.Path
        File to read.

    Returns
    -------
    Todo
        The parsed todo, with ``path`` set.
    """
    return parse_markdown(
        path.read_text(encoding="utf-8"), todo_id=path.stem, path=path
    )
