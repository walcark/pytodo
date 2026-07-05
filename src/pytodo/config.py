"""Two levels of configuration.

- *Local* config (not versioned): ``~/.config/todo/config.toml``. Stores the
  path of the active data repo (``data_dir``).
- *Data repo* config (versioned): ``<data_dir>/config.toml``. Categories,
  urgencies, horizons and the sync toggle, shared across devices.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TODOS_DIRNAME = "todos"
DONE_DIRNAME = "done"
REPO_CONFIG_NAME = "config.toml"

DEFAULT_CATEGORIES = ["work", "home", "perso", "admin"]
DEFAULT_URGENCY = ["now", "soon", "someday"]
DEFAULT_HORIZON = ["today", "week", "month"]


# --------------------------------------------------------------------------- #
# Local config                                                                #
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Data repo config                                                            #
# --------------------------------------------------------------------------- #

@dataclass
class RepoConfig:
    """Configuration shared across devices, versioned in the data repo.

    Attributes
    ----------
    categories : list of str
        Allowed categories (fixed, finite set).
    urgency : list of str
        Allowed urgency values.
    horizon : list of str
        Allowed horizon values.
    sync_auto : bool
        When ``True``, mutations trigger a background pull/push
        (``option 1``: instant local commit, best-effort network).
    """

    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    urgency: list[str] = field(default_factory=lambda: list(DEFAULT_URGENCY))
    horizon: list[str] = field(default_factory=lambda: list(DEFAULT_HORIZON))
    sync_auto: bool = True

    def to_toml(self) -> str:
        """Serialize the config to a TOML string."""
        def arr(values: list[str]) -> str:
            return "[" + ", ".join(f'"{v}"' for v in values) + "]"

        return (
            "[categories]\n"
            f"values = {arr(self.categories)}\n\n"
            "[urgency]\n"
            f"values = {arr(self.urgency)}\n\n"
            "[horizon]\n"
            f"values = {arr(self.horizon)}\n\n"
            "[sync]\n"
            f"auto = {str(self.sync_auto).lower()}\n"
        )


def default_repo_config_toml() -> str:
    """Return the default data repo config as a TOML string."""
    return RepoConfig().to_toml()


def load_repo_config(data_dir: Path) -> RepoConfig:
    """Load the data repo config, falling back to defaults when missing.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.

    Returns
    -------
    RepoConfig
        The parsed config, or a default one if ``config.toml`` is absent.
    """
    path = data_dir / REPO_CONFIG_NAME
    if not path.exists():
        return RepoConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return RepoConfig(
        categories=data.get("categories", {}).get("values", list(DEFAULT_CATEGORIES)),
        urgency=data.get("urgency", {}).get("values", list(DEFAULT_URGENCY)),
        horizon=data.get("horizon", {}).get("values", list(DEFAULT_HORIZON)),
        sync_auto=data.get("sync", {}).get("auto", True),
    )
