from datetime import datetime

from pytodo import store
from pytodo.store import DONE_DIRNAME, PROJECTS_DIRNAME, TODOS_DIRNAME
from pytodo.todo import TodoState, load_todo


def test_new_id_format():
    tid = store.new_id(datetime(2026, 7, 5, 16, 40, 9))
    assert tid.startswith("20260705-164009-")
    assert len(tid) == len("20260705-164009-abcd")


def test_capture_lands_in_inbox(tmp_path):
    # Capture asks nothing beyond the title, so everything else stays unset.
    todo = store.create_todo(tmp_path, title="Pay bill")

    assert todo.state is TodoState.INBOX
    assert todo.context is None
    assert todo.area is None
    assert todo.path.parent.name == TODOS_DIRNAME

    active = store.list_active(tmp_path)
    assert len(active) == 1
    assert active[0].title == "Pay bill"


def test_create_clarified_todo(tmp_path):
    todo = store.create_todo(
        tmp_path,
        title="Call the plumber",
        state=TodoState.NEXT,
        context="@phone",
        area="home",
    )
    reloaded = load_todo(todo.require_path())
    assert reloaded.state is TodoState.NEXT
    assert reloaded.context == "@phone"
    assert reloaded.area == "home"


def test_list_by_state(tmp_path):
    store.create_todo(tmp_path, title="Captured")
    store.create_todo(tmp_path, title="Actionable", state=TodoState.NEXT)
    store.create_todo(tmp_path, title="Later", state=TodoState.SOMEDAY)

    assert len(store.list_active(tmp_path)) == 3
    assert [t.title for t in store.list_by_state(tmp_path, TodoState.INBOX)] == [
        "Captured"
    ]
    assert [t.title for t in store.list_by_state(tmp_path, TodoState.NEXT)] == [
        "Actionable"
    ]


def test_save_todo_rewrites_in_place(tmp_path):
    # A state change must not move the file: only completion does.
    todo = store.create_todo(tmp_path, title="Clarify me")
    original = todo.require_path()

    todo.state = TodoState.NEXT
    todo.context = "@computer"
    store.save_todo(todo)

    assert todo.path == original
    reloaded = load_todo(original)
    assert reloaded.state is TodoState.NEXT
    assert reloaded.context == "@computer"


def test_move_to_done(tmp_path):
    todo = store.create_todo(tmp_path, title="Tidy up", state=TodoState.NEXT)
    old_path = todo.path
    dest = store.move_to_done(todo, tmp_path, now=datetime(2026, 7, 5, 9, 0, 0))

    assert not old_path.exists()
    assert dest.exists()
    assert dest.parent.name == DONE_DIRNAME
    assert dest.stem == old_path.stem  # same id preserved

    reloaded = load_todo(dest)
    assert reloaded.state is TodoState.DONE
    assert reloaded.completed == datetime(2026, 7, 5, 9, 0, 0)
    assert store.list_active(tmp_path) == []
    assert len(store.list_done(tmp_path)) == 1


def test_delete(tmp_path):
    todo = store.create_todo(tmp_path, title="Ephemeral")
    path = todo.path
    store.delete_todo(todo)
    assert not path.exists()
    assert store.list_active(tmp_path) == []


# -- Projects ---------------------------------------------------------------


def test_create_and_list_projects(tmp_path):
    project = store.create_project(
        tmp_path,
        title="Renew passport",
        outcome="Valid passport in hand",
        area="admin",
    )
    assert project.path.parent.name == PROJECTS_DIRNAME

    projects = store.list_projects(tmp_path)
    assert len(projects) == 1
    assert projects[0].outcome == "Valid passport in hand"
    assert projects[0].area == "admin"


def test_stalled_when_project_has_no_next_action(tmp_path):
    project = store.create_project(tmp_path, title="Renew passport")
    assert [p.id for p in store.stalled_projects(tmp_path)] == [project.id]


def test_not_stalled_once_a_next_action_exists(tmp_path):
    project = store.create_project(tmp_path, title="Renew passport")
    store.create_todo(
        tmp_path, title="Find the form", state=TodoState.NEXT, project=project.id
    )
    assert store.stalled_projects(tmp_path) == []


def test_stalled_again_when_the_only_action_is_not_next(tmp_path):
    # A project advanced only by a waiting or someday item is not moving: that
    # is exactly the rule the tool exists to enforce.
    project = store.create_project(tmp_path, title="Renew passport")
    store.create_todo(
        tmp_path, title="Ask Marc", state=TodoState.WAITING, project=project.id
    )
    assert [p.id for p in store.stalled_projects(tmp_path)] == [project.id]


def test_deleting_a_project_leaves_its_todos_standalone(tmp_path):
    # The reference points one way only, so nothing dangles.
    project = store.create_project(tmp_path, title="Renew passport")
    store.create_todo(
        tmp_path, title="Find the form", state=TodoState.NEXT, project=project.id
    )
    store.delete_project(project)

    assert store.list_projects(tmp_path) == []
    assert len(store.list_active(tmp_path)) == 1
