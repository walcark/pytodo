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

from neverland.core import service, store, vcs
from neverland.core.plan import PlanEntry, PlanStatus
from neverland.core.project import Project
from neverland.core.routine import MONTH_NAMES, Freq, Recurrence, Routine
from neverland.core.settings import read_data_dir, write_data_dir
from neverland.core.todo import Todo, TodoState, sort_key
from neverland.core.vocabulary import RepoConfig, load_repo_config

from . import prompt
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
    data_dir = require_data_dir()
    _materialize_due(data_dir)
    _render_today(data_dir)


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
        except typer.Exit:
            # typer.Exit subclasses RuntimeError, so it has to be re-raised
            # before the RuntimeError arm below swallows every clean exit and
            # reports it as a failure with the exit code as its message.
            raise
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
    """Render the warnings/conflicts of a sync returned by the service layer."""
    for w in result.warnings:
        _warn(w)
    if result.conflict_files:
        _err("Rebase conflict on: " + ", ".join(result.conflict_files))
        _err("Resolve it manually in the repo, then run `todo sync`.")


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


def _materialize_due(data_dir: Path) -> None:
    """Spawn the routines that have come due, so looking at your day shows them.

    The server does this on its poller; the CLI has no daemon, so it happens
    whenever you look at (or build) today's plan. It is idempotent: nothing is
    written unless a routine is genuinely due.
    """
    cfg = load_repo_config(data_dir)
    for todo in service.materialize_routines(data_dir, cfg):
        console.print(f"[grey62]routine due:[/grey62] {escape(todo.title)}")


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
    project: bool = typer.Option(
        False, "--project", help="Pick a project to capture into."
    ),
):
    """Capture a todo into the inbox.

    Deliberately asks nothing beyond the title: capture must cost a second and
    zero decisions, or you stop capturing. `todo clarify` does the thinking
    later. `--project` only pre-links it to an outcome you already know; it
    still lands in the inbox, unclarified.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    project_id = None
    if project:
        project_id = _pick_project(data_dir, "Capture into which project?").id

    if not title:
        title = prompt.text_input("Your todo...")
        if not title:
            _err("Empty title, aborting.")
            raise typer.Exit(1)

    if edit:
        # The editor writes the body between creation and commit, so this path
        # composes the primitives directly rather than the one-shot `capture`.
        todo = store.create_todo(data_dir, title=title, project=project_id)
        if todo.path is not None:
            open_editor(todo.path)
        sync = service.auto_sync(data_dir, cfg, f"add: {todo.title}")
    else:
        todo, sync = service.capture(data_dir, cfg, title, project=project_id)

    inbox = len(store.list_by_state(data_dir, TodoState.INBOX))
    _ok(f"Captured: {todo.title}  [inbox: {inbox}]")
    _emit_sync(sync)


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
    _emit_sync(service.auto_sync(data_dir, cfg, f"clarify: {len(done_lines)} item(s)"))


# --------------------------------------------------------------------------- #
# Mutations                                                                    #
# --------------------------------------------------------------------------- #


@app.command()
@handle_errors
def done():
    """Mark todos as completed (fzf multi-selection)."""
    data_dir, cfg, selected = _pick_active(multi=True)
    sync = service.complete(data_dir, cfg, selected)
    _ok(f"{len(selected)} todo(s) completed.")
    _emit_sync(sync)


@app.command()
@handle_errors
def reopen():
    """Undo a completion: bring archived todos back to the next list.

    They come back as ``next``, since the state held before completion is not
    recorded; use ``todo edit`` afterwards if one belonged on another list.
    """
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    done_todos = store.list_done(data_dir)
    if not done_todos:
        console.print("[grey62]No completed todo.[/grey62]")
        raise typer.Exit(0)
    done_todos.sort(key=lambda t: t.completed or datetime.min, reverse=True)
    selected = prompt.select_todos(done_todos, multi=True)
    if not selected:
        raise typer.Exit(1)
    sync = service.reopen(data_dir, cfg, selected)
    _ok(f"{len(selected)} todo(s) reopened.")
    _emit_sync(sync)


@app.command("del")
@handle_errors
def delete():
    """Permanently delete todos (fzf multi + gum confirmation)."""
    data_dir, cfg, selected = _pick_active(multi=True)
    if not prompt.confirm(f"Permanently delete {len(selected)} todo(s)?"):
        raise prompt.Cancelled()
    sync = service.delete(data_dir, cfg, selected)
    _ok(f"{len(selected)} todo(s) deleted.")
    _emit_sync(sync)


@app.command()
@handle_errors
def edit():
    """Edit a todo body in $EDITOR (fzf single selection)."""
    data_dir, cfg, selected = _pick_active(multi=False)
    todo = selected[0]
    open_editor(todo.require_path())
    _ok(f"Edited: {todo.title}")
    _emit_sync(service.auto_sync(data_dir, cfg, f"edit: {todo.title}"))


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
    _materialize_due(data_dir)  # due routines join the plan before we build it
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
    _emit_sync(service.auto_sync(data_dir, cfg, f"day: plan {today.isoformat()}"))


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
    _emit_sync(service.auto_sync(data_dir, cfg, f"doing: {len(selected)} item(s)"))


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
    """Render the outcome of a vocabulary edit; the rule lives in the service."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    try:
        sync = service.set_vocabulary(data_dir, cfg, kind, action, value)
    except service.DuplicateValue as exc:
        # Adding a value already present is a no-op, not a failure.
        _warn(str(exc))
        return
    except service.ValueInUse as exc:
        _err(f"{exc}:")
        for t in exc.users[:5]:
            console.print(f"  [grey62]-[/grey62] {t.title}")
        _err("Reassign them first, or edit config.toml by hand.")
        raise typer.Exit(1) from None
    except service.UnknownValue as exc:
        _err(str(exc))
        raise typer.Exit(1) from None
    _ok(f"{kind[:-1]} {action}: {value}")
    _emit_sync(sync)


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
    _emit_sync(service.auto_sync(data_dir, cfg, "config: edit"))


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
def unplan():
    """Remove items from today's plan (the todos themselves are untouched)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    plan = store.load_day_plan(data_dir, date.today())
    if not plan.entries:
        _warn("Nothing planned today.")
        return

    by_label = {f"{e.title}  [{e.status.value}]": e for e in plan.entries}
    chosen = prompt.choose(list(by_label), header="Remove from today's plan")
    entry = by_label[chosen]
    _ok(f"Unplanned: {entry.title}")
    _emit_sync(service.plan_remove(data_dir, cfg, entry.todo_id))


# --------------------------------------------------------------------------- #
# Projects                                                                     #
# --------------------------------------------------------------------------- #

project_app = typer.Typer(help="Outcomes that need more than one action.")
app.add_typer(project_app, name="project")


def _pick_project(data_dir: Path, header: str) -> Project:
    """Pick one active project via fzf, or exit when there is none."""
    projects = store.list_active_projects(data_dir)
    if not projects:
        _warn("No active projects. Create one with `todo project add`.")
        raise typer.Exit(0)
    by_label = {p.title: p for p in projects}
    return by_label[prompt.choose(list(by_label), header=header)]


@project_app.callback(invoke_without_command=True)
def project_show(ctx: typer.Context) -> None:
    """List the active projects, flagging the ones nothing is advancing."""
    if ctx.invoked_subcommand is not None:
        return
    data_dir = require_data_dir()
    projects = store.list_active_projects(data_dir)
    if not projects:
        console.print("[grey62]No projects. Add one with `todo project add`.[/grey62]")
        return
    active = store.list_active(data_dir)
    for project in projects:
        actions = [t for t in active if t.project == project.id]
        nexts = [t for t in actions if t.state is TodoState.NEXT]
        flag = (
            f"[cyan]{len(nexts)} next[/cyan]" if nexts else "[yellow]stalled[/yellow]"
        )
        console.print(
            f"[bold]{escape(project.title)}[/bold]  {flag}  "
            f"[grey62]{len(actions)} action(s)[/grey62]"
        )
        for todo in sorted(actions, key=sort_key):
            console.print(f"  [grey62]-[/grey62] {prompt.format_line(todo)}")


@project_app.command("add")
@handle_errors
def project_add(
    title: str | None = typer.Argument(None, help="Project name."),
) -> None:
    """Create a project (the outcome you are after)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if not title:
        title = prompt.text_input("Project name...")
        if not title:
            _err("Empty name, aborting.")
            raise typer.Exit(1)

    outcome = prompt.text_input("What does done look like? (optional)") or None
    area = _resolve_optional_choice(None, cfg.areas, label="area", header="Area")

    project, sync = service.add_project(
        data_dir, cfg, title=title, outcome=outcome, area=area
    )
    _ok(f"Project: {project.title}")
    _warn("No next action yet: capture one with `todo add --project`.")
    _emit_sync(sync)


# --------------------------------------------------------------------------- #
# Routines (recurring todos)                                                   #
# --------------------------------------------------------------------------- #

routine_app = typer.Typer(help="Recurring todos that spawn on a schedule.")
app.add_typer(routine_app, name="routine")

_FREQ_LABELS = {
    "every N days": Freq.DAYS,
    "weekly (given weekdays)": Freq.WEEKLY,
    "monthly (day of the month)": Freq.MONTHLY,
    "yearly (month and day)": Freq.YEARLY,
}


def _pick_routine(data_dir: Path, header: str) -> Routine:
    """Pick one routine via fzf, or exit when there is none."""
    routines = store.list_routines(data_dir)
    if not routines:
        _warn("No routines yet. Create one with `todo routine add`.")
        raise typer.Exit(0)
    by_label = {f"{r.title}  ({r.recurrence.describe()})": r for r in routines}
    return by_label[prompt.choose(list(by_label), header=header)]


def _ask_recurrence() -> Recurrence:
    """Build a recurrence by prompting for the mode, then its one parameter."""
    freq = _FREQ_LABELS[prompt.choose(list(_FREQ_LABELS), header="Repeats")]
    if freq is Freq.DAYS:
        raw = prompt.text_input("Every how many days?", default="3")
        return Recurrence(freq=freq, interval=max(int(raw or 3), 1))
    if freq is Freq.WEEKLY:
        raw = prompt.text_input("Which weekdays? (e.g. mon,wed,sat)", default="mon")
        names = [n.strip().lower() for n in raw.split(",") if n.strip()]
        return Recurrence.from_dict({"freq": "weekly", "weekdays": names})
    if freq is Freq.MONTHLY:
        raw = prompt.text_input("Which day of the month? (1-31)", default="1")
        return Recurrence.from_dict({"freq": "monthly", "monthday": int(raw or 1)})
    month = MONTH_NAMES.index(prompt.choose(MONTH_NAMES, header="Month")) + 1
    day = prompt.text_input("Which day of that month?", default="1")
    return Recurrence.from_dict(
        {"freq": "yearly", "month": month, "day": int(day or 1)}
    )


@routine_app.callback(invoke_without_command=True)
def routine_show(ctx: typer.Context) -> None:
    """List the routines and when each one next fires."""
    if ctx.invoked_subcommand is not None:
        return
    routines = store.list_routines(require_data_dir())
    if not routines:
        console.print("[grey62]No routines. Add one with `todo routine add`.[/grey62]")
        return
    for r in routines:
        paused = "" if r.active else " [grey62](paused)[/grey62]"
        lead = f" [grey62]{r.lead}d before[/grey62]" if r.lead else ""
        console.print(
            f"[bold]{escape(r.title)}[/bold]{paused}  "
            f"[cyan]{r.recurrence.describe()}[/cyan]{lead}  "
            f"[grey62]next {r.next_due}[/grey62]"
        )


@routine_app.command("add")
@handle_errors
def routine_add(
    title: str | None = typer.Argument(None, help="Routine title."),
) -> None:
    """Create a recurring routine (prompts for the schedule)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)

    if not title:
        title = prompt.text_input("Routine title...")
        if not title:
            _err("Empty title, aborting.")
            raise typer.Exit(1)

    recurrence = _ask_recurrence()
    context = _resolve_optional_choice(
        None, cfg.contexts, label="context", header="Context"
    )
    area = _resolve_optional_choice(None, cfg.areas, label="area", header="Area")
    lead = int(prompt.text_input("Show how many days early?", default="0") or 0)

    routine, sync = service.add_routine(
        data_dir,
        cfg,
        Routine(
            id="",
            title=title,
            recurrence=recurrence,
            context=context,
            area=area,
            lead=max(lead, 0),
        ),
    )
    _ok(f"Routine: {routine.title}  [{routine.recurrence.describe()}]")
    _materialize_due(data_dir)  # surface it right away when already due
    _emit_sync(sync)


@routine_app.command("edit")
@handle_errors
def routine_edit() -> None:
    """Edit a routine in $EDITOR (its schedule is reseeded if the rule changed)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    routine = _pick_routine(data_dir, "Edit which routine?")
    before = routine.recurrence

    open_editor(routine.require_path())

    edited = store.find_routine(data_dir, routine.id)
    if edited is None:
        _err("Routine file disappeared.")
        raise typer.Exit(1)
    if edited.recurrence != before:
        # A changed rule must not keep firing on the schedule it no longer has.
        edited.next_due = edited.recurrence.first_on_or_after(date.today())
        _warn(f"Schedule changed: next occurrence {edited.next_due}")

    _ok(f"Edited: {edited.title}")
    _emit_sync(service.update_routine(data_dir, cfg, edited))


@routine_app.command("pause")
@handle_errors
def routine_pause() -> None:
    """Pause or resume a routine (a paused routine spawns nothing)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    routine = _pick_routine(data_dir, "Pause/resume which routine?")
    routine.active = not routine.active
    _ok(f"{'Resumed' if routine.active else 'Paused'}: {routine.title}")
    _emit_sync(service.update_routine(data_dir, cfg, routine))


@routine_app.command("rm")
@handle_errors
def routine_rm() -> None:
    """Delete a routine (its already-spawned occurrences are kept)."""
    data_dir = require_data_dir()
    cfg = load_repo_config(data_dir)
    routine = _pick_routine(data_dir, "Delete which routine?")
    if not prompt.confirm(f"Delete routine {routine.title!r}?"):
        console.print("[grey62]Aborted.[/grey62]")
        return
    _ok(f"Deleted: {routine.title}")
    _emit_sync(service.remove_routine(data_dir, cfg, routine))


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


if __name__ == "__main__":
    app()
