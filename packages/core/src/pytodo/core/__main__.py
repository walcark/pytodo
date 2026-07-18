"""Enable ``python -m pytodo.core _flush <data_dir>`` for the detached sync.

Only the background sync worker respawns the interpreter this way (see
:func:`pytodo.core.vcs.spawn_background_flush`). It lives in core, not in an
application layer, so the worker never depends on the CLI or the server.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import vcs


def main(argv: list[str] | None = None) -> None:
    """Run the ``_flush <data_dir>`` subcommand; ignore anything else."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "_flush":
        try:
            vcs.background_flush(Path(args[1]))
        except Exception:
            pass  # detached process: never crash loudly


if __name__ == "__main__":
    main()
