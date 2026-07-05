"""Terminal rendering of `todo show` with rich."""

from __future__ import annotations

import os
import sys
from datetime import date

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import Todo

URGENCY_STYLE = {"now": "bold red", "soon": "yellow", "someday": "grey62"}

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


def _urgency_cell(urgency: str) -> Text:
    return Text(urgency, style=URGENCY_STYLE.get(urgency, ""))


def _deadline_cell(t: Todo, today: date) -> Text:
    if t.deadline is None:
        return Text(t.horizon or "", style="grey62")
    if t.is_overdue(today):
        return Text(f"⚠ {t.deadline.isoformat()}", style="bold red")
    return Text(t.deadline.isoformat())


def render_todos(todos: list[Todo], *, today: date | None = None, title: str | None = None) -> None:
    """Render todos grouped by category, sorted by urgency then deadline.

    Parameters
    ----------
    todos : list of Todo
        Todos to display.
    today : datetime.date, optional
        Reference date for overdue detection, defaults to today.
    title : str, optional
        Optional heading printed above the tables.
    """
    today = today or date.today()

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
        items = sorted(by_category[category], key=lambda t: t.sort_key())
        table = Table(
            title=f"[bold cyan]{category}[/bold cyan]",
            title_justify="left",
            show_edge=False,
            pad_edge=False,
            width=table_width,
        )
        # urgency/deadline stay on one line; the title absorbs the remaining
        # width and wraps (fold) instead of being truncated.
        table.add_column("urgency", no_wrap=True)
        table.add_column("title", ratio=1, overflow="fold")
        table.add_column("deadline", no_wrap=True)
        for t in items:
            table.add_row(_urgency_cell(t.urgency), Text(t.title), _deadline_cell(t, today))
        out.print(table)
        out.print()
