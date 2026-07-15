"""`todo` CLI - Typer entry point."""

from __future__ import annotations

import functools
import os
import subprocess
from datetime import date
from pathlib import Path

import typer
from rich.markup import escape

from . import gitrepo, storage, ui
from .config import (
    RepoConfig,
    load_repo_config,
    read_data_dir,
    write_data_dir,
)
from .render import console, render_todos

app = typer.Typer(
    help="Manage todos synchronized through git.",
    no_args_is_help=True,
    add_completion=False,
)

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
        except ui.Cancelled:
            console.print("[grey62]cancelled[/grey62]")
            raise typer.Exit(1) from None
        except ui.MissingTool as exc:
            _err(str(exc))
            raise typer.Exit(2) from None
        except gitrepo.RepoError as exc:
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


def _emit_sync(result: gitrepo.SyncResult) -> None:
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
    result = gitrepo.sync(data_dir, message=message, network=False)
    _emit_sync(result)
    if cfg.sync_auto:
        gitrepo.spawn_background_flush(data_dir)


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
        value = ui.choose(options, header=header, default=default)
    return _validate_choice(value, options, label)


# --------------------------------------------------------------------------- #
# Data repo management                                                        #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def init(
    repo: str = typer.Argument(..., help="Local path or URL of the data repo."),
):
    """Initialize or adopt a data repo and set it as active."""
    result = gitrepo.setup_repo(repo, confirm=ui.confirm)
    write_data_dir(result.data_dir)
    for action in result.actions:
        console.print(f"  [grey62]-[/grey62] {action}")
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
    result = gitrepo.setup_repo(path, confirm=ui.confirm)
    write_data_dir(result.data_dir)
    for action in result.actions:
        console.print(f"  [grey62]-[/grey62] {action}")
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
    deadline: str | None = typer.Option(
        None, "--deadline", help="ISO date YYYY-MM-DD."
    ),
    edit: bool = typer.Option(False, "--edit", help="Open $EDITOR after creation."),
):
    """Add a todo (interactive; any missing option triggers a prompt)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if not title:
        title = ui.text_input("Your todo...")
        if not title:
            _err("Empty title, aborting.")
            raise typer.Exit(1)

    category = _resolve_choice(
        category, cfg.categories, label="category", header="Category"
    )
    urgency = _resolve_choice(
        urgency, cfg.urgency.values, label="urgency", header="Urgency", default="soon"
    )

    if horizon is None:
        picked = ui.choose(
            ["(none)", *cfg.horizon.values], header="Horizon (Esc/(none) to skip)"
        )
        horizon = None if picked == "(none)" else picked
    if horizon is not None:
        _validate_choice(horizon, cfg.horizon.values, "horizon")

    parsed_deadline: date | None = None
    if deadline:
        try:
            parsed_deadline = date.fromisoformat(deadline)
        except ValueError:
            raise typer.BadParameter(
                "deadline must be an ISO date YYYY-MM-DD"
            ) from None

    todo = storage.create_todo(
        data_dir,
        title=title,
        category=category,
        urgency=urgency,
        horizon=horizon,
        deadline=parsed_deadline,
    )
    if edit and todo.path is not None:
        open_editor(todo.path)

    _ok(f"Added: [{todo.category}/{todo.urgency}] {todo.title}")
    auto_sync(data_dir, cfg, f"add: {todo.title}")


@app.command()
@handle_errors
def done():
    """Mark todos as completed (fzf multi-selection)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    todos = storage.list_active(data_dir)
    if not todos:
        console.print("[grey62]No active todo.[/grey62]")
        return
    selected = ui.select_todos(todos, multi=True)
    if not selected:
        raise typer.Exit(1)
    for t in selected:
        storage.move_to_done(t, data_dir)
    _ok(f"{len(selected)} todo(s) completed.")
    auto_sync(data_dir, cfg, f"done: {len(selected)} todo(s)")


@app.command("del")
@handle_errors
def delete():
    """Permanently delete todos (fzf multi + gum confirmation)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    todos = storage.list_active(data_dir)
    if not todos:
        console.print("[grey62]No active todo.[/grey62]")
        return
    selected = ui.select_todos(todos, multi=True)
    if not selected:
        raise typer.Exit(1)
    if not ui.confirm(f"Permanently delete {len(selected)} todo(s)?"):
        console.print("[grey62]cancelled[/grey62]")
        raise typer.Exit(1)
    for t in selected:
        storage.delete_todo(t)
    _ok(f"{len(selected)} todo(s) deleted.")
    auto_sync(data_dir, cfg, f"del: {len(selected)} todo(s)")


@app.command()
@handle_errors
def edit():
    """Edit a todo body in $EDITOR (fzf single selection)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    todos = storage.list_active(data_dir)
    if not todos:
        console.print("[grey62]No active todo.[/grey62]")
        return
    selected = ui.select_todos(todos, multi=False)
    if not selected:
        raise typer.Exit(1)
    todo = selected[0]
    if todo.path is None:
        raise FileNotFoundError(f"todo not found: {todo.id}")
    open_editor(todo.path)
    _ok(f"Edited: {todo.title}")
    auto_sync(data_dir, cfg, f"edit: {todo.title}")


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
    today: bool = typer.Option(
        False, "--today", help="Today horizon + today's and overdue deadlines."
    ),
    done_: bool = typer.Option(False, "--done", help="Show the archive."),
):
    """Show todos (rich), grouped by category and sorted.

    `todo show` shows everything; `todo show <category>` filters one category.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if done_:
        render_todos(storage.list_done(data_dir), cfg, title="Archive")
        return

    todos = storage.list_active(data_dir)
    if category:
        if category not in cfg.categories:
            _warn(f"unknown category: {category!r}. Known: {', '.join(cfg.categories)}")
        todos = [t for t in todos if t.category == category]
    if urgency:
        todos = [t for t in todos if t.urgency == urgency]
    if today:
        d = date.today()
        todos = [
            t
            for t in todos
            if t.horizon == "today" or (t.deadline is not None and t.deadline <= d)
        ]

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
    with gitrepo.sync_lock(data_dir, blocking=True):
        result = gitrepo.sync(data_dir, push_if_unchanged=True)
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
        gitrepo.background_flush(Path(data_dir))
    except Exception:
        pass  # detached process: never crash loudly


if __name__ == "__main__":
    app()
