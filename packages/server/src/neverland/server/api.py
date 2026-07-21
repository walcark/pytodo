"""JSON API: the endpoints that compose ``neverland.core`` for the web UI.

Reads return the todos and sidebar counts; writes cover capture plus the
clarify loop (edit a todo, complete it, delete it). Endpoints are plain ``def``
so FastAPI runs them in a threadpool: core is synchronous (file I/O and git),
which must not block the event loop.

Every write follows the same contract as capture: commit locally now and let
the poller own the network push (so ``sync_auto`` is cleared and one immediate
background flush is scheduled), which keeps the CLI and the server identical.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from neverland.core import service, store, vcs
from neverland.core.plan import PlanStatus
from neverland.core.routine import Freq, Recurrence, Routine
from neverland.core.todo import Todo, TodoState, sort_key
from neverland.core.vocabulary import RepoConfig, load_repo_config

from .config import ServerConfig
from .schemas import (
    CaptureIn,
    DayPlanOut,
    NamedCount,
    PlanStatusIn,
    ProjectIn,
    ProjectOut,
    ProjectSummaryOut,
    ReviewOut,
    RoutineIn,
    RoutineOut,
    RoutinePatch,
    TodoOut,
    TodoPatch,
    ViewsOut,
    VocabularyOut,
)
from .security import require_token

# The token guard runs before every endpoint (no-op when no token is set).
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

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


# --------------------------------------------------------------------------- #
# Writes: clarify, complete, delete                                            #
# --------------------------------------------------------------------------- #


def _repo_for_write(cfg: ServerConfig) -> RepoConfig:
    """Load the repo config with the background network flush disabled.

    Like capture, every mutation commits locally now and leaves the push to the
    poller, so ``sync_auto`` is cleared to avoid spawning a rival flush process.
    """
    repo = load_repo_config(cfg.data_dir)
    repo.sync_auto = False
    return repo


def _require_active(cfg: ServerConfig, todo_id: str) -> Todo:
    """Return the active todo with ``todo_id`` or raise ``404``."""
    todo = store.find_active(cfg.data_dir, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail=f"unknown todo: {todo_id}")
    return todo


def _require_done(cfg: ServerConfig, todo_id: str) -> Todo:
    """Return the archived todo with ``todo_id`` or raise ``404``."""
    todo = store.find_done(cfg.data_dir, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail=f"unknown archived todo: {todo_id}")
    return todo


def _apply_patch(cfg: ServerConfig, repo: RepoConfig, todo: Todo, fields: dict) -> None:
    """Validate the patched ``fields`` against the vocabulary and apply them.

    Only keys present in ``fields`` are touched; an explicit ``None`` clears the
    field. ``area``, ``context`` and ``project`` must reference known values, so
    a typo cannot orphan a todo onto a value nothing else uses.
    """
    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        todo.title = title
    if "state" in fields:
        try:
            todo.state = TodoState(fields["state"])
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"unknown state: {fields['state']!r}"
            ) from None
    if "area" in fields:
        area = fields["area"]
        if area is not None and area not in repo.areas:
            raise HTTPException(status_code=400, detail=f"unknown area: {area!r}")
        todo.area = area
    if "context" in fields:
        context = fields["context"]
        if context is not None and context not in repo.contexts:
            raise HTTPException(status_code=400, detail=f"unknown context: {context!r}")
        todo.context = context
    if "project" in fields:
        project = fields["project"]
        if project is not None:
            known = {p.id for p in store.list_active_projects(cfg.data_dir)}
            if project not in known:
                raise HTTPException(
                    status_code=400, detail=f"unknown project: {project!r}"
                )
        todo.project = project
    if "waiting_on" in fields:
        todo.waiting_on = fields["waiting_on"] or None


@router.patch("/todos/{todo_id}", response_model=TodoOut)
def update_todo(
    todo_id: str,
    payload: TodoPatch,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Apply a partial edit to a todo (clarify, defer, delegate, rename).

    Only the fields present in the body are changed. Setting ``state`` to
    ``done`` is a completion, so it is routed through the archive path rather
    than an in-place rewrite.
    """
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("state") == TodoState.DONE.value:
        service.complete(cfg.data_dir, repo, [todo])
    else:
        _apply_patch(cfg, repo, todo, fields)
        service.update(cfg.data_dir, repo, todo)

    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


@router.post("/todos/{todo_id}/complete", response_model=TodoOut)
def complete_todo(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Complete a todo: archive it and tick it in today's plan."""
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.complete(cfg.data_dir, repo, [todo])
    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


@router.post("/todos/{todo_id}/reopen", response_model=TodoOut)
def reopen_todo(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Undo a completion: bring an archived todo back to the active list.

    It comes back as ``next``, since the state it held before completion is not
    recorded; edit it afterwards if it belonged on another list.
    """
    todo = _require_done(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.reopen(cfg.data_dir, repo, [todo])
    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


@router.delete("/todos/{todo_id}", status_code=204)
def delete_todo(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> Response:
    """Permanently delete a todo."""
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.delete(cfg.data_dir, repo, [todo])
    background.add_task(vcs.background_flush, cfg.data_dir)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Today's plan                                                                 #
# --------------------------------------------------------------------------- #


@router.post("/today/{todo_id}", response_model=DayPlanOut)
def add_to_today(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> DayPlanOut:
    """Add a todo to today's plan (idempotent) and return the updated plan."""
    todo = _require_active(cfg, todo_id)
    repo = _repo_for_write(cfg)
    service.plan_add(cfg.data_dir, repo, todo)
    background.add_task(vcs.background_flush, cfg.data_dir)
    return DayPlanOut.from_plan(store.load_day_plan(cfg.data_dir, date.today()))


@router.patch("/today/{todo_id}", response_model=DayPlanOut)
def set_today_status(
    todo_id: str,
    payload: PlanStatusIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> DayPlanOut:
    """Set the per-day status of a plan entry (``planned``/``doing``/``done``)."""
    try:
        status = PlanStatus(payload.status)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"unknown status: {payload.status!r}"
        ) from None
    plan = store.load_day_plan(cfg.data_dir, date.today())
    if not plan.has(todo_id):
        raise HTTPException(status_code=404, detail=f"not in today's plan: {todo_id}")
    repo = _repo_for_write(cfg)
    service.plan_set_status(cfg.data_dir, repo, todo_id, status)
    background.add_task(vcs.background_flush, cfg.data_dir)
    return DayPlanOut.from_plan(store.load_day_plan(cfg.data_dir, date.today()))


@router.delete("/today/{todo_id}", status_code=204)
def remove_from_today(
    todo_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> Response:
    """Remove a todo from today's plan (the todo itself is left untouched)."""
    plan = store.load_day_plan(cfg.data_dir, date.today())
    if not plan.has(todo_id):
        raise HTTPException(status_code=404, detail=f"not in today's plan: {todo_id}")
    repo = _repo_for_write(cfg)
    service.plan_remove(cfg.data_dir, repo, todo_id)
    background.add_task(vcs.background_flush, cfg.data_dir)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# History (the archive of completed todos)                                     #
# --------------------------------------------------------------------------- #


@router.get("/done", response_model=list[TodoOut])
def read_done(cfg: ServerConfig = Depends(get_config)) -> list[TodoOut]:
    """Return the completed todos, most recently completed first."""
    done = store.list_done(cfg.data_dir)
    done.sort(key=lambda t: t.completed or datetime.min, reverse=True)
    return [TodoOut.from_todo(t) for t in done]


# --------------------------------------------------------------------------- #
# Review (the four things GTD says rot silently)                               #
# --------------------------------------------------------------------------- #


@router.get("/review", response_model=ReviewOut)
def read_review(cfg: ServerConfig = Depends(get_config)) -> ReviewOut:
    """Report a filling inbox, stalled projects, contextless next actions and
    stale ``waiting`` items, mirroring ``todo review``."""
    repo = load_repo_config(cfg.data_dir)
    active = store.list_active(cfg.data_dir)

    inbox = sorted((t for t in active if t.state is TodoState.INBOX), key=sort_key)
    contextless = sorted(
        (t for t in active if t.state is TodoState.NEXT and not t.context),
        key=sort_key,
    )
    cutoff = datetime.now() - timedelta(days=repo.waiting_stale_days)
    stale = sorted(
        (
            t
            for t in active
            if t.state is TodoState.WAITING
            and t.created is not None
            and t.created < cutoff
        ),
        key=sort_key,
    )
    return ReviewOut(
        inbox=[TodoOut.from_todo(t) for t in inbox],
        stalled_projects=[
            ProjectOut.from_project(p) for p in store.stalled_projects(cfg.data_dir)
        ],
        contextless_next=[TodoOut.from_todo(t) for t in contextless],
        stale_waiting=[TodoOut.from_todo(t) for t in stale],
        waiting_stale_days=repo.waiting_stale_days,
    )


# --------------------------------------------------------------------------- #
# Projects                                                                     #
# --------------------------------------------------------------------------- #


@router.get("/projects", response_model=list[ProjectSummaryOut])
def read_projects(cfg: ServerConfig = Depends(get_config)) -> list[ProjectSummaryOut]:
    """Return the active projects, each with its action and next-action counts."""
    active = store.list_active(cfg.data_dir)
    actions: dict[str, int] = {}
    nexts: dict[str, int] = {}
    for todo in active:
        if todo.project:
            actions[todo.project] = actions.get(todo.project, 0) + 1
            if todo.state is TodoState.NEXT:
                nexts[todo.project] = nexts.get(todo.project, 0) + 1
    return [
        ProjectSummaryOut.from_project(
            p, actions=actions.get(p.id, 0), nexts=nexts.get(p.id, 0)
        )
        for p in store.list_active_projects(cfg.data_dir)
    ]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> ProjectOut:
    """Create a project (born active) and sync."""
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    repo = _repo_for_write(cfg)
    if payload.area is not None and payload.area not in repo.areas:
        raise HTTPException(status_code=400, detail=f"unknown area: {payload.area!r}")
    project, _ = service.add_project(
        cfg.data_dir, repo, title=title, outcome=payload.outcome, area=payload.area
    )
    background.add_task(vcs.background_flush, cfg.data_dir)
    return ProjectOut.from_project(project)


@router.get("/projects/{project_id}/todos", response_model=list[TodoOut])
def read_project_todos(
    project_id: str, cfg: ServerConfig = Depends(get_config)
) -> list[TodoOut]:
    """Return the active todos serving a project, oldest first."""
    known = {p.id for p in store.list_projects(cfg.data_dir)}
    if project_id not in known:
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    todos = sorted(
        (t for t in store.list_active(cfg.data_dir) if t.project == project_id),
        key=sort_key,
    )
    return [TodoOut.from_todo(t) for t in todos]


@router.post("/projects/{project_id}/todos", response_model=TodoOut, status_code=201)
def capture_into_project(
    project_id: str,
    payload: CaptureIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> TodoOut:
    """Capture a todo straight into the inbox, pre-linked to a project.

    A capture, not a clarified action: it lands in the inbox (no context, no
    state decision) but already knows its project, so ``clarify`` only has the
    action and context left to decide.
    """
    known = {p.id for p in store.list_projects(cfg.data_dir)}
    if project_id not in known:
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    repo = _repo_for_write(cfg)
    todo, _ = service.capture(cfg.data_dir, repo, title, project=project_id)
    background.add_task(vcs.background_flush, cfg.data_dir)
    return TodoOut.from_todo(todo)


# --------------------------------------------------------------------------- #
# Routines (recurring todos)                                                   #
# --------------------------------------------------------------------------- #


def _recurrence_from(payload: RoutineIn | RoutinePatch) -> Recurrence:
    """Build and validate a :class:`Recurrence` from the rule fields of a payload."""
    try:
        freq = Freq(payload.freq)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"unknown freq: {payload.freq!r}"
        ) from None
    data: dict = {"freq": payload.freq}
    if freq is Freq.DAYS:
        data["interval"] = payload.interval or 1
    elif freq is Freq.WEEKLY:
        data["weekdays"] = payload.weekdays or []
    elif freq is Freq.MONTHLY:
        data["monthday"] = payload.monthday
    else:
        data["month"], data["day"] = payload.month, payload.day
    try:
        return Recurrence.from_dict(data)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid recurrence: {exc}"
        ) from None


@router.get("/routines", response_model=list[RoutineOut])
def read_routines(cfg: ServerConfig = Depends(get_config)) -> list[RoutineOut]:
    """Return every routine (active or paused)."""
    return [RoutineOut.from_routine(r) for r in store.list_routines(cfg.data_dir)]


@router.post("/routines", response_model=RoutineOut, status_code=201)
def create_routine(
    payload: RoutineIn,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> RoutineOut:
    """Create a routine and immediately materialize it if it is already due."""
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    if payload.lead < 0:
        raise HTTPException(status_code=400, detail="lead must be >= 0")
    repo = _repo_for_write(cfg)
    if payload.area is not None and payload.area not in repo.areas:
        raise HTTPException(status_code=400, detail=f"unknown area: {payload.area!r}")
    if payload.context is not None and payload.context not in repo.contexts:
        raise HTTPException(
            status_code=400, detail=f"unknown context: {payload.context!r}"
        )
    if payload.project is not None:
        known = {p.id for p in store.list_active_projects(cfg.data_dir)}
        if payload.project not in known:
            raise HTTPException(
                status_code=400, detail=f"unknown project: {payload.project!r}"
            )

    recurrence = _recurrence_from(payload)
    routine = Routine(
        id="",
        title=title,
        recurrence=recurrence,
        context=payload.context,
        area=payload.area,
        project=payload.project,
        lead=payload.lead,
    )
    created, _ = service.add_routine(cfg.data_dir, repo, routine)
    service.materialize_routines(cfg.data_dir, repo)  # surface it if due today
    background.add_task(vcs.background_flush, cfg.data_dir)
    return RoutineOut.from_routine(created)


@router.patch("/routines/{routine_id}", response_model=RoutineOut)
def update_routine(
    routine_id: str,
    payload: RoutinePatch,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> RoutineOut:
    """Edit a routine: fix a typo, change its schedule, pause it.

    Changing the rule (sending ``freq``) reseeds ``next_due``, otherwise the
    routine would keep firing on the schedule it no longer has.
    """
    routine = store.find_routine(cfg.data_dir, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail=f"unknown routine: {routine_id}")
    repo = _repo_for_write(cfg)
    fields = payload.model_dump(exclude_unset=True)

    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title must not be empty")
        routine.title = title
    if "area" in fields:
        area = fields["area"]
        if area is not None and area not in repo.areas:
            raise HTTPException(status_code=400, detail=f"unknown area: {area!r}")
        routine.area = area
    if "context" in fields:
        context = fields["context"]
        if context is not None and context not in repo.contexts:
            raise HTTPException(status_code=400, detail=f"unknown context: {context!r}")
        routine.context = context
    if "project" in fields:
        project = fields["project"]
        if project is not None:
            known = {p.id for p in store.list_active_projects(cfg.data_dir)}
            if project not in known:
                raise HTTPException(
                    status_code=400, detail=f"unknown project: {project!r}"
                )
        routine.project = project
    if "lead" in fields:
        lead = int(fields["lead"] or 0)
        if lead < 0:
            raise HTTPException(status_code=400, detail="lead must be >= 0")
        routine.lead = lead
    if "active" in fields:
        routine.active = bool(fields["active"])
    if "freq" in fields:
        routine.recurrence = _recurrence_from(payload)
        routine.next_due = routine.recurrence.first_on_or_after(date.today())

    service.update_routine(cfg.data_dir, repo, routine)
    service.materialize_routines(cfg.data_dir, repo)  # surface it if now due
    background.add_task(vcs.background_flush, cfg.data_dir)
    return RoutineOut.from_routine(routine)


@router.delete("/routines/{routine_id}", status_code=204)
def delete_routine(
    routine_id: str,
    background: BackgroundTasks,
    cfg: ServerConfig = Depends(get_config),
) -> Response:
    """Delete a routine (its already-spawned occurrences are left untouched)."""
    routine = store.find_routine(cfg.data_dir, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail=f"unknown routine: {routine_id}")
    repo = _repo_for_write(cfg)
    service.remove_routine(cfg.data_dir, repo, routine)
    background.add_task(vcs.background_flush, cfg.data_dir)
    return Response(status_code=204)
