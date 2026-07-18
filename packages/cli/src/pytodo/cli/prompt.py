"""Terminal interaction layer, isolated to be mockable in tests.

- ``fzf`` (required) for any selection within an existing list.
- ``gum`` (optional) for free-text input and confirmations, with graceful
  degradation to :func:`input` when ``gum`` is absent.

User cancellation (Esc in fzf, Ctrl-C in gum) is surfaced through
:class:`Cancelled`, which the CLI turns into a clean non-zero exit (no
traceback).
"""

from __future__ import annotations

import shutil
import subprocess

from pytodo.core.todo import Todo


class Cancelled(Exception):
    """The user cancelled the interaction (Esc / Ctrl-C)."""


class MissingTool(Exception):
    """A required external tool is missing."""


def _has(tool: str) -> bool:
    return shutil.which(tool) is not None


def ensure_fzf() -> None:
    """Raise :class:`MissingTool` if ``fzf`` is not installed."""
    if not _has("fzf"):
        raise MissingTool(
            "fzf is required for this command.\n"
            "Install it, e.g.: `sudo dnf install fzf` or `pixi global install fzf`."
        )


# --------------------------------------------------------------------------- #
# fzf                                                                          #
# --------------------------------------------------------------------------- #


def _run_fzf(lines: list[str], args: list[str]) -> list[str]:
    ensure_fzf()
    proc = subprocess.run(
        ["fzf", *args],
        input="\n".join(lines),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 130:  # Esc / Ctrl-C
        raise Cancelled()
    if proc.returncode == 1:  # no match
        return []
    if proc.returncode not in (0,):
        raise RuntimeError(proc.stderr.strip() or "fzf failed")
    return [line for line in proc.stdout.splitlines() if line]


def choose(
    options: list[str], *, header: str | None = None, default: str | None = None
) -> str:
    """Pick a single value from a small list via fzf.

    Parameters
    ----------
    options : list of str
        Candidate values.
    header : str, optional
        fzf header line.
    default : str, optional
        Value moved to the top of the list to act as the preselected default.

    Returns
    -------
    str
        The selected value.

    Raises
    ------
    Cancelled
        If the user cancels or selects nothing.
    """
    ordered = list(options)
    if default and default in ordered:
        ordered.remove(default)
        ordered.insert(0, default)
    args = ["--height=~40%", "--reverse", "--no-multi"]
    if header:
        args += ["--header", header]
    selected = _run_fzf(ordered, args)
    if not selected:
        raise Cancelled()
    return selected[0]


def select_todos(todos: list[Todo], *, multi: bool, preview: bool = True) -> list[Todo]:
    """Select todos via fzf, with a formatted line and a file preview.

    Parameters
    ----------
    todos : list of Todo
        Candidate todos.
    multi : bool
        Allow multi-selection (Tab).
    preview : bool, optional
        Show the file content in the fzf preview window.

    Returns
    -------
    list of Todo
        The selected todos (possibly empty).
    """
    if not todos:
        return []
    by_path: dict[str, Todo] = {}
    lines: list[str] = []
    for t in todos:
        by_path[str(t.path)] = t
        lines.append(f"{format_line(t)}\t{t.path}")

    args = [
        "--height=~60%",
        "--reverse",
        "--delimiter",
        "\t",
        "--with-nth",
        "1",
    ]
    args += ["--multi"] if multi else ["--no-multi"]
    if preview:
        args += ["--preview", "cat -- {2}", "--preview-window", "right:55%:wrap"]

    selected = _run_fzf(lines, args)
    result = []
    for line in selected:
        path = line.split("\t")[-1]
        if path in by_path:
            result.append(by_path[path])
    return result


def format_line(t: Todo) -> str:
    """Return the fzf line ``[state] [context] title (area)``.

    Context comes before the title because it is the axis you scan on: the
    question being answered is "what can I act on right now". Area trails in
    parentheses, since it only ever groups.
    """
    context = f" [{t.context}]" if t.context else ""
    area = f" ({t.area})" if t.area else ""
    return f"[{t.state.value}]{context} {t.title}{area}"


# --------------------------------------------------------------------------- #
# gum (with fallback)                                                          #
# --------------------------------------------------------------------------- #


def text_input(placeholder: str = "", *, default: str = "") -> str:
    """Read a free-text line via ``gum input``, falling back to :func:`input`.

    Parameters
    ----------
    placeholder : str, optional
        Placeholder shown in the input box.
    default : str, optional
        Prefilled value.

    Returns
    -------
    str
        The entered text (stripped).

    Raises
    ------
    Cancelled
        If the user cancels.
    """
    if _has("gum"):
        cmd = ["gum", "input", "--placeholder", placeholder]
        if default:
            cmd += ["--value", default]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 130:
            raise Cancelled()
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "gum input failed")
        return proc.stdout.strip()
    # Python fallback.
    try:
        prompt = f"{placeholder}: " if placeholder else "> "
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise Cancelled() from None


def confirm(prompt: str) -> bool:
    """Ask for confirmation via ``gum confirm``, falling back to a y/n prompt.

    Parameters
    ----------
    prompt : str
        Confirmation question.

    Returns
    -------
    bool
        Whether the user confirmed.

    Raises
    ------
    Cancelled
        If the user aborts the fallback prompt.
    """
    if _has("gum"):
        proc = subprocess.run(["gum", "confirm", prompt])
        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False
        raise Cancelled()
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise Cancelled() from None
    return answer in ("y", "yes")
