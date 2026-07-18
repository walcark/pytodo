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

from datetime import date
from pathlib import Path

from . import store, vcs
from .plan import PlanStatus
from .todo import Todo
from .vocabulary import RepoConfig, save_repo_config

# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #


class ServiceError(RuntimeError):
    """Base class for domain refusals a use case can raise."""


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


def capture(data_dir: Path, cfg: RepoConfig, title: str) -> tuple[Todo, vcs.SyncResult]:
    """Capture a todo into the inbox and sync.

    The GTD capture step: no clarification, straight to the inbox. Returns the
    created todo so the caller can report it (and its inbox count) without a
    second read.
    """
    todo = store.create_todo(data_dir, title=title)
    return todo, auto_sync(data_dir, cfg, f"add: {todo.title}")


def complete(data_dir: Path, cfg: RepoConfig, todos: list[Todo]) -> vcs.SyncResult:
    """Move ``todos`` to the archive, tick them in today's plan, and sync."""
    for todo in todos:
        store.move_to_done(todo, data_dir)
    reflect_done_in_today(data_dir, [t.id for t in todos])
    return auto_sync(data_dir, cfg, f"done: {len(todos)} todo(s)")


def delete(data_dir: Path, cfg: RepoConfig, todos: list[Todo]) -> vcs.SyncResult:
    """Permanently delete ``todos`` and sync."""
    for todo in todos:
        store.delete_todo(todo)
    return auto_sync(data_dir, cfg, f"del: {len(todos)} todo(s)")


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
