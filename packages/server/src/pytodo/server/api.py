"""Read API: the JSON endpoints that compose ``pytodo.core`` for the web UI.

Everything here is read-only (v1). Endpoints are plain ``def`` so FastAPI runs
them in a threadpool: core is synchronous (file I/O and git), which must not
block the event loop. Writes arrive in step 2.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from pytodo.core import service, store, vcs
from pytodo.core.todo import Todo, TodoState
from pytodo.core.vocabulary import load_repo_config

from .config import ServerConfig
from .schemas import (
    CaptureIn,
    DayPlanOut,
    NamedCount,
    TodoOut,
    ViewsOut,
    VocabularyOut,
)

router = APIRouter(prefix="/api")

# Views backed by a single state; "all" and "today" are handled specially.
_STATE_VIEWS = {
    "inbox": TodoState.INBOX,
    "next": TodoState.NEXT,
    "waiting": TodoState.WAITING,
    "someday": TodoState.SOMEDAY,
}


def get_config(request: Request) -> ServerConfig:
    """Return the active :class:`ServerConfig` stored on the app."""
    return request.app.state.config


def _today_todos(cfg: ServerConfig) -> list[Todo]:
    """Active todos referenced in today's plan."""
    plan = store.load_day_plan(cfg.data_dir, date.today())
    ids = {e.todo_id for e in plan.entries}
    return [t for t in store.list_active(cfg.data_dir) if t.id in ids]


def _todos_for_view(cfg: ServerConfig, view: str) -> list[Todo]:
    """Resolve a sidebar view name to the todos it lists."""
    if view == "all":
        return store.list_active(cfg.data_dir)
    if view == "today":
        return _today_todos(cfg)
    state = _STATE_VIEWS.get(view)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown view: {view!r}")
    return store.list_by_state(cfg.data_dir, state)


@router.get("/vocabulary", response_model=VocabularyOut)
def read_vocabulary(cfg: ServerConfig = Depends(get_config)) -> VocabularyOut:
    """Return the editable areas and contexts."""
    repo = load_repo_config(cfg.data_dir)
    return VocabularyOut(areas=repo.areas, contexts=repo.contexts)


@router.get("/views", response_model=ViewsOut)
def read_views(cfg: ServerConfig = Depends(get_config)) -> ViewsOut:
    """Return the sidebar counts: fixed buckets plus per-area/context."""
    repo = load_repo_config(cfg.data_dir)
    active = store.list_active(cfg.data_dir)

    def _count(state: TodoState) -> int:
        return sum(1 for t in active if t.state is state)

    areas = [
        NamedCount(name=a, count=sum(1 for t in active if t.area == a))
        for a in repo.areas
    ]
    contexts = [
        NamedCount(name=c, count=sum(1 for t in active if t.context == c))
        for c in repo.contexts
    ]
    return ViewsOut(
        inbox=_count(TodoState.INBOX),
        today=len(_today_todos(cfg)),
        all=len(active),
        next=_count(TodoState.NEXT),
        waiting=_count(TodoState.WAITING),
        someday=_count(TodoState.SOMEDAY),
        areas=areas,
        contexts=contexts,
    )


@router.get("/todos", response_model=list[TodoOut])
def read_todos(
    view: str = "all",
    area: str | None = None,
    context: str | None = None,
    cfg: ServerConfig = Depends(get_config),
) -> list[TodoOut]:
    """Return the todos of a view, optionally filtered by area and context."""
    todos = _todos_for_view(cfg, view)
    if area is not None:
        todos = [t for t in todos if t.area == area]
    if context is not None:
        todos = [t for t in todos if t.context == context]
    return [TodoOut.from_todo(t) for t in todos]


@router.get("/today", response_model=DayPlanOut)
def read_today(cfg: ServerConfig = Depends(get_config)) -> DayPlanOut:
    """Return today's plan (entries with their per-day status)."""
    plan = store.load_day_plan(cfg.data_dir, date.today())
    return DayPlanOut.from_plan(plan)


@router.post("/capture", response_model=TodoOut, status_code=201)
def capture(
    payload: CaptureIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Capture a todo into the inbox (GTD capture, zero decisions).

    The write is committed locally right away; the network push is left to the
    poller, plus one immediate background flush so a capture propagates without
    waiting a full poll interval. Both take the shared lock, so they never
    collide.
    """
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")

    repo = load_repo_config(cfg.data_dir)
    repo.sync_auto = False  # the poller owns the network sync, not a subprocess
    todo, _ = service.capture(cfg.data_dir, repo, title)

    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)
