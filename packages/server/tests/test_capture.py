import subprocess

import pytest
from fastapi.testclient import TestClient

from neverland.core import store
from neverland.core.todo import TodoState
from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    """A TestClient over a real git repo (capture commits, so git is required)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def test_capture_lands_in_inbox(client, tmp_path):
    resp = client.post("/api/capture", json={"title": "Buy milk"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Buy milk"
    assert body["state"] == "inbox"

    # visible through the read API...
    inbox = client.get("/api/todos", params={"view": "inbox"}).json()
    assert [t["title"] for t in inbox] == ["Buy milk"]
    # ...and committed to disk.
    assert store.list_by_state(tmp_path, TodoState.INBOX)[0].title == "Buy milk"


def test_capture_trims_and_rejects_blank(client):
    assert client.post("/api/capture", json={"title": "   "}).status_code == 400

    resp = client.post("/api/capture", json={"title": "  Padded  "})
    assert resp.status_code == 201
    assert resp.json()["title"] == "Padded"


def test_capture_makes_a_git_commit(client, tmp_path):
    client.post("/api/capture", json={"title": "Track me"})
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "add: Track me" in log.stdout
