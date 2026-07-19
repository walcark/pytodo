import subprocess

import pytest
from fastapi.testclient import TestClient

from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    config = ServerConfig(data_dir=tmp_path, poll_interval=0)
    return TestClient(create_app(config))


def _capture(client, title="Action"):
    return client.post("/api/capture", json={"title": title}).json()["id"]


def _create_project(client, title="Renew passport", **extra):
    return client.post("/api/projects", json={"title": title, **extra}).json()["id"]


def test_create_project_starts_stalled(client):
    pid = _create_project(client, outcome="Valid passport in hand", area="admin")
    projects = client.get("/api/projects").json()
    summary = next(p for p in projects if p["id"] == pid)
    assert summary["title"] == "Renew passport"
    assert summary["outcome"] == "Valid passport in hand"
    assert (summary["action_count"], summary["next_count"]) == (0, 0)
    assert summary["stalled"] is True


def test_create_rejects_blank_and_unknown_area(client):
    assert client.post("/api/projects", json={"title": "  "}).status_code == 400
    assert (
        client.post("/api/projects", json={"title": "X", "area": "nope"}).status_code
        == 400
    )


def test_assigning_a_next_action_unstalls_the_project(client):
    pid = _create_project(client)
    todo_id = _capture(client, "Book appointment")
    resp = client.patch(
        f"/api/todos/{todo_id}",
        json={"state": "next", "context": "@phone", "project": pid},
    )
    assert resp.status_code == 200

    summary = next(p for p in client.get("/api/projects").json() if p["id"] == pid)
    assert (summary["action_count"], summary["next_count"]) == (1, 1)
    assert summary["stalled"] is False

    todos = client.get(f"/api/projects/{pid}/todos").json()
    assert [t["title"] for t in todos] == ["Book appointment"]


def test_patch_unknown_project_is_400(client):
    todo_id = _capture(client)
    assert (
        client.patch(f"/api/todos/{todo_id}", json={"project": "nope"}).status_code
        == 400
    )


def test_project_todos_unknown_is_404(client):
    assert client.get("/api/projects/nope/todos").status_code == 404


def test_capture_into_project_lands_in_inbox_prelinked(client):
    pid = _create_project(client)
    resp = client.post(f"/api/projects/{pid}/todos", json={"title": "Photos"})
    assert resp.status_code == 201
    body = resp.json()
    assert (body["state"], body["project"]) == ("inbox", pid)

    # it counts as an action, but leaves the project stalled (no next action yet)
    summary = next(p for p in client.get("/api/projects").json() if p["id"] == pid)
    assert (summary["action_count"], summary["next_count"]) == (1, 0)
    assert summary["stalled"] is True


def test_capture_into_project_validation(client):
    pid = _create_project(client)
    assert (
        client.post(f"/api/projects/{pid}/todos", json={"title": " "}).status_code
        == 400
    )
    assert (
        client.post("/api/projects/nope/todos", json={"title": "X"}).status_code == 404
    )


def test_create_project_makes_a_git_commit(client, tmp_path):
    _create_project(client, title="Tracked project")
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "project: add Tracked project" in log.stdout
