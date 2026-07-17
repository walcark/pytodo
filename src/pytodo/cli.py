"""`todo` CLI - Typer entry point.

The command surface follows GTD's five steps (see ``docs/model.md``):

- capture  : ``todo add "..."``   straight to the inbox, zero prompts
- clarify  : ``todo clarify``     empties the inbox, one decision at a time
- organize : the states, contexts and projects themselves
- reflect  : ``todo review``
- engage   : ``todo day`` / ``todo doing`` / ``todo next`` / ``todo show``
"""

from __future__ import annotations

import functools
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import typer
from rich.markup import escape

from . import prompt, store, vcs
from .plan import PlanEntry, PlanStatus
from .settings import read_data_dir, write_data_dir
from .todo import Todo, TodoState, sort_key
from .view import console, render_history, render_todos
from .vocabulary import RepoConfig, load_repo_config, save_repo_config

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
# Capture                                                                      #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def add(
    title: str | None = typer.Argument(None, help="Todo title."),
    edit: bool = typer.Option(False, "--edit", help="Open $EDITOR after creation."),
):
    """Capture a todo into the inbox.

    Deliberately asks nothing beyond the title: capture must cost a second and
    zero decisions, or you stop capturing. `todo clarify` does the thinking
    later.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if not title:
        title = prompt.text_input("Your todo...")
        if not title:
            _err("Empty title, aborting.")
            raise typer.Exit(1)

    todo = store.create_todo(data_dir, title=title)
    if edit and todo.path is not None:
        open_editor(todo.path)

    inbox = len(store.list_by_state(data_dir, TodoState.INBOX))
    _ok(f"Captured: {todo.title}  [inbox: {inbox}]")
    auto_sync(data_dir, cfg, f"add: {todo.title}")


# --------------------------------------------------------------------------- #
# Clarify                                                                      #
# --------------------------------------------------------------------------- #


def _clarify_actionable(data_dir: Path, cfg: RepoConfig, todo: Todo) -> str:
    """Clarify one actionable item. Return a short log line."""
    kind = prompt.choose(
        ["single action", "multi-step (project)"],
        header=f"{todo.title}  |  is it multi-step?",
    )

    project_id = None
    if kind == "multi-step (project)":
        outcome = prompt.text_input("What does 'done' look like?", default=todo.title)
        area = _resolve_optional_choice(
            None, cfg.areas, label="area", header="Area (Esc/(none) to skip)"
        )
        project = store.create_project(
            data_dir, title=todo.title, outcome=outcome or None, area=area
        )
        project_id = project.id
        todo.title = prompt.text_input(
            "First next action?", default=f"Plan: {todo.title}"
        )
        todo.area = area

    disposition = prompt.choose(
        ["next action", "under 2 min (do it now)", "waiting on someone"],
        header=f"{todo.title}  |  what happens to it?",
    )

    todo.project = project_id
    if todo.area is None:
        todo.area = _resolve_optional_choice(
            None, cfg.areas, label="area", header="Area (Esc/(none) to skip)"
        )

    if disposition == "under 2 min (do it now)":
        store.save_todo(todo)
        store.move_to_done(todo, data_dir)
        return f"done (2-min rule): {todo.title}"

    if disposition == "waiting on someone":
        todo.state = TodoState.WAITING
        todo.waiting_on = prompt.text_input("Waiting on whom?") or None
        store.save_todo(todo)
        return f"waiting on {todo.waiting_on or '?'}: {todo.title}"

    todo.state = TodoState.NEXT
    todo.context = _resolve_choice(
        None, cfg.contexts, label="context", header="Context (what do you need?)"
    )
    store.save_todo(todo)
    return f"next {todo.context}: {todo.title}"


def _clarify_one(data_dir: Path, cfg: RepoConfig, todo: Todo) -> str:
    """Walk GTD's clarify tree for a single inbox item. Return a log line."""
    actionable = prompt.choose(
        ["yes", "no"], header=f"{todo.title}  |  is it actionable?"
    )
    if actionable == "no":
        disposition = prompt.choose(
            ["someday/maybe", "trash"], header=f"{todo.title}  |  then what?"
        )
        if disposition == "trash":
            store.delete_todo(todo)
            return f"trashed: {todo.title}"
        todo.state = TodoState.SOMEDAY
        store.save_todo(todo)
        return f"someday: {todo.title}"

    return _clarify_actionable(data_dir, cfg, todo)


@app.command()
@handle_errors
def clarify():
    """Empty the inbox, one decision at a time (GTD's clarify step).

    Walks each captured item through the decision tree: actionable or not,
    multi-step or not, then the two-minute rule, delegation, or a next action
    with a context.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    inbox = sorted(store.list_by_state(data_dir, TodoState.INBOX), key=sort_key)
    if not inbox:
        _ok("Inbox zero.")
        return

    done_lines: list[str] = []
    for i, todo in enumerate(inbox, 1):
        console.print(f"\n[bold cyan]({i}/{len(inbox)})[/bold cyan] {todo.title}")
        try:
            done_lines.append(_clarify_one(data_dir, cfg, todo))
        except prompt.Cancelled:
            console.print("[grey62]stopped; the rest stays in the inbox[/grey62]")
            break

    if not done_lines:
        return
    console.print()
    for line in done_lines:
        console.print(f"  [grey62]-[/grey62] {line}")
    _ok(f"{len(done_lines)} item(s) clarified.")
    auto_sync(data_dir, cfg, f"clarify: {len(done_lines)} item(s)")


# --------------------------------------------------------------------------- #
# Mutations                                                                    #
# --------------------------------------------------------------------------- #


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
# Daily plans (engage)                                                         #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def day():
    """Build today's plan: carry unfinished items forward, then add todos.

    On the first run of a new day, offers to carry the previous day's
    unfinished (planned/doing) items forward. Then lets you pick, via fzf,
    among the `next` actions not already planned today.
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
            question = (
                f"Carry {len(carry)} unfinished item(s) "
                f"from {previous.day.isoformat()}?"
            )
            if carry and prompt.confirm(question):
                for e in carry:
                    plan.entries.append(PlanEntry(todo_id=e.todo_id, title=e.title))

    # Only `next` actions are pickable: a day plan you cannot act on is how a
    # list stops being trusted.
    candidates = [t for t in active if t.state is TodoState.NEXT and not plan.has(t.id)]
    if candidates:
        for t in prompt.select_todos(sorted(candidates, key=sort_key), multi=True):
            plan.entries.append(PlanEntry(todo_id=t.id, title=t.title))
    elif not plan.entries:
        console.print("[grey62]No next action to plan. Run `todo clarify`.[/grey62]")
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
# Read (engage)                                                                #
# --------------------------------------------------------------------------- #


@app.command("next")
@handle_errors
def next_(
    context: str | None = typer.Option(
        None, "-c", "--context", help="Only this context (e.g. @computer)."
    ),
):
    """List next actions, optionally filtered by context.

    This is the engage question: "I am here, with this to hand, what can I do?"
    """
    data_dir = require_data_dir()
    todos = store.list_by_state(data_dir, TodoState.NEXT)
    if context:
        todos = [t for t in todos if t.context == context]
    render_todos(todos, title=f"Next actions{f' - {context}' if context else ''}")


@app.command()
@handle_errors
def show(
    area: str | None = typer.Argument(None, help="Only show this area (default: all)."),
    state: str | None = typer.Option(None, "-s", "--state", help="Filter by state."),
    done_: bool = typer.Option(False, "--done", help="Show the archive."),
):
    """Show todos (rich), grouped by area and oldest first.

    `todo show` shows everything; `todo show <area>` filters one area.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if done_:
        render_todos(store.list_done(data_dir), title="Archive")
        return

    todos = store.list_active(data_dir)
    if area:
        if area not in cfg.areas:
            _warn(f"unknown area: {area!r}. Known: {', '.join(cfg.areas)}")
        todos = [t for t in todos if t.area == area]
    if state:
        wanted = _validate_choice(state, [s.value for s in TodoState], label="state")
        todos = [t for t in todos if t.state.value == wanted]

    render_todos(todos)


# --------------------------------------------------------------------------- #
# Reflect                                                                      #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def review():
    """Report what GTD says is broken: the weekly review, checked by the tool.

    Four things rot silently, so the tool watches them: a filling inbox, a
    project nothing is advancing, a next action you cannot select because it
    has no context, and someone you forgot you were waiting on.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    active = store.list_active(data_dir)
    problems = 0

    inbox = sorted([t for t in active if t.state is TodoState.INBOX], key=sort_key)
    if inbox:
        problems += 1
        oldest = inbox[0]
        age = ""
        if oldest.created is not None:
            days = (datetime.now() - oldest.created).days
            age = f", oldest sat {days} day(s)"
        _warn(f"Inbox: {len(inbox)} item(s) to clarify{age}")

    stalled = store.stalled_projects(data_dir)
    if stalled:
        problems += 1
        _warn(f"{len(stalled)} stalled project(s) - no next action:")
        for p in stalled:
            console.print(f"  [grey62]-[/grey62] {p.title}")

    contextless = [t for t in active if t.state is TodoState.NEXT and not t.context]
    if contextless:
        problems += 1
        _warn(f"{len(contextless)} next action(s) with no context (unselectable):")
        for t in sorted(contextless, key=sort_key):
            console.print(f"  [grey62]-[/grey62] {t.title}")

    cutoff = datetime.now() - timedelta(days=cfg.waiting_stale_days)
    stale = [
        t
        for t in active
        if t.state is TodoState.WAITING and t.created is not None and t.created < cutoff
    ]
    if stale:
        problems += 1
        _warn(f"{len(stale)} item(s) waiting over {cfg.waiting_stale_days} day(s):")
        for t in sorted(stale, key=sort_key):
            console.print(f"  [grey62]-[/grey62] {t.title} ({t.waiting_on or '?'})")

    if not problems:
        _ok("Nothing to fix: inbox zero, every project moving.")


# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #

config_app = typer.Typer(help="Read and edit the shared vocabulary.")
app.add_typer(config_app, name="config")


def _edit_vocabulary(kind: str, action: str, value: str) -> None:
    """Add or remove one value from ``areas``/``contexts`` and sync.

    Editing the vocabulary is a mutation like any other: the file is versioned
    and shared across devices, so it commits and syncs rather than being
    treated as a local preference.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    values: list[str] = getattr(cfg, kind)

    if action == "add":
        if value in values:
            _warn(f"{value!r} is already a known {kind[:-1]}.")
            return
        values.append(value)
    else:
        if value not in values:
            _err(f"unknown {kind[:-1]}: {value!r}. Known: {', '.join(values)}")
            raise typer.Exit(1)
        # Removing a value still in use would silently orphan those todos.
        field = "context" if kind == "contexts" else "area"
        users = [t for t in store.list_active(data_dir) if getattr(t, field) == value]
        if users:
            _err(f"{len(users)} todo(s) still use {value!r}:")
            for t in users[:5]:
                console.print(f"  [grey62]-[/grey62] {t.title}")
            _err("Reassign them first, or edit config.toml by hand.")
            raise typer.Exit(1)
        values.remove(value)

    save_repo_config(data_dir, cfg)
    _ok(f"{kind[:-1]} {action}: {value}")
    auto_sync(data_dir, cfg, f"config: {action} {kind[:-1]} {value}")


@config_app.callback(invoke_without_command=True)
def config_show(ctx: typer.Context) -> None:
    """Print the shared vocabulary."""
    if ctx.invoked_subcommand is not None:
        return
    cfg = load_repo_config(require_data_dir())
    console.print(f"[bold]areas[/bold]     {', '.join(cfg.areas)}")
    console.print(f"[bold]contexts[/bold]  {', '.join(cfg.contexts)}")
    console.print(f"[bold]waiting[/bold]   stale after {cfg.waiting_stale_days} day(s)")


@config_app.command("edit")
@handle_errors
def config_edit():
    """Open the shared config.toml in $EDITOR."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    open_editor(data_dir / "config.toml")
    auto_sync(data_dir, cfg, "config: edit")


@config_app.command("context")
@handle_errors
def config_context(
    action: str = typer.Argument(..., help="add | rm"),
    value: str = typer.Argument(..., help="e.g. @gym"),
):
    """Add or remove a context."""
    verb = _validate_choice(action, ["add", "rm"], "action")
    _edit_vocabulary("contexts", verb, value)


@config_app.command("area")
@handle_errors
def config_area(
    action: str = typer.Argument(..., help="add | rm"),
    value: str = typer.Argument(..., help="e.g. health"),
):
    """Add or remove an area."""
    _edit_vocabulary("areas", _validate_choice(action, ["add", "rm"], "action"), value)


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
