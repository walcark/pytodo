from pytodo.core import store, vcs
from pytodo.core.store import DONE_DIRNAME, TODOS_DIRNAME
from pytodo.core.vocabulary import REPO_CONFIG_NAME


def test_setup_new_repo_scaffolds(tmp_path):
    target = tmp_path / "data"
    result = vcs.setup_repo(str(target))
    assert result.created_repo is True
    assert vcs.is_git_repo(target)
    assert vcs.is_todo_repo(target)
    assert (target / REPO_CONFIG_NAME).exists()
    assert (target / TODOS_DIRNAME).is_dir()
    assert (target / DONE_DIRNAME).is_dir()


def test_missing_layout_detection(tmp_path):
    assert set(vcs.missing_layout(tmp_path)) == {
        REPO_CONFIG_NAME,
        f"{TODOS_DIRNAME}/",
        f"{DONE_DIRNAME}/",
    }


def test_setup_adopts_existing_valid_repo(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))  # first time: scaffold
    result = vcs.setup_repo(str(target))  # second time: adoption
    assert result.adopted is True
    assert result.created_items == []


def test_setup_confirm_declined_on_unrelated_content(tmp_path):
    target = tmp_path / "data"
    target.mkdir()
    (target / "other.txt").write_text("unrelated content", encoding="utf-8")
    try:
        vcs.setup_repo(str(target), confirm=lambda _: False)
        raise AssertionError("should have raised RepoError")
    except vcs.RepoError:
        pass


def test_sync_commits_without_origin(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    store.create_todo(target, title="Task")
    result = vcs.sync(target)
    assert result.committed is True
    assert result.pushed is False
    assert result.warnings == []  # no origin -> no network warning


def test_sync_pushes_to_origin(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    store.create_todo(target, title="Task")
    result = vcs.sync(target)
    assert result.committed is True
    assert result.pushed is True

    files = vcs.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert any(
        line.startswith("todos/") and line.endswith(".md")
        for line in files.splitlines()
    )


def test_background_flush_drains_all_commits(tmp_path):
    origin = tmp_path / "origin.git"
    vcs.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    vcs.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    # Several unpushed local commits (as after quick successive `add`s).
    for i in range(3):
        store.create_todo(target, title=f"Task {i}")
        vcs.sync(target, network=False)  # local commit only

    assert vcs._unpushed_count(target) == 0  # no upstream yet -> 0

    vcs.background_flush(target)

    # Everything is pushed, nothing left pending.
    assert vcs._unpushed_count(target) == 0
    files = vcs.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert files.count(".md") >= 3


def test_sync_lock_is_exclusive(tmp_path):
    target = tmp_path / "data"
    vcs.setup_repo(str(target))
    with vcs.sync_lock(target) as first:
        assert first is True
        with vcs.sync_lock(target) as second:
            assert second is False  # already held -> non-blocking yields False
    # Once released, it can be re-acquired.
    with vcs.sync_lock(target) as again:
        assert again is True
