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


def test_complete_project_leaves_its_actions_alone(client):
    pid = _create_project(client)
    todo_id = client.post(f"/api/projects/{pid}/todos", json={"title": "Book slot"})
    todo_id = todo_id.json()["id"]

    resp = client.post(f"/api/projects/{pid}/complete")
    assert resp.status_code == 200
    assert resp.json()["state"] == "done"
    assert resp.json()["completed"] is not None

    # gone from the default list, still reachable with include_done
    assert [p["id"] for p in client.get("/api/projects").json()] == []
    done = client.get("/api/projects?include_done=true").json()
    assert [p["id"] for p in done] == [pid]
    # a finished outcome is not stalled, it is over
    assert done[0]["stalled"] is False

    # the action survives untouched, still linked to the project
    todos = client.get("/api/todos?view=all").json()
    assert [(t["id"], t["project"]) for t in todos] == [(todo_id, pid)]


def test_reopen_project_undoes_completion(client):
    pid = _create_project(client)
    client.post(f"/api/projects/{pid}/complete")

    resp = client.post(f"/api/projects/{pid}/reopen")
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"
    assert resp.json()["completed"] is None
    assert [p["id"] for p in client.get("/api/projects").json()] == [pid]


def test_delete_project_refuses_while_actions_reference_it(client):
    pid = _create_project(client)
    client.post(f"/api/projects/{pid}/todos", json={"title": "Book slot"})

    assert client.delete(f"/api/projects/{pid}").status_code == 409
    # nothing happened: the project is still there
    assert [p["id"] for p in client.get("/api/projects").json()] == [pid]


def test_delete_project_with_detach_keeps_the_actions(client):
    pid = _create_project(client)
    todo_id = client.post(
        f"/api/projects/{pid}/todos", json={"title": "Book slot"}
    ).json()["id"]

    assert client.delete(f"/api/projects/{pid}?detach=true").status_code == 204
    assert client.get("/api/projects?include_done=true").json() == []
    # the action survives, without a project
    todos = client.get("/api/todos?view=all").json()
    assert [(t["id"], t["project"]) for t in todos] == [(todo_id, None)]


def test_delete_project_without_actions_needs_no_detach(client):
    pid = _create_project(client)
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get("/api/projects?include_done=true").json() == []


def test_archived_todos_never_block_a_deletion(client):
    pid = _create_project(client)
    todo_id = client.post(
        f"/api/projects/{pid}/todos", json={"title": "Was done for it"}
    ).json()["id"]
    client.post(f"/api/todos/{todo_id}/complete")

    # history is a record: it neither blocks nor gets rewritten
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get("/api/done").json()[0]["project"] == pid


def test_missing_project_is_404(client):
    assert client.post("/api/projects/nope/complete").status_code == 404
    assert client.post("/api/projects/nope/reopen").status_code == 404
    assert client.delete("/api/projects/nope").status_code == 404
