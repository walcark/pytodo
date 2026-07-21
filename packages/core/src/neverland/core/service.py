"""UI-agnostic use cases composing ``store`` and ``vcs``.

This is the layer the CLI (and, later, the server) call instead of wiring
``store`` writes to ``vcs`` syncs themselves. Every mutation follows the same
rule the sync model promises: commit locally now, schedule the network flush in
the background (see :func:`auto_sync`).

Nothing here knows about Typer, rich, fzf or a terminal. Inputs are already
resolved (a title, a list of todos, a vocabulary edit); prompting and rendering
stay at the edges. Domain refusals are raised as :class:`ServiceError`
subclasses for the caller to render however it likes.

The interactive flows (``clarify``, ``day``) are not full use cases here: they
are dialogues that compose ``store`` and ``prompt`` step by step and then reach
for :func:`auto_sync` as their single write primitive. Only the parts that are
genuinely input-agnostic live in this module.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from . import store, vcs
from .plan import PlanEntry, PlanStatus
from .project import Project, ProjectState
from .routine import Routine
from .todo import Todo, TodoState
from .vocabulary import RepoConfig, save_repo_config

# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #


class ServiceError(RuntimeError):
    """Base class for domain refusals a use case can raise."""


class ProjectHasActions(ServiceError):
    """A project being deleted is still referenced by active todos."""


class DuplicateValue(ServiceError):
    """A vocabulary value being added is already known (a no-op, not a failure)."""

    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value
        super().__init__(f"{value!r} is already a known {_singular(kind)}.")


class UnknownValue(ServiceError):
    """A vocabulary value being removed is not part of the set."""

    def __init__(self, kind: str, value: str, known: list[str]) -> None:
        self.kind = kind
        self.value = value
        self.known = known
        super().__init__(
            f"unknown {_singular(kind)}: {value!r}. Known: {', '.join(known)}"
        )


class ValueInUse(ServiceError):
    """A vocabulary value being removed is still referenced by active todos."""

    def __init__(self, kind: str, value: str, users: list[Todo]) -> None:
        self.kind = kind
        self.value = value
        self.users = users
        super().__init__(f"{len(users)} todo(s) still use {value!r}")


# --------------------------------------------------------------------------- #
# Sync primitive                                                               #
# --------------------------------------------------------------------------- #


def auto_sync(data_dir: Path, cfg: RepoConfig, message: str) -> vcs.SyncResult:
    """Commit a mutation locally, then schedule the background network flush.

    The local commit is instant so the caller returns immediately; the
    pull/push round-trip is delegated to a detached process (gated by
    ``cfg.sync_auto``). This is the single write path shared by every mutation,
    so the CLI and the server behave identically.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    cfg : RepoConfig
        Active repo config; ``sync_auto`` gates the background network flush.
    message : str
        Commit message for the local commit.

    Returns
    -------
    vcs.SyncResult
        The local sync outcome (warnings, conflicts) for the caller to render.
    """
    result = vcs.sync(data_dir, message=message, network=False)
    if cfg.sync_auto:
        vcs.spawn_background_flush(data_dir)
    return result


# --------------------------------------------------------------------------- #
# Mutations                                                                    #
# --------------------------------------------------------------------------- #


def capture(
    data_dir: Path,
    cfg: RepoConfig,
    title: str,
    *,
    project: str | None = None,
) -> tuple[Todo, vcs.SyncResult]:
    """Capture a todo into the inbox and sync.

    The GTD capture step: no clarification, straight to the inbox. Returns the
    created todo so the caller can report it (and its inbox count) without a
    second read.

    ``project`` may pre-link the captured item to a project while leaving
    everything else to ``clarify``: you already know the outcome it belongs to,
    but not yet the action or its context.
    """
    todo = store.create_todo(data_dir, title=title, project=project)
    return todo, auto_sync(data_dir, cfg, f"add: {todo.title}")


def complete(data_dir: Path, cfg: RepoConfig, todos: list[Todo]) -> vcs.SyncResult:
    """Move ``todos`` to the archive, tick them in today's plan, and sync."""
    for todo in todos:
        store.move_to_done(todo, data_dir)
    reflect_done_in_today(data_dir, [t.id for t in todos])
    _advance_routines(data_dir, todos)
    return auto_sync(data_dir, cfg, f"done: {len(todos)} todo(s)")


def delete(data_dir: Path, cfg: RepoConfig, todos: list[Todo]) -> vcs.SyncResult:
    """Permanently delete ``todos`` and sync."""
    for todo in todos:
        store.delete_todo(todo)
    _advance_routines(data_dir, todos)
    return auto_sync(data_dir, cfg, f"del: {len(todos)} todo(s)")


def reopen(
    data_dir: Path,
    cfg: RepoConfig,
    todos: list[Todo],
    *,
    state: TodoState = TodoState.NEXT,
) -> vcs.SyncResult:
    """Bring archived ``todos`` back to the active list, and sync.

    The undo of :func:`complete`, for the item ticked off by mistake. The state
    held before completion is not recorded, so everything comes back as
    ``next``; adjust afterwards if it belonged on another list.

    A routine occurrence reopens like any other todo, but the routine's own
    schedule is left untouched: rolling an advance back is not reliably
    invertible, and leaving it alone is the conservative choice, since
    materialization skips a routine that already has an open occurrence.
    """
    for todo in todos:
        store.move_to_active(todo, data_dir, state=state)
    reflect_reopen_in_today(data_dir, [t.id for t in todos])
    return auto_sync(data_dir, cfg, f"reopen: {len(todos)} todo(s)")


def _advance_routines(data_dir: Path, todos: list[Todo]) -> None:
    """Move the routine of every resolved occurrence to its next due date.

    Resolving an occurrence (completing or deleting it) is what schedules the
    following one: the routine advances past today, so the next materialization
    spawns it on its next due date and nothing backfills in between.
    """
    today = date.today()
    seen: set[str] = set()
    for todo in todos:
        rid = todo.routine
        if not rid or rid in seen:
            continue
        seen.add(rid)
        routine = store.find_routine(data_dir, rid)
        if routine is not None:
            routine.advance(today)
            store.save_routine(routine)


def update(data_dir: Path, cfg: RepoConfig, todo: Todo) -> vcs.SyncResult:
    """Persist an edited todo (clarify, defer, delegate, rename) and sync.

    A state change never moves the file, so this is a rewrite in place; only
    completion, which archives the file, goes through :func:`complete`. The
    caller mutates ``todo`` (its state, context, area, ...) beforehand; here we
    only write it back and schedule the sync.
    """
    store.save_todo(todo)
    return auto_sync(data_dir, cfg, f"edit: {todo.title}")


# --------------------------------------------------------------------------- #
# Projects                                                                     #
# --------------------------------------------------------------------------- #


def add_project(
    data_dir: Path,
    cfg: RepoConfig,
    *,
    title: str,
    outcome: str | None = None,
    area: str | None = None,
) -> tuple[Project, vcs.SyncResult]:
    """Create a project (born active) and sync.

    Returns the created project so the caller can report it without a second
    read, mirroring :func:`capture`.
    """
    project = store.create_project(data_dir, title=title, outcome=outcome, area=area)
    return project, auto_sync(data_dir, cfg, f"project: add {project.title}")


def project_actions(data_dir: Path, project_id: str) -> list[Todo]:
    """Return the *active* todos serving a project.

    Archived todos are deliberately out of scope: they are a record of what was
    done, and nothing should rewrite them when the project they served is
    completed or removed.
    """
    return [t for t in store.list_active(data_dir) if t.project == project_id]


def complete_project(
    data_dir: Path, cfg: RepoConfig, project: Project
) -> vcs.SyncResult:
    """Mark a project as done and sync.

    The outcome is what completes, so the actions still serving it are left
    alone rather than archived: whether a leftover action became moot or is
    still worth doing is a judgement call the user makes, not the app. The
    caller is expected to surface :func:`project_actions` beforehand.
    """
    project.state = ProjectState.DONE
    project.completed = datetime.now().replace(microsecond=0)
    store.save_project(project)
    return auto_sync(data_dir, cfg, f"project: done {project.title}")


def reopen_project(data_dir: Path, cfg: RepoConfig, project: Project) -> vcs.SyncResult:
    """Bring a completed project back to active, and sync.

    The undo of :func:`complete_project`, for the outcome ticked off too early.
    """
    project.state = ProjectState.ACTIVE
    project.completed = None
    store.save_project(project)
    return auto_sync(data_dir, cfg, f"project: reopen {project.title}")


def remove_project(
    data_dir: Path, cfg: RepoConfig, project: Project, *, detach: bool = False
) -> vcs.SyncResult:
    """Delete a project, optionally detaching the actions that serve it.

    Todos reference projects one way, so deleting the *target* is the one
    direction that can dangle. Rather than allow that, this refuses while active
    todos still point at the project; ``detach`` clears their ``project`` field
    first, which keeps the actions but drops the link.

    Raises
    ------
    ProjectHasActions
        If active todos reference the project and ``detach`` is false.
    """
    actions = project_actions(data_dir, project.id)
    if actions and not detach:
        raise ProjectHasActions(
            f"{len(actions)} active todo(s) still reference this project"
        )
    for todo in actions:
        todo.project = None
        store.save_todo(todo)
    store.delete_project(project)
    return auto_sync(data_dir, cfg, f"project: del {project.title}")


# --------------------------------------------------------------------------- #
# Routines                                                                     #
# --------------------------------------------------------------------------- #


def add_routine(
    data_dir: Path, cfg: RepoConfig, routine: Routine
) -> tuple[Routine, vcs.SyncResult]:
    """Create a routine (seeding its first due date) and sync."""
    if routine.next_due is None:
        routine.next_due = routine.recurrence.first_on_or_after(date.today())
    store.create_routine(data_dir, routine=routine)
    return routine, auto_sync(data_dir, cfg, f"routine: add {routine.title}")


def update_routine(data_dir: Path, cfg: RepoConfig, routine: Routine) -> vcs.SyncResult:
    """Persist an edited routine and sync.

    The caller mutates the routine first (title, rule, lead, ...). When the
    *rule* itself changes the caller must also reseed ``next_due``, or the
    routine keeps firing on the schedule it no longer has.
    """
    store.save_routine(routine)
    return auto_sync(data_dir, cfg, f"routine: edit {routine.title}")


def remove_routine(data_dir: Path, cfg: RepoConfig, routine: Routine) -> vcs.SyncResult:
    """Delete a routine and sync (its already-spawned occurrences are kept)."""
    store.delete_routine(routine)
    return auto_sync(data_dir, cfg, f"routine: remove {routine.title}")


def materialize_routines(
    data_dir: Path, cfg: RepoConfig, today: date | None = None
) -> list[Todo]:
    """Spawn the due routines as todos and add them to today's plan, then sync.

    Idempotent and safe to run on a timer: a routine spawns nothing while its
    previous occurrence is still open (one at a time, no pile-up), and only when
    ``next_due - lead`` has been reached. ``next_due`` itself is advanced when
    the occurrence is resolved, not here.
    """
    today = today or date.today()
    open_routines = {t.routine for t in store.list_active(data_dir) if t.routine}
    spawned: list[Todo] = []
    plan = None
    for routine in store.list_routines(data_dir):
        if not routine.due_on(today) or routine.id in open_routines:
            continue
        todo = store.create_todo(
            data_dir,
            title=routine.title,
            state=TodoState.NEXT,
            context=routine.context,
            area=routine.area,
            project=routine.project,
            routine=routine.id,
        )
        spawned.append(todo)
        if plan is None:
            plan = store.load_day_plan(data_dir, today)
        if not plan.has(todo.id):
            plan.entries.append(PlanEntry(todo_id=todo.id, title=todo.title))

    if not spawned:
        return []
    assert plan is not None  # set whenever an occurrence was spawned
    store.save_day_plan(data_dir, plan)
    auto_sync(data_dir, cfg, f"routine: materialize {len(spawned)} occurrence(s)")
    return spawned


# --------------------------------------------------------------------------- #
# Daily plan                                                                   #
# --------------------------------------------------------------------------- #


def plan_add(
    data_dir: Path, cfg: RepoConfig, todo: Todo, *, day: date | None = None
) -> vcs.SyncResult:
    """Add ``todo`` to a day's plan (default today) and sync.

    Idempotent: a todo already in the plan is left untouched (no duplicate
    entry), so the "Today" toggle can call this without checking first.
    """
    day = day or date.today()
    plan = store.load_day_plan(data_dir, day)
    if not plan.has(todo.id):
        plan.entries.append(PlanEntry(todo_id=todo.id, title=todo.title))
        store.save_day_plan(data_dir, plan)
    return auto_sync(data_dir, cfg, f"plan: add {todo.title}")


def plan_remove(
    data_dir: Path, cfg: RepoConfig, todo_id: str, *, day: date | None = None
) -> vcs.SyncResult:
    """Drop ``todo_id`` from a day's plan (default today) and sync.

    Takes an id, not a todo: an entry may reference a todo that is already
    completed or deleted, and it must still be removable from the plan.
    """
    day = day or date.today()
    plan = store.load_day_plan(data_dir, day)
    plan.entries = [e for e in plan.entries if e.todo_id != todo_id]
    store.save_day_plan(data_dir, plan)
    return auto_sync(data_dir, cfg, "plan: remove item")


def plan_set_status(
    data_dir: Path,
    cfg: RepoConfig,
    todo_id: str,
    status: PlanStatus,
    *,
    day: date | None = None,
) -> vcs.SyncResult:
    """Set the per-day status of a plan entry (default today) and sync."""
    day = day or date.today()
    plan = store.load_day_plan(data_dir, day)
    entry = plan.find(todo_id)
    if entry is not None:
        entry.status = status
        store.save_day_plan(data_dir, plan)
    return auto_sync(data_dir, cfg, f"plan: {status.value} item")


def reflect_done_in_today(data_dir: Path, todo_ids: list[str]) -> None:
    """Mark ``todo_ids`` as done in today's plan, if they appear in it.

    The daily status is a separate axis from the global lifecycle, but a global
    completion is also a completion for the day, so it is reflected (only when a
    plan for today already exists).
    """
    today = date.today()
    if not store.plan_exists(data_dir, today):
        return
    plan = store.load_day_plan(data_dir, today)
    changed = False
    for todo_id in todo_ids:
        entry = plan.find(todo_id)
        if entry is not None and entry.status is not PlanStatus.DONE:
            entry.status = PlanStatus.DONE
            changed = True
    if changed:
        store.save_day_plan(data_dir, plan)


def reflect_reopen_in_today(data_dir: Path, todo_ids: list[str]) -> None:
    """Put ``todo_ids`` back to ``planned`` in today's plan, if they appear in it.

    The mirror of :func:`reflect_done_in_today`: undoing a completion also undoes
    the completion it stamped on the day. Entries left at ``planned`` or
    ``doing`` are untouched, so reopening never demotes a day status the user
    set by hand.
    """
    today = date.today()
    if not store.plan_exists(data_dir, today):
        return
    plan = store.load_day_plan(data_dir, today)
    changed = False
    for todo_id in todo_ids:
        entry = plan.find(todo_id)
        if entry is not None and entry.status is PlanStatus.DONE:
            entry.status = PlanStatus.PLANNED
            changed = True
    if changed:
        store.save_day_plan(data_dir, plan)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #


def set_vocabulary(
    data_dir: Path, cfg: RepoConfig, kind: str, action: str, value: str
) -> vcs.SyncResult:
    """Add or remove one value from ``areas``/``contexts``, then sync.

    Editing the vocabulary is a mutation like any other: ``config.toml`` is
    versioned and shared across devices, so it commits and syncs rather than
    being a local preference.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    cfg : RepoConfig
        Active repo config; mutated in place before being saved.
    kind : {"areas", "contexts"}
        Which list to edit.
    action : {"add", "rm"}
        Whether to add or remove ``value``.
    value : str
        The area or context to add or remove.

    Returns
    -------
    vcs.SyncResult
        The sync outcome.

    Raises
    ------
    DuplicateValue
        Adding a value already present (the caller should treat it as a no-op).
    UnknownValue
        Removing a value that is not in the set.
    ValueInUse
        Removing a value still referenced by active todos (would orphan them).
    """
    values: list[str] = getattr(cfg, kind)

    if action == "add":
        if value in values:
            raise DuplicateValue(kind, value)
        values.append(value)
    else:
        if value not in values:
            raise UnknownValue(kind, value, values)
        field = "context" if kind == "contexts" else "area"
        users = [t for t in store.list_active(data_dir) if getattr(t, field) == value]
        if users:
            raise ValueInUse(kind, value, users)
        values.remove(value)

    save_repo_config(data_dir, cfg)
    return auto_sync(data_dir, cfg, f"config: {action} {_singular(kind)} {value}")


def _singular(kind: str) -> str:
    """Return the singular label for a vocabulary ``kind`` ("areas" -> "area")."""
    return kind[:-1]
