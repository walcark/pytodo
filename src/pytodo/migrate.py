"""One-shot migration of a data repo from the pre-GTD format.

Old todos carried ``category`` / ``urgency`` / ``horizon``; the model now uses
``state`` / ``context`` / ``area`` / ``project`` (see ``docs/model.md``). This
rewrites each file in place following the migration table, and is idempotent: a
file already in the new shape is left untouched.

It reads the *raw* front matter rather than going through
:func:`pytodo.todo.parse_markdown`, which already drops the old keys silently,
so the mapping would otherwise be lost.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .store import done_dir, todos_dir
from .todo import Todo, TodoState, _coerce_datetime
from .vocabulary import (
    DEFAULT_CONTEXTS,
    DEFAULT_WAITING_STALE_DAYS,
    REPO_CONFIG_NAME,
    RepoConfig,
    save_repo_config,
)

_OLD_KEYS = frozenset({"category", "urgency", "horizon"})


@dataclass
class MigrationResult:
    """Outcome of :func:`migrate_repo`.

    Attributes
    ----------
    migrated : list of str
        Ids of the todo files that were rewritten.
    skipped : int
        Files already in the new shape, left untouched.
    config_migrated : bool
        Whether ``config.toml`` was rewritten.
    warnings : list of str
        Non-fatal issues (an unreadable file is skipped, not fatal).
    """

    migrated: list[str] = field(default_factory=list)
    skipped: int = 0
    config_migrated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Return whether the migration wrote anything at all."""
        return bool(self.migrated) or self.config_migrated


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return ``(front_matter, body)`` from a markdown file.

    Raises
    ------
    ValueError
        If the front matter is missing or unterminated.
    """
    if not text.startswith("---"):
        raise ValueError("missing front matter")
    parts = text.split("\n")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("unterminated front matter")
    fm = yaml.safe_load("\n".join(parts[1:end])) or {}
    body = "\n".join(parts[end + 1 :]).strip("\n")
    return fm, body


def _needs_migration(fm: dict) -> bool:
    """Return whether a front matter still carries the old shape."""
    return bool(_OLD_KEYS & fm.keys()) or "state" not in fm


def _migrated_todo(fm: dict, body: str, *, todo_id: str, archived: bool) -> Todo:
    """Build the new-shape :class:`Todo` from an old front matter.

    Mapping (see ``docs/model.md``): ``category`` becomes ``area``; a completed
    or archived item becomes ``done``; ``urgency: someday`` becomes the
    ``someday`` state, anything else ``next`` (existing todos were already
    clarified under the old model, so calling them ``next`` is truthful).
    ``horizon`` is dropped, and ``context`` stays empty for ``todo review`` to
    flag.
    """
    completed = _coerce_datetime(fm.get("completed"))
    if archived or completed is not None:
        state = TodoState.DONE
    elif str(fm.get("urgency", "")).lower() == "someday":
        state = TodoState.SOMEDAY
    else:
        state = TodoState.NEXT

    return Todo(
        id=todo_id,
        title=str(fm.get("title", "")).strip() or todo_id,
        state=state,
        context=None,
        area=(fm.get("category") or None),
        created=_coerce_datetime(fm.get("created")),
        completed=completed,
        body=body,
    )


def _migrate_dir(directory: Path, *, archived: bool, result: MigrationResult) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.md")):
        try:
            fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            result.warnings.append(f"skipped {path.name}: {exc}")
            continue
        if not _needs_migration(fm):
            result.skipped += 1
            continue
        todo = _migrated_todo(fm, body, todo_id=path.stem, archived=archived)
        path.write_text(todo.to_markdown(), encoding="utf-8")
        result.migrated.append(todo.id)


def _migrate_config(data_dir: Path, result: MigrationResult) -> None:
    """Rewrite ``config.toml`` from the old vocabulary, if it is still old.

    The old ``[categories]`` become ``[areas]``; ``[urgency]`` and
    ``[horizon]`` are dropped and contexts seeded with the defaults. Read the
    old keys explicitly: :func:`load_repo_config` would silently fall back to
    the default areas and lose the user's categories.
    """
    path = data_dir / REPO_CONFIG_NAME
    if not path.exists():
        return
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if "categories" not in data and "urgency" not in data and "horizon" not in data:
        return  # already new (or has no old sections to carry over)

    areas = data.get("categories", {}).get("values") or list(RepoConfig().areas)
    cfg = RepoConfig(
        areas=areas,
        contexts=list(DEFAULT_CONTEXTS),
        waiting_stale_days=data.get("review", {}).get(
            "waiting_stale_days", DEFAULT_WAITING_STALE_DAYS
        ),
        sync_auto=data.get("sync", {}).get("auto", True),
    )
    save_repo_config(data_dir, cfg)
    result.config_migrated = True


def count_pending(data_dir: Path) -> int:
    """Return how many files (todos, archive, config) still need migrating.

    Used to decide whether the migration has anything to do and to size the
    confirmation, without writing anything.
    """
    n = 0
    for directory in (todos_dir(data_dir), done_dir(data_dir)):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue  # unreadable: migrate_repo will record the warning
            if _needs_migration(fm):
                n += 1

    config = data_dir / REPO_CONFIG_NAME
    if config.exists():
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        if any(k in data for k in ("categories", "urgency", "horizon")):
            n += 1
    return n


def migrate_repo(data_dir: Path) -> MigrationResult:
    """Migrate every todo, archived todo and the config of a data repo.

    Parameters
    ----------
    data_dir : pathlib.Path
        Data repo root.

    Returns
    -------
    MigrationResult
        What was migrated, skipped, and any per-file warning. Idempotent:
        running it twice leaves everything in ``skipped`` the second time.
    """
    result = MigrationResult()
    _migrate_dir(todos_dir(data_dir), archived=False, result=result)
    _migrate_dir(done_dir(data_dir), archived=True, result=result)
    _migrate_config(data_dir, result)
    return result
