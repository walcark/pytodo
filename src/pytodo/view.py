"""Terminal rendering of `todo show` with rich."""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import RepoConfig
from .plan import DayPlan, PlanStatus
from .todo import Todo, make_sort_key

# Max table width: tables adapt to the terminal width but never exceed this
# bound (readability on wide screens).
MAX_TABLE_WIDTH = 100

# Shared console for the CLI's short messages. Table rendering uses a console
# sized to the real terminal (see below).
console = Console()


def terminal_width(default: int = 80) -> int:
    """Return the real terminal width via an ioctl on the output fd.

    We query :func:`os.get_terminal_size` directly rather than the ``COLUMNS``
    environment variable (which rich/shutil consult first): that variable is
    not refreshed when the window is shrunk or split, which would make the
    table overflow and cut its rightmost column. The ioctl always reflects the
    current size.

    Parameters
    ----------
    default : int, optional
        Fallback width when the output is not a terminal.

    Returns
    -------
    int
        The current terminal width in columns.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            return os.get_terminal_size(stream.fileno()).columns
        except (OSError, ValueError, AttributeError):
            continue
    return default


def _urgency_cell(urgency: str, cfg: RepoConfig) -> Text:
    return Text(urgency, style=cfg.urgency.style(urgency))


def _horizon_cell(t: Todo) -> Text:
    return Text(t.horizon or "", style="grey62")


def render_todos(
    todos: list[Todo],
    cfg: RepoConfig,
    *,
    title: str | None = None,
) -> None:
    """Render todos grouped by category, sorted by urgency then horizon.

    Parameters
    ----------
    todos : list of Todo
        Todos to display.
    cfg : RepoConfig
        Active repo config, providing the urgency/horizon orderings and colors.
    title : str, optional
        Optional heading printed above the tables.
    """
    sort_key = make_sort_key(cfg.urgency.values, cfg.horizon.values)

    # Console sized to the REAL terminal so rendering never exceeds the current
    # pane (nothing is cut), and the table is capped at MAX.
    term = terminal_width()
    out = Console(width=term)
    table_width = min(term, MAX_TABLE_WIDTH)

    if not todos:
        out.print("[grey62]No todo.[/grey62]")
        return

    if title:
        out.print(f"[bold]{title}[/bold]")

    by_category: dict[str, list[Todo]] = {}
    for t in todos:
        by_category.setdefault(t.category or "(uncategorized)", []).append(t)

    for category in sorted(by_category):
        items = sorted(by_category[category], key=sort_key)
        table = Table(
            title=f"[bold cyan]{category}[/bold cyan]",
            title_justify="left",
            show_edge=False,
            pad_edge=False,
            width=table_width,
        )
        # urgency/horizon stay on one line; the title absorbs the remaining
        # width and wraps (fold) instead of being truncated.
        table.add_column("urgency", no_wrap=True)
        table.add_column("title", ratio=1, overflow="fold")
        table.add_column("horizon", no_wrap=True)
        for t in items:
            table.add_row(
                _urgency_cell(t.urgency, cfg), Text(t.title), _horizon_cell(t)
            )
        out.print(table)
        out.print()


# Per-day status glyphs and colors for `todo history` (git-diff feel).
_PLAN_GLYPH = {
    PlanStatus.DONE: ("✓", "green"),
    PlanStatus.DOING: ("◐", "yellow"),
    PlanStatus.PLANNED: ("○", "grey62"),
}


def render_history(plans: list[DayPlan]) -> None:
    """Print each day's plan, one colorized line per entry.

    Parameters
    ----------
    plans : list of DayPlan
        Daily plans, oldest first (most recent shown last).
    """
    if not plans:
        console.print("[grey62]No daily plan yet.[/grey62]")
        return
    for plan in plans:
        console.print(f"[bold]{plan.day.isoformat()}[/bold]")
        for entry in plan.entries:
            glyph, style = _PLAN_GLYPH[entry.status]
            console.print(Text(f"  {glyph} {entry.title}", style=style))
        console.print()
