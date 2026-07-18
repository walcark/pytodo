"""Deployment helpers: env-file and systemd user unit generation.

These back the ``neverland-server setup`` and ``install`` commands. They only
render and write files (plus, optionally, call ``systemctl --user``); keeping
the rendering pure makes it testable without touching the real systemd.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

UNIT_NAME = "neverland-server.service"


def systemd_user_dir() -> Path:
    """Return the systemd *user* unit directory (``$XDG_CONFIG_HOME/systemd/user``)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "systemd" / "user"


def executable() -> str:
    """Return the command that starts the server, for a unit's ``ExecStart``.

    Prefers the installed ``neverland-server`` console script; falls back to
    ``<python> -m neverland.server.cli`` when it is not on ``PATH`` (e.g. inside a
    pixi environment), so the unit works either way.
    """
    found = shutil.which("neverland-server")
    if found:
        return found
    return f"{sys.executable} -m neverland.server.cli"


def write_env_file(path: Path, values: dict[str, str]) -> None:
    """Write ``values`` as a ``KEY=VALUE`` env file with owner-only permissions.

    The file holds the token, so it is created ``0600`` (before any content is
    written) and never widened.

    Parameters
    ----------
    path : pathlib.Path
        Destination file; parent directories are created as needed.
    values : dict of str to str
        Key/value pairs to serialise, one per line, in insertion order.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={val}\n" for key, val in values.items())
    # Open with 0600 up front so the token is never briefly world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(body)
    path.chmod(0o600)


def render_unit(config_path: Path, exec_start: str) -> str:
    """Render the systemd user unit for the server.

    Parameters
    ----------
    config_path : pathlib.Path
        Env file the unit loads via ``EnvironmentFile=``.
    exec_start : str
        Command that runs the server (see :func:`executable`).

    Returns
    -------
    str
        The full unit file contents.
    """
    return f"""\
[Unit]
Description=neverland web server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile={config_path}
ExecStart={exec_start} run
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


def write_unit(config_path: Path, unit_dir: Path | None = None) -> Path:
    """Render and install the systemd user unit; return its path.

    Parameters
    ----------
    config_path : pathlib.Path
        Env file the unit references.
    unit_dir : pathlib.Path, optional
        Target directory. Defaults to :func:`systemd_user_dir`.

    Returns
    -------
    pathlib.Path
        The written unit file.
    """
    directory = unit_dir or systemd_user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    unit_path = directory / UNIT_NAME
    unit_path.write_text(render_unit(config_path, executable()))
    return unit_path
