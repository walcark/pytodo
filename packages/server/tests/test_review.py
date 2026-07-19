import subprocess
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from neverland.core import store
from neverland.core.todo import TodoState
from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def test_review_reports_each_problem(client, tmp_path):
    # inbox item
    store.create_todo(tmp_path, title="Unclarified")
    # a next action without a context (unselectable)
    store.create_todo(tmp_path, title="No context", state=TodoState.NEXT)
    # a project with no next action -> stalled
    store.create_project(tmp_path, title="Passport")
    # a waiting item older than the stale threshold (default 7 days)
    old = datetime.now() - timedelta(days=30)
    store.create_todo(tmp_path, title="Waiting long", state=TodoState.WAITING, now=old)

    review = client.get("/api/review").json()
    assert [t["title"] for t in review["inbox"]] == ["Unclarified"]
    assert [p["title"] for p in review["stalled_projects"]] == ["Passport"]
    assert [t["title"] for t in review["contextless_next"]] == ["No context"]
    assert [t["title"] for t in review["stale_waiting"]] == ["Waiting long"]
    assert review["waiting_stale_days"] == 7


def test_review_is_clean_when_nothing_rots(client, tmp_path):
    # a next action with a context is not a problem
    store.create_todo(
        tmp_path, title="Ready", state=TodoState.NEXT, context="@computer"
    )
    review = client.get("/api/review").json()
    assert review["inbox"] == []
    assert review["stalled_projects"] == []
    assert review["contextless_next"] == []
    assert review["stale_waiting"] == []
