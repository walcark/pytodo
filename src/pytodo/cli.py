"""`todo` CLI - Typer entry point."""

from __future__ import annotations

import functools
import os
import subprocess
from datetime import date
from pathlib import Path

import typer
from rich.markup import escape

from . import prompt, store, vcs
from .config import (
    RepoConfig,
    load_repo_config,
    read_data_dir,
    write_data_dir,
)
from .plan import PlanEntry, PlanStatus
from .todo import Todo
from .view import console, render_history, render_todos

app = typer.Typer(
    help="Manage todos synchronized through git.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Show today's plan when run without a subcommand (`todo`)."""
    if ctx.invoked_subcommand is not None:
        return
    _render_today(require_data_dir())


_NO_REPO = "No data repo configured. Run `todo init <path-or-url>`."


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _err(msg: str) -> None:
    console.print(f"[red]✗[/red] {escape(msg)}")


def _ok(msg: str) -> None:
    console.print(f"[green]✓[/green] {escape(msg)}")


def _warn(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {escape(msg)}")


def handle_errors(fn):
    """Translate business exceptions into clean exits (no traceback)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except prompt.Cancelled:
            console.print("[grey62]cancelled[/grey62]")
            raise typer.Exit(1) from None
        except prompt.MissingTool as exc:
            _err(str(exc))
            raise typer.Exit(2) from None
        except vcs.RepoError as exc:
            _err(str(exc))
            raise typer.Exit(1) from None
        except FileNotFoundError as exc:
            _err(str(exc))
            raise typer.Exit(1) from None
        except RuntimeError as exc:
            _err(str(exc))
            raise typer.Exit(2) from None

    return wrapper


def require_data_dir() -> Path:
    """Return the active data dir, exiting cleanly if it is unset or missing."""
    data_dir = read_data_dir()
    if data_dir is None:
        _err(_NO_REPO)
        raise typer.Exit(1)
    if not data_dir.exists():
        _err(f"Data repo not found: {data_dir}. Run `todo init` or `todo repo` again.")
        raise typer.Exit(1)
    return data_dir


def _emit_sync(result: vcs.SyncResult) -> None:
    for w in result.warnings:
        _warn(w)
    if result.conflict_files:
        _err("Rebase conflict on: " + ", ".join(result.conflict_files))
        _err("Resolve it manually in the repo, then run `todo sync`.")


def auto_sync(data_dir: Path, cfg: RepoConfig, message: str) -> None:
    """Sync after a mutation.

    Commit locally right away (instant), then delegate pull/push to a detached
    process so that ``add``/``del`` return immediately.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    cfg : RepoConfig
        Active repo config (its ``sync_auto`` gates the background network sync).
    message : str
        Commit message for the local commit.
    """
    result = vcs.sync(data_dir, message=message, network=False)
    _emit_sync(result)
    if cfg.sync_auto:
        vcs.spawn_background_flush(data_dir)


def open_editor(path: Path) -> None:
    """Open ``path`` in ``$EDITOR`` (defaulting to ``vi``)."""
    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)])


def _validate_choice(value: str, allowed: list[str], label: str) -> str:
    if value not in allowed:
        _err(f"invalid {label}: {value!r}. Allowed values: {', '.join(allowed)}")
        raise typer.Exit(1)
    return value


def _resolve_choice(
    value: str | None,
    options: list[str],
    *,
    label: str,
    header: str,
    default: str | None = None,
) -> str:
    """Return a valid choice, prompting via fzf when ``value`` is None."""
    if value is None:
        value = prompt.choose(options, header=header, default=default)
    return _validate_choice(value, options, label)


def _resolve_optional_choice(
    value: str | None, options: list[str], *, label: str, header: str
) -> str | None:
    """Like :func:`_resolve_choice`, but the prompt offers a ``(none)`` opt-out."""
    if value is None:
        value = prompt.choose(["(none)", *options], header=header)
        if value == "(none)":
            return None
    return _validate_choice(value, options, label)


def _apply_setup(target: str) -> vcs.SetupResult:
    """Set up/adopt the repo at ``target``, persist it, and log the actions."""
    result = vcs.setup_repo(target, confirm=prompt.confirm)
    write_data_dir(result.data_dir)
    for action in result.actions:
        console.print(f"  [grey62]-[/grey62] {action}")
    return result


def _pick_active(*, multi: bool) -> tuple[Path, RepoConfig, list[Todo]]:
    """Load the repo and let the user select among the active todos.

    Shared preamble of the mutation commands: exits cleanly (code 0) when no
    todo exists, and (code 1) when the selection is cancelled.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    todos = store.list_active(data_dir)
    if not todos:
        console.print("[grey62]No active todo.[/grey62]")
        raise typer.Exit(0)
    selected = prompt.select_todos(todos, multi=multi)
    if not selected:
        raise typer.Exit(1)
    return data_dir, cfg, selected


def _reflect_done_in_today(data_dir: Path, todo_ids: list[str]) -> None:
    """Mark ``todo_ids`` as done in today's plan, if they appear in it.

    The daily status is a separate axis from the global lifecycle, but a global
    completion is also a completion for the day, so we reflect it (only when a
    plan for today exists).
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


def _render_today(data_dir: Path) -> None:
    """Print today's plan, or a hint when there is none yet."""
    plan = store.load_day_plan(data_dir, date.today())
    if not plan.entries:
        console.print(
            "[grey62]No plan for today. Run `todo day` to build one.[/grey62]"
        )
        return
    render_history([plan])


# --------------------------------------------------------------------------- #
# Data repo management                                                        #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def init(
    repo: str = typer.Argument(..., help="Local path or URL of the data repo."),
):
    """Initialize or adopt a data repo and set it as active."""
    result = _apply_setup(repo)
    if result.adopted and not result.created_items:
        _ok(f"Adopted existing repo: {result.data_dir}")
    else:
        _ok(f"Data repo initialized: {result.data_dir}")


@app.command()
@handle_errors
def repo(
    path: str | None = typer.Argument(
        None, help="New repo (path/URL). Empty prints the active one."
    ),
):
    """Print the active data repo, or switch to another one."""
    if path is None:
        current = read_data_dir()
        if current is None:
            _err(_NO_REPO)
            raise typer.Exit(1)
        console.print(str(current))
        return
    result = _apply_setup(path)
    _ok(f"Active data repo: {result.data_dir}")


# --------------------------------------------------------------------------- #
# Mutations                                                                    #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def add(
    title: str | None = typer.Argument(None, help="Todo title."),
    category: str | None = typer.Option(None, "-c", "--category"),
    urgency: str | None = typer.Option(None, "-u", "--urgency"),
    horizon: str | None = typer.Option(None, "--horizon"),
    edit: bool = typer.Option(False, "--edit", help="Open $EDITOR after creation."),
):
    """Add a todo (interactive; any missing option triggers a prompt)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if not title:
        title = prompt.text_input("Your todo...")
        if not title:
            _err("Empty title, aborting.")
            raise typer.Exit(1)

    category = _resolve_choice(
        category, cfg.categories, label="category", header="Category"
    )
    urgency = _resolve_choice(
        urgency, cfg.urgency.values, label="urgency", header="Urgency", default="soon"
    )

    horizon = _resolve_optional_choice(
        horizon,
        cfg.horizon.values,
        label="horizon",
        header="Horizon (Esc/(none) to skip)",
    )

    todo = store.create_todo(
        data_dir,
        title=title,
        category=category,
        urgency=urgency,
        horizon=horizon,
    )
    if edit and todo.path is not None:
        open_editor(todo.path)

    _ok(f"Added: [{todo.category}/{todo.urgency}] {todo.title}")
    auto_sync(data_dir, cfg, f"add: {todo.title}")


@app.command()
@handle_errors
def done():
    """Mark todos as completed (fzf multi-selection)."""
    data_dir, cfg, selected = _pick_active(multi=True)
    for t in selected:
        store.move_to_done(t, data_dir)
    _reflect_done_in_today(data_dir, [t.id for t in selected])
    _ok(f"{len(selected)} todo(s) completed.")
    auto_sync(data_dir, cfg, f"done: {len(selected)} todo(s)")


@app.command("del")
@handle_errors
def delete():
    """Permanently delete todos (fzf multi + gum confirmation)."""
    data_dir, cfg, selected = _pick_active(multi=True)
    if not prompt.confirm(f"Permanently delete {len(selected)} todo(s)?"):
        raise prompt.Cancelled()
    for t in selected:
        store.delete_todo(t)
    _ok(f"{len(selected)} todo(s) deleted.")
    auto_sync(data_dir, cfg, f"del: {len(selected)} todo(s)")


@app.command()
@handle_errors
def edit():
    """Edit a todo body in $EDITOR (fzf single selection)."""
    data_dir, cfg, selected = _pick_active(multi=False)
    todo = selected[0]
    open_editor(todo.require_path())
    _ok(f"Edited: {todo.title}")
    auto_sync(data_dir, cfg, f"edit: {todo.title}")


# --------------------------------------------------------------------------- #
# Daily plans                                                                  #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def day():
    """Build today's plan: carry unfinished items forward, then add todos.

    On the first run of a new day, offers to carry the previous day's
    unfinished (planned/doing) items forward. Then lets you pick, via fzf,
    among the active todos not already planned today.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    today = date.today()
    active = store.list_active(data_dir)
    active_ids = {t.id for t in active}
    plan = store.load_day_plan(data_dir, today)

    # Rollover: only on the first `day` of a new day, and only for items whose
    # todo is still active (globally completed/deleted ones are dropped).
    if not store.plan_exists(data_dir, today):
        previous = store.latest_plan_before(data_dir, today)
        if previous is not None:
            carry = [
                e
                for e in previous.entries
                if e.status is not PlanStatus.DONE and e.todo_id in active_ids
            ]
            prompt = (
                f"Carry {len(carry)} unfinished item(s) "
                f"from {previous.day.isoformat()}?"
            )
            if carry and prompt.confirm(prompt):
                for e in carry:
                    plan.entries.append(PlanEntry(todo_id=e.todo_id, title=e.title))

    candidates = [t for t in active if not plan.has(t.id)]
    if candidates:
        for t in prompt.select_todos(candidates, multi=True):
            plan.entries.append(PlanEntry(todo_id=t.id, title=t.title))
    elif not plan.entries:
        console.print("[grey62]No active todo to plan.[/grey62]")
        return

    store.save_day_plan(data_dir, plan)
    render_history([plan])
    _ok(f"Today's plan: {len(plan.entries)} item(s).")
    auto_sync(data_dir, cfg, f"day: plan {today.isoformat()}")


@app.command()
@handle_errors
def doing():
    """Mark planned items of today's plan as in progress (fzf multi-select)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    today = date.today()
    plan = store.load_day_plan(data_dir, today)
    planned = {e.todo_id for e in plan.entries if e.status is PlanStatus.PLANNED}
    if not planned:
        console.print("[grey62]No planned item today.[/grey62]")
        return
    todos = [t for t in store.list_active(data_dir) if t.id in planned]
    selected = prompt.select_todos(todos, multi=True)
    if not selected:
        raise typer.Exit(1)
    for t in selected:
        entry = plan.find(t.id)
        if entry is not None:
            entry.status = PlanStatus.DOING
    store.save_day_plan(data_dir, plan)
    _ok(f"{len(selected)} item(s) in progress.")
    auto_sync(data_dir, cfg, f"doing: {len(selected)} item(s)")


@app.command()
@handle_errors
def history(
    today: bool = typer.Option(False, "--today", "-t", help="Only today's plan."),
):
    """Show each day's plan with colorized per-day statuses (git-diff feel)."""
    data_dir = require_data_dir()
    if today:
        _render_today(data_dir)
        return
    render_history(store.load_plans(data_dir))


# --------------------------------------------------------------------------- #
# Read                                                                         #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def show(
    category: str | None = typer.Argument(
        None, help="Only show this category (default: all)."
    ),
    urgency: str | None = typer.Option(None, "-u", "--urgency"),
    done_: bool = typer.Option(False, "--done", help="Show the archive."),
):
    """Show todos (rich), grouped by category and sorted.

    `todo show` shows everything; `todo show <category>` filters one category.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if done_:
        render_todos(store.list_done(data_dir), cfg, title="Archive")
        return

    todos = store.list_active(data_dir)
    if category:
        if category not in cfg.categories:
            _warn(f"unknown category: {category!r}. Known: {', '.join(cfg.categories)}")
        todos = [t for t in todos if t.category == category]
    if urgency:
        todos = [t for t in todos if t.urgency == urgency]

    render_todos(todos, cfg)


# --------------------------------------------------------------------------- #
# Manual synchronization                                                       #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def sync():
    """Force a blocking git sync (pull --rebase -> commit -> push)."""
    data_dir = require_data_dir()
    # Blocking lock: wait for any background sync to finish to avoid git
    # collisions, then run a full, guaranteed sync.
    with vcs.sync_lock(data_dir, blocking=True):
        result = vcs.sync(data_dir, push_if_unchanged=True)
    _emit_sync(result)
    if result.conflict_files:
        raise typer.Exit(1)
    if result.committed or result.pushed or result.pulled:
        _ok("Synchronized.")
    else:
        console.print("[grey62]Already up to date.[/grey62]")


@app.command("_flush", hidden=True)
def flush(data_dir: str):
    """Internal: detached background sync (spawned via `python -m pytodo _flush`)."""
    try:
        vcs.background_flush(Path(data_dir))
    except Exception:
        pass  # detached process: never crash loudly


if __name__ == "__main__":
    app()
