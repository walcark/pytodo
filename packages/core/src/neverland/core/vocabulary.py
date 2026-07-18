"""The finite sets of values a todo may carry, versioned in the data repo.

This is *domain*, not configuration: which areas and contexts exist defines
what a todo can mean, and the answer must be identical on every device, so it
lives in ``<data_dir>/config.toml`` and travels with the data. Where that data
directory sits is the only genuinely machine-local thing, and it lives in
:mod:`neverland.core.settings`.

Both sets are flat and unordered. Nothing ranks them: the ordered
``Scale``/``make_sort_key`` machinery existed only to serve ``urgency`` and
``horizon``, and went with them (see ``docs/model.md``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_CONFIG_NAME = "config.toml"

DEFAULT_AREAS = ["work", "home", "perso", "admin"]
DEFAULT_CONTEXTS = [
    "@computer",
    "@phone",
    "@errands",
    "@office",
    "@home",
    "@anywhere",
]
DEFAULT_WAITING_STALE_DAYS = 7


@dataclass
class RepoConfig:
    """Vocabulary and settings shared across devices, versioned in the data repo.

    Attributes
    ----------
    areas : list of str
        Allowed domains of responsibility ("which part of my life").
    contexts : list of str
        Allowed contexts ("what I need in order to act"). This is the axis you
        filter on when choosing what to do, so a context is only worth having
        if you are regularly in it.
    waiting_stale_days : int
        How long a ``waiting`` todo may sit before ``todo review`` tells you to
        chase it.
    sync_auto : bool
        When ``True``, mutations trigger a background pull/push (instant local
        commit, best-effort network).
    """

    areas: list[str] = field(default_factory=lambda: list(DEFAULT_AREAS))
    contexts: list[str] = field(default_factory=lambda: list(DEFAULT_CONTEXTS))
    waiting_stale_days: int = DEFAULT_WAITING_STALE_DAYS
    sync_auto: bool = True

    def to_toml(self) -> str:
        """Serialize the config to a TOML string.

        The whole file is regenerated rather than edited in place: ``tomllib``
        is read-only (there is no ``tomllib.dumps``). Any hand-written comment
        is therefore lost, which is accepted deliberately: todo owns this file,
        it is created by ``todo init`` and maintained through ``todo config``.
        That is what keeps a round-trip TOML dependency out of the package.
        """

        def arr(values: list[str]) -> str:
            return "[" + ", ".join(f'"{v}"' for v in values) + "]"

        lines = [
            "[areas]",
            f"values = {arr(self.areas)}",
            "",
            "[contexts]",
            f"values = {arr(self.contexts)}",
            "",
            "[review]",
            f"waiting_stale_days = {self.waiting_stale_days}",
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
        areas=data.get("areas", {}).get("values", list(DEFAULT_AREAS)),
        contexts=data.get("contexts", {}).get("values", list(DEFAULT_CONTEXTS)),
        waiting_stale_days=data.get("review", {}).get(
            "waiting_stale_days", DEFAULT_WAITING_STALE_DAYS
        ),
        sync_auto=data.get("sync", {}).get("auto", True),
    )


def save_repo_config(data_dir: Path, cfg: RepoConfig) -> Path:
    """Write the config back to the data repo.

    Editing the vocabulary is a *mutation*: this file is versioned and shared,
    so callers must commit and sync it like any other write, not treat it as a
    local preference.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.
    cfg : RepoConfig
        The config to persist.

    Returns
    -------
    pathlib.Path
        The path that was written.
    """
    path = data_dir / REPO_CONFIG_NAME
    path.write_text(cfg.to_toml(), encoding="utf-8")
    return path
