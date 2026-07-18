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
from neverland.core.todo import Todo


class CaptureIn(BaseModel):
    """Payload of a quick capture: just a title, straight to the inbox."""

    title: str


class TodoOut(BaseModel):
    """A todo as sent to the client (no body, no filesystem path)."""

    id: str
    title: str
    state: str
    context: str | None = None
    area: str | None = None
    project: str | None = None
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
