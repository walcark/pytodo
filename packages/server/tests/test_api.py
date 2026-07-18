from datetime import date

import pytest
from fastapi.testclient import TestClient

from neverland.core import store
from neverland.core.plan import PlanEntry
from neverland.core.todo import TodoState
from neverland.server.app import create_app
from neverland.server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    """A TestClient over a data repo seeded with a few todos and a plan.

    Reads touch no git, so the repo needs no `git init` here.
    """
    store.create_todo(tmp_path, title="Unclarified thought")  # inbox
    next_todo = store.create_todo(
        tmp_path,
        title="Call plumber",
        state=TodoState.NEXT,
        area="home",
        context="@phone",
    )
    store.create_todo(
        tmp_path, title="Wait on Bob", state=TodoState.WAITING, area="work"
    )

    plan = store.load_day_plan(tmp_path, date.today())
    plan.entries.append(PlanEntry(todo_id=next_todo.id, title=next_todo.title))
    store.save_day_plan(tmp_path, plan)

    config = ServerConfig(data_dir=tmp_path, poll_interval=0)  # no poller in tests
    return TestClient(create_app(config))


def test_vocabulary(client):
    body = client.get("/api/vocabulary").json()
    assert "home" in body["areas"]
    assert "@phone" in body["contexts"]


def test_views_counts(client):
    body = client.get("/api/views").json()
    assert body["inbox"] == 1
    assert body["next"] == 1
    assert body["waiting"] == 1
    assert body["all"] == 3
    assert body["today"] == 1
    home = next(a for a in body["areas"] if a["name"] == "home")
    assert home["count"] == 1
    phone = next(c for c in body["contexts"] if c["name"] == "@phone")
    assert phone["count"] == 1


def test_todos_by_view(client):
    inbox = client.get("/api/todos", params={"view": "inbox"}).json()
    assert [t["title"] for t in inbox] == ["Unclarified thought"]
    assert inbox[0]["state"] == "inbox"

    all_todos = client.get("/api/todos", params={"view": "all"}).json()
    assert len(all_todos) == 3


def test_todos_filtered_by_context(client):
    got = client.get("/api/todos", params={"view": "all", "context": "@phone"}).json()
    assert [t["title"] for t in got] == ["Call plumber"]


def test_unknown_view_is_404(client):
    assert client.get("/api/todos", params={"view": "nope"}).status_code == 404


def test_today_plan(client):
    body = client.get("/api/today").json()
    assert body["day"] == date.today().isoformat()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["status"] == "planned"
