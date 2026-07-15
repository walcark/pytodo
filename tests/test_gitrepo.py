from pytodo import gitrepo, storage
from pytodo.config import DONE_DIRNAME, REPO_CONFIG_NAME, TODOS_DIRNAME


def test_setup_new_repo_scaffolds(tmp_path):
    target = tmp_path / "data"
    result = gitrepo.setup_repo(str(target))
    assert result.created_repo is True
    assert gitrepo.is_git_repo(target)
    assert gitrepo.is_todo_repo(target)
    assert (target / REPO_CONFIG_NAME).exists()
    assert (target / TODOS_DIRNAME).is_dir()
    assert (target / DONE_DIRNAME).is_dir()


def test_missing_layout_detection(tmp_path):
    assert set(gitrepo.missing_layout(tmp_path)) == {
        REPO_CONFIG_NAME,
        f"{TODOS_DIRNAME}/",
        f"{DONE_DIRNAME}/",
    }


def test_setup_adopts_existing_valid_repo(tmp_path):
    target = tmp_path / "data"
    gitrepo.setup_repo(str(target))  # first time: scaffold
    result = gitrepo.setup_repo(str(target))  # second time: adoption
    assert result.adopted is True
    assert result.created_items == []


def test_setup_confirm_declined_on_unrelated_content(tmp_path):
    target = tmp_path / "data"
    target.mkdir()
    (target / "other.txt").write_text("unrelated content", encoding="utf-8")
    try:
        gitrepo.setup_repo(str(target), confirm=lambda _: False)
        raise AssertionError("should have raised RepoError")
    except gitrepo.RepoError:
        pass


def test_sync_commits_without_origin(tmp_path):
    target = tmp_path / "data"
    gitrepo.setup_repo(str(target))
    storage.create_todo(target, title="Task", category="work")
    result = gitrepo.sync(target)
    assert result.committed is True
    assert result.pushed is False
    assert result.warnings == []  # no origin -> no network warning


def test_sync_pushes_to_origin(tmp_path):
    origin = tmp_path / "origin.git"
    gitrepo.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    gitrepo.setup_repo(str(target))
    gitrepo.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    storage.create_todo(target, title="Task", category="work")
    result = gitrepo.sync(target)
    assert result.committed is True
    assert result.pushed is True

    files = gitrepo.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert any(
        line.startswith("todos/") and line.endswith(".md")
        for line in files.splitlines()
    )


def test_background_flush_drains_all_commits(tmp_path):
    origin = tmp_path / "origin.git"
    gitrepo.run_git(["init", "--bare", str(origin)])
    target = tmp_path / "data"
    gitrepo.setup_repo(str(target))
    gitrepo.run_git(["remote", "add", "origin", str(origin)], cwd=target)

    # Several unpushed local commits (as after quick successive `add`s).
    for i in range(3):
        storage.create_todo(target, title=f"Task {i}", category="work")
        gitrepo.sync(target, network=False)  # local commit only

    assert gitrepo._unpushed_count(target) == 0  # no upstream yet -> 0

    gitrepo.background_flush(target)

    # Everything is pushed, nothing left pending.
    assert gitrepo._unpushed_count(target) == 0
    files = gitrepo.run_git(["ls-tree", "-r", "--name-only", "HEAD"], cwd=origin).stdout
    assert files.count(".md") >= 3


def test_sync_lock_is_exclusive(tmp_path):
    target = tmp_path / "data"
    gitrepo.setup_repo(str(target))
    with gitrepo.sync_lock(target) as first:
        assert first is True
        with gitrepo.sync_lock(target) as second:
            assert second is False  # already held -> non-blocking yields False
    # Once released, it can be re-acquired.
    with gitrepo.sync_lock(target) as again:
        assert again is True
