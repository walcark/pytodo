from pytodo import migrate, store
from pytodo.store import done_dir, todos_dir
from pytodo.todo import TodoState, load_todo

OLD_TODO = """\
---
title: "Renew passport"
category: admin
urgency: soon
horizon: month
created: 2026-07-05T14:32:01
completed: null
---

Body kept as-is.
"""

OLD_SOMEDAY = """\
---
title: "Learn Rust"
category: perso
urgency: someday
horizon: null
created: 2026-07-05T14:32:01
---
"""

OLD_DONE = """\
---
title: "Pay bill"
category: admin
urgency: now
horizon: today
created: 2026-07-01T09:00:00
completed: 2026-07-02T10:00:00
---
"""

OLD_CONFIG = """\
[categories]
values = ["work", "home", "perso", "admin"]

[urgency]
values = ["now", "soon", "someday"]
colors = ["bold red", "yellow", "grey62"]

[horizon]
values = ["today", "week", "month"]

[sync]
auto = false
"""


def _write(directory, name, text):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_migrates_todo_fields(tmp_path):
    path = _write(todos_dir(tmp_path), "20260705-143201-a3f2.md", OLD_TODO)
    result = migrate.migrate_repo(tmp_path)

    assert path.stem in result.migrated
    todo = load_todo(path)
    assert todo.state is TodoState.NEXT  # non-someday active -> next
    assert todo.area == "admin"  # category -> area
    assert todo.context is None  # left for review to flag
    assert todo.body == "Body kept as-is."
    assert todo.created is not None
    # old keys are gone from disk
    assert "urgency" not in path.read_text()
    assert "horizon" not in path.read_text()
    assert "category" not in path.read_text()


def test_someday_urgency_becomes_someday_state(tmp_path):
    path = _write(todos_dir(tmp_path), "20260705-143201-bbbb.md", OLD_SOMEDAY)
    migrate.migrate_repo(tmp_path)
    assert load_todo(path).state is TodoState.SOMEDAY


def test_archived_becomes_done(tmp_path):
    path = _write(done_dir(tmp_path), "20260701-090000-cccc.md", OLD_DONE)
    migrate.migrate_repo(tmp_path)
    todo = load_todo(path)
    assert todo.state is TodoState.DONE
    assert todo.completed is not None


def test_config_categories_become_areas(tmp_path):
    (tmp_path / "config.toml").write_text(OLD_CONFIG, encoding="utf-8")
    result = migrate.migrate_repo(tmp_path)

    assert result.config_migrated
    from pytodo.vocabulary import load_repo_config

    cfg = load_repo_config(tmp_path)
    assert cfg.areas == ["work", "home", "perso", "admin"]
    assert cfg.sync_auto is False  # preserved
    assert cfg.contexts  # seeded with defaults
    text = (tmp_path / "config.toml").read_text()
    assert "urgency" not in text
    assert "horizon" not in text


def test_is_idempotent(tmp_path):
    _write(todos_dir(tmp_path), "20260705-143201-a3f2.md", OLD_TODO)
    (tmp_path / "config.toml").write_text(OLD_CONFIG, encoding="utf-8")

    first = migrate.migrate_repo(tmp_path)
    assert first.changed
    assert migrate.count_pending(tmp_path) == 0

    second = migrate.migrate_repo(tmp_path)
    assert not second.changed
    assert second.migrated == []
    assert second.skipped == 1


def test_leaves_new_format_untouched(tmp_path):
    # A repo already on the new model has nothing pending.
    store.create_todo(tmp_path, title="Fresh", state=TodoState.NEXT, context="@home")
    assert migrate.count_pending(tmp_path) == 0
    result = migrate.migrate_repo(tmp_path)
    assert not result.changed
    assert result.skipped == 1
