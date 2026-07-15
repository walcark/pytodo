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
DEFAULT_URGENCY_COLORS = ["bold red", "yellow", "grey62"]
DEFAULT_HORIZON = ["today", "week", "month"]


@dataclass(frozen=True)
class Scale:
    """An ordered, finite set of allowed values with optional display colors.

    A *scale* is the single source of truth for one axis of a todo (urgency or
    horizon). The order is meaningful: index 0 is the most urgent / nearest
    value and also defines the sort rank. ``colors`` maps a value to a rich
    style used by the renderer.

    Attributes
    ----------
    values : list of str
        Allowed values, ordered from most to least urgent (or nearest to
        farthest).
    colors : dict of str to str
        Per-value rich style, empty when the axis is not colored.
    """

    values: list[str]
    colors: dict[str, str] = field(default_factory=dict)

    def style(self, value: str) -> str:
        """Return the rich style for ``value`` (empty string when unset)."""
        return self.colors.get(value, "")


def _default_urgency() -> Scale:
    colors = dict(zip(DEFAULT_URGENCY, DEFAULT_URGENCY_COLORS, strict=True))
    return Scale(list(DEFAULT_URGENCY), colors)


def _default_horizon() -> Scale:
    return Scale(list(DEFAULT_HORIZON))


def _parse_scale(
    section: dict, default_values: list[str], default_colors: list[str] | None
) -> Scale:
    """Build a :class:`Scale` from a ``config.toml`` section.

    ``values`` fall back to ``default_values``; ``colors`` (parallel to
    ``values``) fall back to ``default_colors`` and are zipped into a mapping.
    A shorter/longer ``colors`` list is tolerated (extra values are uncolored).
    """
    values = section.get("values", list(default_values))
    colors_list = section.get("colors", default_colors)
    colors = dict(zip(values, colors_list, strict=False)) if colors_list else {}
    return Scale(values, colors)


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
    urgency : Scale
        Allowed urgency values, ordered and colored.
    horizon : Scale
        Allowed horizon values, ordered.
    sync_auto : bool
        When ``True``, mutations trigger a background pull/push
        (``option 1``: instant local commit, best-effort network).
    """

    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    urgency: Scale = field(default_factory=_default_urgency)
    horizon: Scale = field(default_factory=_default_horizon)
    sync_auto: bool = True

    def to_toml(self) -> str:
        """Serialize the config to a TOML string."""

        def arr(values: list[str]) -> str:
            return "[" + ", ".join(f'"{v}"' for v in values) + "]"

        def section(name: str, scale: Scale) -> list[str]:
            lines = [f"[{name}]", f"values = {arr(scale.values)}"]
            if scale.colors:
                ordered = [scale.colors.get(v, "") for v in scale.values]
                lines.append(f"colors = {arr(ordered)}")
            return lines

        lines = [
            "[categories]",
            f"values = {arr(self.categories)}",
            "",
            *section("urgency", self.urgency),
            "",
            *section("horizon", self.horizon),
            "",
            "[sync]",
            f"auto = {str(self.sync_auto).lower()}",
            "",
        ]
        return "\n".join(lines)


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
        urgency=_parse_scale(
            data.get("urgency", {}), DEFAULT_URGENCY, DEFAULT_URGENCY_COLORS
        ),
        horizon=_parse_scale(data.get("horizon", {}), DEFAULT_HORIZON, None),
        sync_auto=data.get("sync", {}).get("auto", True),
    )
