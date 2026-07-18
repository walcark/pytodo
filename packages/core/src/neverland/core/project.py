"""Project model: an outcome requiring more than one action.

A project is not a todo with children. It is the *outcome* you are after
("valid passport in hand"), and the actions that serve it are ordinary todos
carrying ``project: <id>``. The reference points one way only, from the action
to the project, so deleting an action can never leave a dangling list. Same
reasoning as the daily plan being a log of references (see ``plan.py``).

This is also the answer to subtasks: a parent with children *is* a project with
next actions, and it needs no second mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import yaml

from .todo import _coerce_datetime


class ProjectState(Enum):
    """Engagement level of a project, mirroring :class:`~neverland.core.todo.TodoState`.

    There is no ``inbox``: a project only exists once you have clarified that
    the thing is multi-step, so it is born ``ACTIVE`` or ``SOMEDAY``.
    """

    ACTIVE = "active"
    SOMEDAY = "someday"
    DONE = "done"


@dataclass
class Project:
    """A desired outcome, stored as one markdown file.

    Attributes
    ----------
    id : str
        Unique identifier, also the file stem. Todos reference it via their
        ``project`` field.
    title : str
        Short name ("Renew passport").
    outcome : str or None
        What "done" looks like ("Valid passport in hand"). Distinct from the
        title on purpose: naming the outcome is what makes a project reviewable.
    area : str or None
        Domain of responsibility, constrained by the repo config.
    state : ProjectState
        Engagement level.
    created : datetime.datetime or None
        Creation timestamp.
    completed : datetime.datetime or None
        Completion timestamp.
    body : str
        Optional markdown body: notes, links, reference material.
    path : pathlib.Path or None
        On-disk location of the file, when known.
    """

    id: str
    title: str
    outcome: str | None = None
    area: str | None = None
    state: ProjectState = ProjectState.ACTIVE
    created: datetime | None = None
    completed: datetime | None = None
    body: str = ""
    path: Path | None = None

    def to_frontmatter(self) -> dict:
        """Return the front matter as an ordered mapping."""
        return {
            "title": self.title,
            "outcome": self.outcome,
            "area": self.area,
            "state": self.state.value,
            "created": self.created,
            "completed": self.completed,
        }

    def to_markdown(self) -> str:
        """Render the project as a markdown document."""
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

        Raises
        ------
        FileNotFoundError
            If the project has no path or the file does not exist.
        """
        if self.path is None or not self.path.exists():
            raise FileNotFoundError(f"project not found: {self.id}")
        return self.path


def _coerce_state(value) -> ProjectState:
    """Return the parsed state, falling back to ``ACTIVE`` on an unknown value.

    ``ACTIVE`` is the safe default: it keeps the project inside the stalled
    check, so a broken file surfaces in ``todo review`` instead of going quiet.
    """
    try:
        return ProjectState(str(value))
    except ValueError:
        return ProjectState.ACTIVE


def parse_markdown(text: str, *, project_id: str, path: Path | None = None) -> Project:
    """Parse a project file into a :class:`Project`.

    Parameters
    ----------
    text : str
        Full file content.
    project_id : str
        Identifier to assign (typically the file stem).
    path : pathlib.Path, optional
        On-disk location, stored on the returned object.

    Returns
    -------
    Project
        The parsed project.

    Raises
    ------
    ValueError
        If the front matter is missing, malformed, or lacks a ``title``.
    """
    if not text.startswith("---"):
        raise ValueError("missing front matter (file must start with '---')")

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

    fm = yaml.safe_load("\n".join(parts[1:end])) or {}
    body = "\n".join(parts[end + 1 :]).strip("\n")

    title = fm.get("title")
    if not title:
        raise ValueError("mandatory 'title' field is missing")

    return Project(
        id=project_id,
        title=str(title),
        outcome=(fm.get("outcome") or None),
        area=(fm.get("area") or None),
        state=_coerce_state(fm.get("state", ProjectState.ACTIVE.value)),
        created=_coerce_datetime(fm.get("created")),
        completed=_coerce_datetime(fm.get("completed")),
        body=body,
        path=path,
    )


def load_project(path: Path) -> Project:
    """Read and parse a project file from disk.

    Parameters
    ----------
    path : pathlib.Path
        File to read.

    Returns
    -------
    Project
        The parsed project, with ``path`` set.
    """
    return parse_markdown(
        path.read_text(encoding="utf-8"), project_id=path.stem, path=path
    )
