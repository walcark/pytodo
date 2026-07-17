from datetime import datetime

from pytodo import store
from pytodo.config import DONE_DIRNAME, TODOS_DIRNAME
from pytodo.todo import load_todo


def test_new_todo_id_format():
    tid = store.new_todo_id(datetime(2026, 7, 5, 16, 40, 9))
    assert tid.startswith("20260705-164009-")
    assert len(tid) == len("20260705-164009-abcd")


def test_create_and_list(tmp_path):
    todo = store.create_todo(
        tmp_path,
        title="Pay bill",
        category="admin",
        urgency="now",
        horizon="today",
    )
    assert todo.path.exists()
    assert todo.path.parent.name == TODOS_DIRNAME

    active = store.list_active(tmp_path)
    assert len(active) == 1
    assert active[0].title == "Pay bill"
    assert active[0].horizon == "today"


def test_move_to_done(tmp_path):
    todo = store.create_todo(tmp_path, title="Tidy up", category="home")
    old_path = todo.path
    dest = store.move_to_done(todo, tmp_path, now=datetime(2026, 7, 5, 9, 0, 0))

    assert not old_path.exists()
    assert dest.exists()
    assert dest.parent.name == DONE_DIRNAME
    # same id preserved
    assert dest.stem == old_path.stem
    # completed stamped and read back from disk
    reloaded = load_todo(dest)
    assert reloaded.completed == datetime(2026, 7, 5, 9, 0, 0)
    assert store.list_active(tmp_path) == []
    assert len(store.list_done(tmp_path)) == 1


def test_delete(tmp_path):
    todo = store.create_todo(tmp_path, title="Ephemeral", category="perso")
    path = todo.path
    store.delete_todo(todo)
    assert not path.exists()
    assert store.list_active(tmp_path) == []
