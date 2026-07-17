"""Todo model and markdown front matter (de)serialization.

The model follows GTD (see ``docs/model.md``). The two axes that matter are
kept strictly separate: ``area`` is a domain of responsibility ("which part of
my life"), ``context`` is a precondition for acting ("what do I need in order
to do this right now"). They are orthogonal, and only ``context`` answers the
question you actually ask when choosing what to do next.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

import yaml


class TodoState(Enum):
    """Engagement level of a todo.

    ``INBOX`` is captured but unclarified. ``NEXT`` is a physical action you
    can start right now given its context. ``WAITING`` is blocked on someone
    else, so it stays out of the list you pick from. ``SOMEDAY`` is not
    committed to, and stays out for the same reason: a list where everything
    is doable is the only kind you keep trusting.
    """

    INBOX = "inbox"
    NEXT = "next"
    WAITING = "waiting"
    SOMEDAY = "someday"
    DONE = "done"


@dataclass
class Todo:
    """A single todo, stored as one markdown file with a YAML front matter.

    The identifier (``id``) is the file name without extension. It is set once
    at creation time and never changes; moving the file to ``done/`` keeps the
    same name, and a change of ``state`` never moves the file at all.

    Attributes
    ----------
    id : str
        Unique identifier, also the file stem (``YYYYMMDD-HHMMSS-<hex>``).
    title : str
        One-line title, mandatory. For a ``NEXT`` todo it should be a physical,
        visible next step ("Call the plumber about the leak"), not a topic.
    state : TodoState
        Engagement level. Captured todos start at ``INBOX``.
    context : str or None
        What you need in order to act (``@computer``, ``@phone``...). ``None``
        while unclarified; a ``NEXT`` todo without one is unselectable, which
        ``todo review`` reports.
    area : str or None
        Domain of responsibility, constrained by the repo config.
    project : str or None
        Id of the project this action belongs to, or ``None`` when standalone.
    waiting_on : str or None
        Who or what is blocking, when ``state`` is ``WAITING``.
    created : datetime.datetime or None
        Creation timestamp. Also the sort key: lists run oldest first.
    completed : datetime.datetime or None
        Completion timestamp, filled when the file moves to ``done/``.
    body : str
        Optional markdown body.
    path : pathlib.Path or None
        On-disk location of the file, when known.
    """

    id: str
    title: str
    state: TodoState = TodoState.INBOX
    context: str | None = None
    area: str | None = None
    project: str | None = None
    waiting_on: str | None = None
    created: datetime | None = None
    completed: datetime | None = None
    body: str = ""
    path: Path | None = None

    # -- Serialization ----------------------------------------------------

    def to_frontmatter(self) -> dict:
        """Return the front matter as an ordered mapping."""
        return {
            "title": self.title,
            "state": self.state.value,
            "context": self.context,
            "area": self.area,
            "project": self.project,
            "waiting_on": self.waiting_on,
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

    def require_path(self) -> Path:
        """Return the on-disk path, raising if it is unset or missing.

        Returns
        -------
        pathlib.Path
            The existing file location.

        Raises
        ------
        FileNotFoundError
            If the todo has no path or the file does not exist.
        """
        if self.path is None or not self.path.exists():
            raise FileNotFoundError(f"todo not found: {self.id}")
        return self.path


def sort_key(todo: Todo) -> tuple:
    """Return the ordering key for a todo: oldest first, then title.

    Nothing ranks todos any more now that ``urgency`` and ``horizon`` are gone.
    Age is the only honest signal left, and it has the right property: an old
    item taps you on the shoulder. Any other order would smuggle a priority
    field back in, which is what GTD says not to do (priority is decided at
    engage time, and ``todo day`` is where that happens).

    Todos without a ``created`` stamp sort last.

    Parameters
    ----------
    todo : Todo
        The todo to key.

    Returns
    -------
    tuple
        A key suitable for ``sorted(todos, key=sort_key)``.
    """
    return (todo.created is None, todo.created or datetime.max, todo.title.lower())


def _coerce_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _coerce_state(value) -> TodoState:
    """Return the parsed state, falling back to ``INBOX`` on an unknown value.

    An unreadable state must not lose the todo: ``INBOX`` puts it back in front
    of you at the next ``todo clarify`` rather than hiding it in a list you
    never look at.
    """
    try:
        return TodoState(str(value))
    except ValueError:
        return TodoState.INBOX


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
        state=_coerce_state(fm.get("state", TodoState.INBOX.value)),
        context=(fm.get("context") or None),
        area=(fm.get("area") or None),
        project=(fm.get("project") or None),
        waiting_on=(fm.get("waiting_on") or None),
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
