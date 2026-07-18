"""Daily plan model: a per-day working set that references todos by id.

A daily plan is one markdown file per day (``plans/YYYY-MM-DD.md``). Each line
references an existing todo by id and carries a *per-day* status, encoded as a
markdown checkbox so that ``todo history`` reads like a git diff::

    ---
    date: 2026-07-15
    ---
    - [ ] 20260705-143201-a3f2  Renew passport   # planned
    - [/] 20260706-091200-b1c3  Write report     # doing
    - [x] 20260701-120000-77de  Pay bill         # done

A plan is a *log of references*: it stores only the todo id and a title
snapshot, never a copy of the todo body, so it stays self-contained even after
the referenced todo is completed or deleted. The per-day status is a distinct
axis from the global lifecycle (``todos/`` vs ``done/``).

Because entries reference todos by id, first-class subtasks (todos carrying a
parent) would slot in later as ordinary entries without changing this format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class PlanStatus(Enum):
    """Per-day status of a planned todo (distinct from the global lifecycle)."""

    PLANNED = "planned"
    DOING = "doing"
    DONE = "done"


# Markdown checkbox marks: status -> mark (for writing) and mark -> status.
_MARK_BY_STATUS = {
    PlanStatus.PLANNED: " ",
    PlanStatus.DOING: "/",
    PlanStatus.DONE: "x",
}
_STATUS_BY_MARK = {mark: status for status, mark in _MARK_BY_STATUS.items()}


@dataclass
class PlanEntry:
    """One todo referenced in a daily plan.

    Attributes
    ----------
    todo_id : str
        Id of the referenced todo (the todo file stem).
    title : str
        Title snapshot, kept so history survives the todo's deletion.
    status : PlanStatus
        Per-day status, ``planned`` by default.
    """

    todo_id: str
    title: str
    status: PlanStatus = PlanStatus.PLANNED


@dataclass
class DayPlan:
    """The plan for a single day: an ordered list of entries."""

    day: date
    entries: list[PlanEntry] = field(default_factory=list)

    def find(self, todo_id: str) -> PlanEntry | None:
        """Return the entry referencing ``todo_id``, or ``None``."""
        return next((e for e in self.entries if e.todo_id == todo_id), None)

    def has(self, todo_id: str) -> bool:
        """Return whether ``todo_id`` is already in the plan."""
        return self.find(todo_id) is not None

    def to_markdown(self) -> str:
        """Render the plan as a markdown document (front matter plus entries)."""
        lines = [f"---\ndate: {self.day.isoformat()}\n---", ""]
        for entry in self.entries:
            mark = _MARK_BY_STATUS[entry.status]
            lines.append(f"- [{mark}] {entry.todo_id}  {entry.title}")
        return "\n".join(lines) + "\n"


_ENTRY_RE = re.compile(r"^- \[(?P<mark>.)\]\s+(?P<id>\S+)\s+(?P<title>.*)$")


def parse_plan(text: str, *, day: date) -> DayPlan:
    """Parse a daily plan file into a :class:`DayPlan`.

    Front matter and blank lines are ignored; an unknown status mark falls back
    to ``planned``. The ``day`` is taken from the caller (the file name), not
    from the front matter.

    Parameters
    ----------
    text : str
        Full file content.
    day : datetime.date
        The day this plan belongs to.

    Returns
    -------
    DayPlan
        The parsed plan.
    """
    entries: list[PlanEntry] = []
    for line in text.splitlines():
        match = _ENTRY_RE.match(line.strip())
        if match is None:
            continue
        status = _STATUS_BY_MARK.get(match["mark"].lower(), PlanStatus.PLANNED)
        entries.append(
            PlanEntry(
                todo_id=match["id"],
                title=match["title"].strip(),
                status=status,
            )
        )
    return DayPlan(day=day, entries=entries)
