"""Pydantic response models: the JSON contract of the read API.

These decouple the wire format from core's dataclasses, so the API others build
against is stable even if the core types move. Enums are sent as their string
value (``state="next"``), datetimes as ISO 8601.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from neverland.core.plan import DayPlan, PlanEntry
from neverland.core.project import Project
from neverland.core.routine import Routine
from neverland.core.todo import Todo


class CaptureIn(BaseModel):
    """Payload of a quick capture: just a title, straight to the inbox."""

    title: str


class TodoPatch(BaseModel):
    """Partial edit of a todo: only the fields actually sent are applied.

    ``model_dump(exclude_unset=True)`` on the server side tells apart "leave
    this field alone" from "clear it" (an explicit ``null``), which is what a
    clarify step needs (set a context, drop a stale ``waiting_on``, ...).
    """

    title: str | None = None
    state: str | None = None
    context: str | None = None
    area: str | None = None
    project: str | None = None
    waiting_on: str | None = None


class PlanStatusIn(BaseModel):
    """Payload to set a plan entry's per-day status (``planned``/``doing``/``done``)."""

    status: str


class TodoOut(BaseModel):
    """A todo as sent to the client (no body, no filesystem path)."""

    id: str
    title: str
    state: str
    context: str | None = None
    area: str | None = None
    project: str | None = None
    routine: str | None = None
    waiting_on: str | None = None
    created: datetime | None = None
    completed: datetime | None = None

    @classmethod
    def from_todo(cls, todo: Todo) -> TodoOut:
        return cls(
            id=todo.id,
            title=todo.title,
            state=todo.state.value,
            context=todo.context,
            area=todo.area,
            project=todo.project,
            routine=todo.routine,
            waiting_on=todo.waiting_on,
            created=todo.created,
            completed=todo.completed,
        )


class ProjectOut(BaseModel):
    """A project as sent to the client."""

    id: str
    title: str
    outcome: str | None = None
    area: str | None = None
    state: str
    created: datetime | None = None
    completed: datetime | None = None

    @classmethod
    def from_project(cls, project: Project) -> ProjectOut:
        return cls(
            id=project.id,
            title=project.title,
            outcome=project.outcome,
            area=project.area,
            state=project.state.value,
            created=project.created,
            completed=project.completed,
        )


class ProjectIn(BaseModel):
    """Payload to create a project: a title, optionally an outcome and area."""

    title: str
    outcome: str | None = None
    area: str | None = None


class ProjectSummaryOut(BaseModel):
    """A project plus how many todos serve it (and whether it is stalled)."""

    id: str
    title: str
    outcome: str | None = None
    area: str | None = None
    state: str
    action_count: int
    next_count: int
    stalled: bool

    @classmethod
    def from_project(
        cls, project: Project, *, actions: int, nexts: int
    ) -> ProjectSummaryOut:
        return cls(
            id=project.id,
            title=project.title,
            outcome=project.outcome,
            area=project.area,
            state=project.state.value,
            action_count=actions,
            next_count=nexts,
            stalled=nexts == 0,
        )


class RoutineIn(BaseModel):
    """Payload to create a routine: a title and the recurrence rule fields.

    Only the fields the chosen ``freq`` needs are read (``interval`` for days,
    ``weekdays`` for weekly, ``monthday`` for monthly, ``month``/``day`` for
    yearly); the server builds and validates the rule from them.
    """

    title: str
    freq: str
    interval: int | None = None
    weekdays: list[str] | None = None
    monthday: int | None = None
    month: int | None = None
    day: int | None = None
    context: str | None = None
    area: str | None = None
    project: str | None = None
    lead: int = 0


class RoutineOut(BaseModel):
    """A routine as sent to the client, with a human-readable rule."""

    id: str
    title: str
    rule: str
    next_due: str | None = None
    lead: int
    active: bool
    context: str | None = None
    area: str | None = None
    project: str | None = None

    @classmethod
    def from_routine(cls, routine: Routine) -> RoutineOut:
        return cls(
            id=routine.id,
            title=routine.title,
            rule=routine.recurrence.describe(),
            next_due=routine.next_due.isoformat() if routine.next_due else None,
            lead=routine.lead,
            active=routine.active,
            context=routine.context,
            area=routine.area,
            project=routine.project,
        )


class PlanEntryOut(BaseModel):
    """One entry of the daily plan (todo id, title snapshot, per-day status)."""

    id: str
    title: str
    status: str

    @classmethod
    def from_entry(cls, entry: PlanEntry) -> PlanEntryOut:
        return cls(id=entry.todo_id, title=entry.title, status=entry.status.value)


class DayPlanOut(BaseModel):
    """The plan for a day."""

    day: str
    entries: list[PlanEntryOut]

    @classmethod
    def from_plan(cls, plan: DayPlan) -> DayPlanOut:
        return cls(
            day=plan.day.isoformat(),
            entries=[PlanEntryOut.from_entry(e) for e in plan.entries],
        )


class ReviewOut(BaseModel):
    """The weekly-review report: the four things GTD says rot silently.

    A filling inbox, a project nothing advances, a next action with no context
    (so it is unselectable), and someone you forgot you were waiting on.
    """

    inbox: list[TodoOut]
    stalled_projects: list[ProjectOut]
    contextless_next: list[TodoOut]
    stale_waiting: list[TodoOut]
    waiting_stale_days: int


class NamedCount(BaseModel):
    """A sidebar label and how many todos fall under it."""

    name: str
    count: int


class ViewsOut(BaseModel):
    """Sidebar counts: the fixed buckets plus the per-area/context breakdown."""

    inbox: int
    today: int
    all: int
    next: int
    waiting: int
    someday: int
    areas: list[NamedCount]
    contexts: list[NamedCount]


class VocabularyOut(BaseModel):
    """The editable vocabulary shown in the sidebar."""

    areas: list[str]
    contexts: list[str]
