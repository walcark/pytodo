"""Filesystem operations on the todo tree (git-independent).

Owns the on-disk layout of the data repo, hence the directory names live here:
:mod:`pytodo.vcs` scaffolds the layout that this module reads.

One markdown file per todo, per project and per day. A todo's ``state`` is a
front matter field, not a directory: only completion moves a file (to
``done/``), so clarifying an item does not churn its path and every state
change stays a one-line diff.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime
from pathlib import Path

from .plan import DayPlan, parse_plan
from .project import Project, ProjectState, load_project
from .todo import Todo, TodoState, load_todo

TODOS_DIRNAME = "todos"
DONE_DIRNAME = "done"
PLANS_DIRNAME = "plans"
PROJECTS_DIRNAME = "projects"


def todos_dir(data_dir: Path) -> Path:
    """Return the ``todos/`` directory for a data repo."""
    return data_dir / TODOS_DIRNAME


def done_dir(data_dir: Path) -> Path:
    """Return the ``done/`` directory for a data repo."""
    return data_dir / DONE_DIRNAME


def new_id(now: datetime | None = None) -> str:
    """Return a fresh id for a todo or a project.

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
    """Return every non-completed todo, whatever its state (files under ``todos/``)."""
    return _list_dir(todos_dir(data_dir))


def list_done(data_dir: Path) -> list[Todo]:
    """Return the archived todos (files under ``done/``)."""
    return _list_dir(done_dir(data_dir))


def list_by_state(data_dir: Path, state: TodoState) -> list[Todo]:
    """Return the active todos in a given state.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    state : TodoState
        State to filter on.

    Returns
    -------
    list of Todo
        Matching todos, in directory order (callers sort with
        :func:`pytodo.todo.sort_key`).
    """
    return [todo for todo in list_active(data_dir) if todo.state is state]


def create_todo(
    data_dir: Path,
    *,
    title: str,
    state: TodoState = TodoState.INBOX,
    context: str | None = None,
    area: str | None = None,
    project: str | None = None,
    now: datetime | None = None,
) -> Todo:
    """Create a new todo file.

    Defaults to ``INBOX`` with nothing else set: capture must cost one second
    and zero decisions, or you stop capturing. Everything past the title is
    filled in later by ``todo clarify``.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    title : str
        Todo title.
    state : TodoState, optional
        Engagement level, defaults to ``INBOX``.
    context : str or None, optional
        What you need in order to act.
    area : str or None, optional
        Domain of responsibility.
    project : str or None, optional
        Id of the parent project.
    now : datetime.datetime, optional
        Creation time, defaults to now.

    Returns
    -------
    Todo
        The created todo, with ``path`` set to the new file.
    """
    now = now or datetime.now()
    todo_id = new_id(now)
    directory = todos_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{todo_id}.md"
    todo = Todo(
        id=todo_id,
        title=title.strip(),
        state=state,
        context=context,
        area=area,
        project=project,
        created=now.replace(microsecond=0),
        path=path,
    )
    path.write_text(todo.to_markdown(), encoding="utf-8")
    return todo


def save_todo(todo: Todo) -> Path:
    """Write a todo back to its existing file.

    Used by every state change (clarify, defer, delegate). The path never
    moves, so this is always a rewrite in place.

    Parameters
    ----------
    todo : Todo
        Todo to persist; its ``path`` must exist.

    Returns
    -------
    pathlib.Path
        The path that was written.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = todo.require_path()
    path.write_text(todo.to_markdown(), encoding="utf-8")
    return path


def move_to_done(todo: Todo, data_dir: Path, *, now: datetime | None = None) -> Path:
    """Move a todo file to ``done/``, stamping its completion time and state.

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
    todo.state = TodoState.DONE
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


# --------------------------------------------------------------------------- #
# Projects                                                                     #
# --------------------------------------------------------------------------- #


def projects_dir(data_dir: Path) -> Path:
    """Return the ``projects/`` directory for a data repo."""
    return data_dir / PROJECTS_DIRNAME


def list_projects(data_dir: Path) -> list[Project]:
    """Return every project, whatever its state."""
    directory = projects_dir(data_dir)
    if not directory.exists():
        return []
    return [load_project(path) for path in sorted(directory.glob("*.md"))]


def list_active_projects(data_dir: Path) -> list[Project]:
    """Return the projects you are currently committed to."""
    return [p for p in list_projects(data_dir) if p.state is ProjectState.ACTIVE]


def create_project(
    data_dir: Path,
    *,
    title: str,
    outcome: str | None = None,
    area: str | None = None,
    now: datetime | None = None,
) -> Project:
    """Create a new active project file.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    title : str
        Project name.
    outcome : str or None, optional
        What "done" looks like.
    area : str or None, optional
        Domain of responsibility.
    now : datetime.datetime, optional
        Creation time, defaults to now.

    Returns
    -------
    Project
        The created project, with ``path`` set.
    """
    now = now or datetime.now()
    project_id = new_id(now)
    directory = projects_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{project_id}.md"
    project = Project(
        id=project_id,
        title=title.strip(),
        outcome=outcome,
        area=area,
        created=now.replace(microsecond=0),
        path=path,
    )
    path.write_text(project.to_markdown(), encoding="utf-8")
    return project


def save_project(project: Project) -> Path:
    """Write a project back to its existing file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = project.require_path()
    path.write_text(project.to_markdown(), encoding="utf-8")
    return path


def delete_project(project: Project) -> None:
    """Permanently delete a project file.

    Todos referencing it are left alone: the reference points one way only, so
    they simply become standalone actions rather than dangling.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    project.require_path().unlink()


def stalled_projects(data_dir: Path) -> list[Project]:
    """Return the active projects with no ``next`` action.

    This is GTD's central operational rule, and the one humans always break:
    every active project must have at least one next action, or it is not
    moving. Checking it is free, which is much of the point of building this.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.

    Returns
    -------
    list of Project
        Active projects that nothing is currently advancing.
    """
    advancing = {
        todo.project
        for todo in list_active(data_dir)
        if todo.state is TodoState.NEXT and todo.project
    }
    return [p for p in list_active_projects(data_dir) if p.id not in advancing]


# --------------------------------------------------------------------------- #
# Daily plans                                                                  #
# --------------------------------------------------------------------------- #


def plans_dir(data_dir: Path) -> Path:
    """Return the ``plans/`` directory for a data repo."""
    return data_dir / PLANS_DIRNAME


def _plan_path(data_dir: Path, day: date) -> Path:
    return plans_dir(data_dir) / f"{day.isoformat()}.md"


def plan_exists(data_dir: Path, day: date) -> bool:
    """Return whether a plan file already exists for ``day``."""
    return _plan_path(data_dir, day).exists()


def load_day_plan(data_dir: Path, day: date) -> DayPlan:
    """Return the plan for ``day`` (an empty plan if the file is absent)."""
    path = _plan_path(data_dir, day)
    if not path.exists():
        return DayPlan(day=day)
    return parse_plan(path.read_text(encoding="utf-8"), day=day)


def save_day_plan(data_dir: Path, plan: DayPlan) -> Path:
    """Write ``plan`` to its day file, creating ``plans/`` if needed."""
    directory = plans_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = _plan_path(data_dir, plan.day)
    path.write_text(plan.to_markdown(), encoding="utf-8")
    return path


def list_plan_days(data_dir: Path) -> list[date]:
    """Return every day that has a plan file, oldest first."""
    directory = plans_dir(data_dir)
    if not directory.exists():
        return []
    days: list[date] = []
    for path in directory.glob("*.md"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError:
            continue  # ignore files that are not ISO-dated plans
    return sorted(days)


def load_plans(data_dir: Path) -> list[DayPlan]:
    """Return every daily plan, oldest first."""
    return [load_day_plan(data_dir, day) for day in list_plan_days(data_dir)]


def latest_plan_before(data_dir: Path, day: date) -> DayPlan | None:
    """Return the most recent non-empty plan strictly before ``day``."""
    for past in reversed(list_plan_days(data_dir)):
        if past >= day:
            continue
        plan = load_day_plan(data_dir, past)
        if plan.entries:
            return plan
    return None
