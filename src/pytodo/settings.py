"""Machine-local settings, not versioned: where the data repo lives.

This is the *only* per-machine state. Everything else that configures todo is
versioned inside the data repo and shared across devices (see
:mod:`pytodo.vocabulary`). Keeping the two apart is what makes the vocabulary a
domain concern rather than a config file.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def local_config_path() -> Path:
    """Return the path of the local (non-versioned) config file."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "todo" / "config.toml"


def read_data_dir() -> Path | None:
    """Return the active data repo path.

    Returns
    -------
    pathlib.Path or None
        The configured ``data_dir``, or ``None`` if not configured yet.
    """
    path = local_config_path()
    if not path.exists():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("data_dir")
    if not raw:
        return None
    return Path(raw).expanduser()


def write_data_dir(data_dir: Path) -> Path:
    """Persist the active data repo path in the local config.

    Parameters
    ----------
    data_dir : pathlib.Path
        Absolute path of the data repo to make active.

    Returns
    -------
    pathlib.Path
        The path of the config file that was written.
    """
    path = local_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Store the resolved absolute path to avoid any ambiguity.
    path.write_text(f'data_dir = "{data_dir}"\n', encoding="utf-8")
    return path
