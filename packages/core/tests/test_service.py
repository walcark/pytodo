from datetime import date

import pytest

from pytodo.core import service, store, vcs
from pytodo.core.plan import PlanEntry, PlanStatus
from pytodo.core.store import done_dir, todos_dir
from pytodo.core.todo import TodoState
from pytodo.core.vocabulary import RepoConfig, load_repo_config


@pytest.fixture
def no_sync(monkeypatch):
    """Stub the git layer so service tests exercise logic, not the network.

    ``service.auto_sync`` calls ``vcs.sync`` (a real commit) then schedules a
    background flush. The use cases only need those to be called; the git
    behaviour has its own tests in ``test_vcs``.
    """
    calls: list[str] = []

    def fake_sync(data_dir, *, message=None, **kwargs):
        calls.append(message or "")
        return vcs.SyncResult(committed=True)

    monkeypatch.setattr(service.vcs, "sync", fake_sync)
    monkeypatch.setattr(service.vcs, "spawn_background_flush", lambda data_dir: None)
    return calls


def test_capture_lands_in_inbox(tmp_path, no_sync):
    cfg = RepoConfig()
    todo, sync = service.capture(tmp_path, cfg, "Buy milk")

    assert todo.state is TodoState.INBOX
    assert todo.path is not None and todo.path.parent == todos_dir(tmp_path)
    assert sync.committed
    assert no_sync == ["add: Buy milk"]


def test_complete_archives_and_reflects_today(tmp_path, no_sync):
    cfg = RepoConfig()
    todo = store.create_todo(tmp_path, title="Pay bill", state=TodoState.NEXT)

    plan = store.load_day_plan(tmp_path, date.today())
    plan.entries.append(PlanEntry(todo_id=todo.id, title=todo.title))
    store.save_day_plan(tmp_path, plan)

    service.complete(tmp_path, cfg, [todo])

    assert not list(todos_dir(tmp_path).glob("*.md"))
    assert list(done_dir(tmp_path).glob("*.md"))
    reloaded = store.load_day_plan(tmp_path, date.today())
    assert reloaded.find(todo.id).status is PlanStatus.DONE


def test_complete_without_today_plan_is_fine(tmp_path, no_sync):
    cfg = RepoConfig()
    todo = store.create_todo(tmp_path, title="No plan today", state=TodoState.NEXT)

    service.complete(tmp_path, cfg, [todo])

    assert list(done_dir(tmp_path).glob("*.md"))


def test_delete_removes_the_file(tmp_path, no_sync):
    cfg = RepoConfig()
    todo = store.create_todo(tmp_path, title="Scratch that")

    service.delete(tmp_path, cfg, [todo])

    assert not list(todos_dir(tmp_path).glob("*.md"))


def test_set_vocabulary_adds_and_persists(tmp_path, no_sync):
    cfg = RepoConfig()
    service.set_vocabulary(tmp_path, cfg, "areas", "add", "health")

    assert "health" in load_repo_config(tmp_path).areas


def test_set_vocabulary_add_duplicate_raises(tmp_path, no_sync):
    cfg = RepoConfig(areas=["work"])
    with pytest.raises(service.DuplicateValue):
        service.set_vocabulary(tmp_path, cfg, "areas", "add", "work")


def test_set_vocabulary_rm_unknown_raises(tmp_path, no_sync):
    cfg = RepoConfig(areas=["work"])
    with pytest.raises(service.UnknownValue):
        service.set_vocabulary(tmp_path, cfg, "areas", "rm", "ghost")


def test_set_vocabulary_rm_in_use_lists_the_users(tmp_path, no_sync):
    cfg = RepoConfig(areas=["work", "home"])
    store.create_todo(tmp_path, title="Fix sink", state=TodoState.NEXT, area="home")

    with pytest.raises(service.ValueInUse) as excinfo:
        service.set_vocabulary(tmp_path, cfg, "areas", "rm", "home")

    assert [t.title for t in excinfo.value.users] == ["Fix sink"]
    assert "home" in load_repo_config(tmp_path).areas  # nothing saved


def test_set_vocabulary_rm_unused_persists(tmp_path, no_sync):
    cfg = RepoConfig(areas=["work", "home"])
    service.set_vocabulary(tmp_path, cfg, "areas", "rm", "home")

    assert "home" not in load_repo_config(tmp_path).areas
