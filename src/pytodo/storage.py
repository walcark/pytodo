"""Filesystem operations on the todo tree (git-independent)."""

from __future__ import annotations

import secrets
from datetime import date, datetime
from pathlib import Path

from .config import DONE_DIRNAME, TODOS_DIRNAME
from .models import Todo, load_todo


def todos_dir(data_dir: Path) -> Path:
    """Return the ``todos/`` directory for a data repo."""
    return data_dir / TODOS_DIRNAME


def done_dir(data_dir: Path) -> Path:
    """Return the ``done/`` directory for a data repo."""
    return data_dir / DONE_DIRNAME


def new_todo_id(now: datetime | None = None) -> str:
    """Return a fresh todo id.

    Parameters
    ----------
    now : datetime.datetime, optional
        Creation time, defaults to :func:`datetime.datetime.now`.

    Returns
    -------
    str
        ``YYYYMMDD-HHMMSS-<4 hex>``: creation timestamp plus a random suffix
        to avoid collisions.
    """
    now = now or datetime.now()
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _list_dir(directory: Path) -> list[Todo]:
    if not directory.exists():
        return []
    return [load_todo(path) for path in sorted(directory.glob("*.md"))]


def list_active(data_dir: Path) -> list[Todo]:
    """Return the active todos (files under ``todos/``)."""
    return _list_dir(todos_dir(data_dir))


def list_done(data_dir: Path) -> list[Todo]:
    """Return the archived todos (files under ``done/``)."""
    return _list_dir(done_dir(data_dir))


def create_todo(
    data_dir: Path,
    *,
    title: str,
    category: str,
    urgency: str = "soon",
    horizon: str | None = None,
    deadline: date | None = None,
    now: datetime | None = None,
) -> Todo:
    """Create a new active todo file.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    title : str
        Todo title.
    category : str
        Category name.
    urgency : str, optional
        Urgency value, defaults to ``soon``.
    horizon : str or None, optional
        Optional horizon.
    deadline : datetime.date or None, optional
        Optional hard deadline.
    now : datetime.datetime, optional
        Creation time, defaults to now.

    Returns
    -------
    Todo
        The created todo, with ``path`` set to the new file.
    """
    now = now or datetime.now()
    todo_id = new_todo_id(now)
    directory = todos_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{todo_id}.md"
    todo = Todo(
        id=todo_id,
        title=title.strip(),
        category=category,
        urgency=urgency,
        horizon=horizon,
        deadline=deadline,
        created=now.replace(microsecond=0),
        path=path,
    )
    path.write_text(todo.to_markdown(), encoding="utf-8")
    return todo


def move_to_done(todo: Todo, data_dir: Path, *, now: datetime | None = None) -> Path:
    """Move a todo file to ``done/`` and stamp its completion time.

    Parameters
    ----------
    todo : Todo
        Todo to complete; its ``path`` must exist.
    data_dir : pathlib.Path
        Data repo root.
    now : datetime.datetime, optional
        Completion time, defaults to now.

    Returns
    -------
    pathlib.Path
        The new file location under ``done/``.

    Raises
    ------
    FileNotFoundError
        If the source file does not exist.
    """
    now = now or datetime.now()
    src = todo.require_path()
    dest_dir = done_dir(data_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{todo.id}.md"
    todo.completed = now.replace(microsecond=0)
    dest.write_text(todo.to_markdown(), encoding="utf-8")
    src.unlink()
    todo.path = dest
    return dest


def delete_todo(todo: Todo) -> None:
    """Permanently delete a todo file.

    Parameters
    ----------
    todo : Todo
        Todo to delete; its ``path`` must exist.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    todo.require_path().unlink()
